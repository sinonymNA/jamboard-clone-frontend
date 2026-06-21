"""Generates the complete store copy/asset package once the operator
approves a product, and hands the operator a ready-to-paste package."""
import json
import logging
from pathlib import Path

import config
import storage.database as db
from agent.llm import complete
from notifications.discord import send_message
from utils import parse_json_response

logger = logging.getLogger("brand_engine.workflows.launch")

ASSETS_SYSTEM_PROMPT = (
    "You are a senior direct-response ecommerce copywriter. You write "
    "high-converting Shopify store copy grounded in a specific customer "
    "avatar and positioning angle, not generic marketing language."
)


def _foundational_docs_text(product: dict) -> str:
    docs_path = product.get("foundational_docs_path")
    if not docs_path:
        return ""
    parts = []
    for filename in ("avatar.md", "offer.md", "necessary_beliefs.md", "deep_research.md"):
        try:
            doc_file = Path(docs_path) / filename
            if doc_file.exists():
                parts.append(f"### {filename}\n{doc_file.read_text(encoding='utf-8')[:3000]}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read foundational doc %s: %s", filename, exc)
    return "\n\n".join(parts)


def _generate_store_assets(product: dict) -> dict:
    blind_spot = product.get("blind_spot_data") or {}
    margin = product.get("margin_data") or {}
    foundational_text = _foundational_docs_text(product)

    prompt = (
        f"Product: {product['name']}\n"
        f"Positioning statement: {blind_spot.get('positioning_statement', '')}\n"
        f"Blind spot demographic: {blind_spot.get('blind_spot_demographic', '')}\n"
        f"Purple ocean angle: {blind_spot.get('purple_ocean_angle', '')}\n"
        f"Recommended price: ${margin.get('recommended_price', 0)}\n\n"
        f"Foundational research:\n{foundational_text}\n\n"
        "Generate complete Shopify store assets. Respond with ONLY a JSON "
        "object with exactly these keys: brand_name (string, 2-3 words, "
        "memorable and niche-specific), tagline (string), "
        "product_page_headline (string), product_description (string, "
        "three sections covering pain, solution, proof - use markdown "
        "headers), bullet_points (array of 5 strings, benefit-focused), "
        "faq (array of 5 objects each with 'question' and 'answer' keys, "
        "based on likely objections), meta_title (string, under 60 chars), "
        "meta_description (string, under 160 chars)."
    )

    raw = complete(ASSETS_SYSTEM_PROMPT, prompt, max_tokens=3000)
    data = parse_json_response(raw)
    if not data:
        logger.error("Store asset generation returned no usable data for '%s'", product["slug"])
    return data


def launch_store(product_slug: str) -> dict:
    product = db.get_product_by_slug(product_slug)
    if not product:
        logger.error("launch_store called for unknown slug '%s'", product_slug)
        return {"success": False, "reason": "unknown_product"}

    assets = _generate_store_assets(product)
    if not assets:
        send_message(
            f"⚠️ Could not generate store assets for {product['name']}. "
            f"Will retry on next data entry cycle, or reply REPORT {product_slug} "
            f"to see what's stored so far."
        )
        return {"success": False, "reason": "generation_failed"}

    assets_dir = config.REPORTS_DIR / product_slug / "store_assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "store_assets.json").write_text(json.dumps(assets, indent=2), encoding="utf-8")

    margin = product.get("margin_data") or {}
    db.update_product_status(product_slug, "store_building")

    bullets = "\n".join(f"- {b}" for b in assets.get("bullet_points", []))
    faq_text = "\n".join(
        f"Q: {item.get('question', '')}\nA: {item.get('answer', '')}"
        for item in assets.get("faq", [])
    )

    message = (
        f"🚀 STORE PACKAGE READY — {product['name']}\n\n"
        f"Brand name: {assets.get('brand_name', '')}\n"
        f"Tagline: {assets.get('tagline', '')}\n\n"
        f"Headline: {assets.get('product_page_headline', '')}\n\n"
        f"Description:\n{assets.get('product_description', '')}\n\n"
        f"Bullets:\n{bullets}\n\n"
        f"FAQ:\n{faq_text}\n\n"
        f"Meta title: {assets.get('meta_title', '')}\n"
        f"Meta description: {assets.get('meta_description', '')}\n\n"
        f"Supplier link: {margin.get('source_url', 'see foundational docs')}\n"
        f"Recommended price: ${margin.get('recommended_price', 0)}\n\n"
        "SHOPIFY SETUP STEPS:\n"
        "1. Create a new Shopify store, pick a theme.\n"
        "2. Add product, paste in the title/description/bullets above.\n"
        "3. Set price to the recommended price above.\n"
        "4. Add the FAQ section to the product page or a dedicated page.\n"
        "5. Paste the meta title/description into SEO settings.\n"
        "6. Order a sample from the supplier link, then publish the store.\n\n"
        f"Full foundational docs: {product.get('foundational_docs_path', 'n/a')}\n\n"
        "Reply LIVE when the store is published to get your content brief."
    )
    send_message(message)

    logger.info("Store package generated and sent for '%s'", product_slug)
    return {"success": True, "assets": assets, "assets_path": str(assets_dir)}
