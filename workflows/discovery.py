"""Master discovery workflow: surveils both feeds, cross-references,
validates, scores, and queues approval requests for the operator."""
import logging

import config
import storage.database as db
from analysis.blind_spot import find_blind_spot, generate_foundational_docs
from analysis.margin import calculate_margins
from analysis.supplier import find_supplier
from notifications.discord import send_discovery_alert, send_message
from scoring.scorer import format_approval_request, score_product
from surveillance.cross_reference import cross_reference
from surveillance.meta_ads import run_meta_sweep
from surveillance.tiktok_shop import run_tiktok_sweep
from utils import slugify

logger = logging.getLogger("brand_engine.workflows.discovery")


def _tiktok_summary(item: dict | None) -> str:
    if not item:
        return "N/A"
    return f"{item.get('orders_per_day', 0)} orders/day, +{item.get('growth_percent', 0)}% WoW"


def _meta_summary(item: dict | None) -> str:
    if not item:
        return "N/A"
    return f"{item.get('days_running', 0)} days running, {item.get('interactions', 0)} interactions"


def _build_product_data(entry: dict) -> tuple[dict, dict]:
    """Converts a cross_reference entry into (product_data, surveillance_data)."""
    if entry["priority"] == 1:
        tiktok_data = entry["tiktok_data"]
        meta_data = entry["meta_data"]
        name = entry.get("product_concept") or tiktok_data.get("name", "Unknown product")
        product_data = {
            "name": name,
            "slug": slugify(name),
            "category": tiktok_data.get("category", "unknown"),
            "description": f"{name} - {tiktok_data.get('visual_notes', '')} {meta_data.get('product_description', '')}".strip(),
            "ad_copy": meta_data.get("ad_copy", ""),
            "current_target_demographic": "unknown, infer from ad copy",
            "price_point": "unknown",
            "overlap": True,
            "tiktok_summary": _tiktok_summary(tiktok_data),
            "meta_summary": _meta_summary(meta_data),
        }
        surveillance_data = {"tiktok": tiktok_data, "meta": meta_data, "overlap": True}
    else:
        data = entry["data"]
        source = entry["source"]
        name = entry.get("product_concept") or data.get("name") or data.get("product_description", "Unknown product")
        product_data = {
            "name": name,
            "slug": slugify(name),
            "category": data.get("category", "unknown"),
            "description": data.get("visual_notes") or data.get("product_description") or name,
            "ad_copy": data.get("ad_copy", ""),
            "current_target_demographic": "unknown, infer from ad copy",
            "price_point": "unknown",
            "overlap": False,
            "tiktok_summary": _tiktok_summary(data if source == "tiktok_shop" else None),
            "meta_summary": _meta_summary(data if source == "meta_ads" else None),
        }
        surveillance_data = {
            "tiktok": data if source == "tiktok_shop" else None,
            "meta": data if source == "meta_ads" else None,
            "overlap": False,
        }
    return product_data, surveillance_data


def _evaluate_candidate(entry: dict) -> dict | None:
    """Runs supplier lookup, margin check, blind spot analysis, and scoring
    for one candidate. Returns the approval-queue entry or None if skipped/
    disqualified."""
    product_data, surveillance_data = _build_product_data(entry)
    slug = product_data["slug"]

    if db.get_product_by_slug(slug):
        logger.info("Skipping '%s', already in database", slug)
        return None

    try:
        supplier_data = find_supplier(product_data["name"])
    except Exception as exc:  # noqa: BLE001
        logger.error("Supplier lookup failed for '%s': %s", slug, exc)
        return None

    margin_data = calculate_margins(supplier_data.get("total_cogs", 0), product_data)
    margin_data["supplier"] = supplier_data.get("supplier")
    margin_data["source_url"] = supplier_data.get("source_url")
    margin_data["delivery_days"] = supplier_data.get("delivery_days")
    if margin_data["disqualified"]:
        logger.info("Disqualified '%s' on margins: %s", slug, margin_data["disqualification_reason"])
        db.log_system_event("INFO", "workflows.discovery", f"Disqualified {slug} on margins", margin_data)
        return None

    try:
        blind_spot_data = find_blind_spot(product_data)
    except Exception as exc:  # noqa: BLE001
        logger.error("Blind spot analysis failed for '%s': %s", slug, exc)
        return None

    score_data = score_product(product_data, blind_spot_data, margin_data, surveillance_data)
    if score_data["total_score"] < 60 or score_data["disqualified"]:
        logger.info("Filtered '%s' below threshold: %s/100", slug, score_data["total_score"])
        return None

    try:
        docs_path = generate_foundational_docs(product_data, blind_spot_data)
    except Exception as exc:  # noqa: BLE001
        logger.error("Foundational docs generation failed for '%s': %s", slug, exc)
        docs_path = ""

    product_id = db.upsert_product({
        "name": product_data["name"],
        "slug": slug,
        "status": "pending_approval",
        "priority": entry["priority"],
        "validation_score": int(score_data["total_score"]),
        "validation_threshold": score_data["threshold"],
        "tiktok_data": surveillance_data.get("tiktok"),
        "meta_data": surveillance_data.get("meta"),
        "blind_spot_data": blind_spot_data,
        "margin_data": margin_data,
        "foundational_docs_path": docs_path,
    })
    db.log_scoring(product_id, score_data, score_data["weights_used"])

    approval_text = format_approval_request(score_data, product_data, blind_spot_data, margin_data)
    return {
        "slug": slug,
        "score": score_data["total_score"],
        "threshold": score_data["threshold"],
        "approval_text": approval_text,
    }


def run_discovery_workflow() -> dict:
    active_stores = db.count_active_stores()
    if active_stores >= config.MAX_ACTIVE_STORES:
        logger.info("At capacity (%s/%s active stores). Skipping discovery.", active_stores, config.MAX_ACTIVE_STORES)
        db.log_system_event(
            "INFO", "workflows.discovery",
            f"At capacity ({active_stores}/{config.MAX_ACTIVE_STORES}), discovery skipped",
        )
        return {"status": "skipped_at_capacity", "products_found": 0, "products_escalated": 0, "products_filtered": 0}

    try:
        tiktok_results = run_tiktok_sweep()
    except Exception as exc:  # noqa: BLE001
        logger.error("TikTok sweep crashed: %s", exc)
        tiktok_results = []

    try:
        meta_results = run_meta_sweep()
    except Exception as exc:  # noqa: BLE001
        logger.error("Meta sweep crashed: %s", exc)
        meta_results = []

    cross_ref = cross_reference(tiktok_results, meta_results)

    queued = []
    products_found = len(cross_ref["priority_1"]) + len(cross_ref["priority_2"])
    products_filtered = 0

    for entry in cross_ref["priority_1"]:
        try:
            result = _evaluate_candidate(entry)
        except Exception as exc:  # noqa: BLE001
            logger.error("Candidate evaluation crashed: %s", exc)
            result = None
        if result:
            queued.append(result)
        else:
            products_filtered += 1

    if not queued:
        for entry in cross_ref["priority_2"]:
            try:
                result = _evaluate_candidate(entry)
            except Exception as exc:  # noqa: BLE001
                logger.error("Candidate evaluation crashed: %s", exc)
                result = None
            if result:
                queued.append(result)
            else:
                products_filtered += 1

    db.log_surveillance_run(
        tiktok_results, meta_results, cross_ref,
        products_found, len(queued), products_filtered,
    )

    if queued:
        header = f"🔥 Discovery sweep complete: {len(queued)} product(s) ready for review.\n"
        send_message(header)
        for item in queued:
            send_discovery_alert(item["approval_text"])
    else:
        send_message(
            f"Discovery sweep complete. {products_found} candidates evaluated, "
            f"none cleared the bar. Pipeline unchanged."
        )

    logger.info(
        "Discovery workflow complete: found=%s escalated=%s filtered=%s",
        products_found, len(queued), products_filtered,
    )
    return {
        "status": "complete",
        "products_found": products_found,
        "products_escalated": len(queued),
        "products_filtered": products_filtered,
    }
