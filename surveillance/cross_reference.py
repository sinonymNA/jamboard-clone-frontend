"""Semantically matches TikTok Shop and Meta Ad Library results to find
products that are winning in both feeds simultaneously (Priority 1)."""
import logging

from agent.llm import complete
from utils import parse_json_response

logger = logging.getLogger("brand_engine.surveillance.cross_reference")

SYSTEM_PROMPT = (
    "You are a product-matching analyst for ecommerce surveillance. You "
    "compare product listings from two different sources and determine "
    "whether they represent the same underlying product concept, even if "
    "named or described differently. Two products match if they serve the "
    "same core function for the customer."
)


def cross_reference(tiktok_results: list, meta_results: list) -> dict:
    """Returns {"priority_1": [...], "priority_2": [...], "filtered": []}."""
    matches = []
    matched_tiktok_indices = set()
    matched_meta_indices = set()

    if tiktok_results and meta_results:
        matches, matched_tiktok_indices, matched_meta_indices = _find_matches(
            tiktok_results, meta_results
        )

    priority_1 = []
    for match in matches:
        tiktok_item = tiktok_results[match["tiktok_index"]]
        meta_item = meta_results[match["meta_index"]]
        priority_1.append({
            "product_concept": match.get("product_concept", tiktok_item.get("name", "Unknown")),
            "tiktok_data": tiktok_item,
            "meta_data": meta_item,
            "overlap_confidence": match.get("confidence", 0.0),
            "priority": 1,
        })

    priority_2 = []
    for idx, item in enumerate(tiktok_results):
        if idx not in matched_tiktok_indices:
            priority_2.append({
                "product_concept": item.get("name", "Unknown"),
                "data": item,
                "source": "tiktok_shop",
                "priority": 2,
            })
    for idx, item in enumerate(meta_results):
        if idx not in matched_meta_indices:
            priority_2.append({
                "product_concept": item.get("product_description", item.get("advertiser", "Unknown")),
                "data": item,
                "source": "meta_ads",
                "priority": 2,
            })

    logger.info(
        "Cross reference: %s priority_1, %s priority_2",
        len(priority_1), len(priority_2),
    )
    return {"priority_1": priority_1, "priority_2": priority_2, "filtered": []}


def _find_matches(tiktok_results: list, meta_results: list) -> tuple[list, set, set]:
    tiktok_listing = "\n".join(
        f"[T{i}] {item.get('name', '')} (category: {item.get('category', '')})"
        for i, item in enumerate(tiktok_results)
    )
    meta_listing = "\n".join(
        f"[M{i}] {item.get('product_description', '')} (advertiser: {item.get('advertiser', '')})"
        for i, item in enumerate(meta_results)
    )

    prompt = (
        f"TikTok Shop products:\n{tiktok_listing}\n\n"
        f"Meta Ad Library products:\n{meta_listing}\n\n"
        "Identify every pair (Tn, Mm) where the two represent the same "
        "underlying product concept. Example: 'Smart Jump Rope' and 'Digital "
        "Jump Rope Counter' are the same concept. Respond with ONLY a JSON "
        "array of objects, one per matched pair, with exactly these keys: "
        "tiktok_index (integer, the T number), meta_index (integer, the M "
        "number), product_concept (string, a short name for the shared "
        "concept), confidence (float 0-1). If there are no matches, return "
        "an empty array []."
    )

    raw = complete(SYSTEM_PROMPT, prompt, max_tokens=1500)
    parsed = parse_json_response(raw)
    if not isinstance(parsed, list):
        parsed = parsed.get("matches", []) if isinstance(parsed, dict) else []

    matches = []
    matched_tiktok = set()
    matched_meta = set()
    for match in parsed:
        try:
            t_idx = int(match["tiktok_index"])
            m_idx = int(match["meta_index"])
        except (KeyError, ValueError, TypeError):
            continue
        if not (0 <= t_idx < len(tiktok_results)) or not (0 <= m_idx < len(meta_results)):
            continue
        matches.append({
            "tiktok_index": t_idx,
            "meta_index": m_idx,
            "product_concept": match.get("product_concept", ""),
            "confidence": float(match.get("confidence", 0) or 0),
        })
        matched_tiktok.add(t_idx)
        matched_meta.add(m_idx)

    return matches, matched_tiktok, matched_meta
