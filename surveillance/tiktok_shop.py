"""Surveils TikTok Shop's bestseller/trending surface for rising products."""
import logging
from datetime import datetime, timezone

import config
from agent.computer_use import run_agent_task
from utils import parse_json_response

logger = logging.getLogger("brand_engine.surveillance.tiktok_shop")

EXCLUDED_KEYWORDS = {"course", "ebook", "digital", "subscription", "alcohol", "vape", "cbd"}
EXCLUDED_CATEGORIES = {"food", "grocery", "snacks", "beverages", "digital products", "age-restricted"}

PRIMARY_TASK = (
    "Navigate to https://shop.tiktok.com/ and find the bestseller or "
    "trending products section. Look at the top 20 products. For each one "
    "extract: the product name, the category, an order count or sales "
    "velocity indicator (orders per day or total orders if that's what's "
    "shown), week-over-week growth percentage if displayed, and a short "
    "note on its visual characteristics (is it something that would film "
    "well). Report your findings as a single JSON array, one object per "
    "product, with exactly these keys: name (string), category (string), "
    "orders_per_day (number, your best estimate from whatever sales data is "
    "shown), growth_percent (number, 0 if not available), visual_notes "
    "(string)."
)

FALLBACK_TASK = (
    "The TikTok Shop bestseller page did not load as expected. Instead, "
    "navigate to the TikTok Creator Marketplace and search for top "
    "performing product videos from the last 7 days. Look at the top 20 "
    "results. For each one extract: the product name shown or implied, the "
    "category, an estimate of orders per day based on video performance "
    "metrics (views/engagement as a proxy if no direct sales count is shown), "
    "any growth indicator, and a short visual note. Report your findings as "
    "a single JSON array, one object per product, with exactly these keys: "
    "name (string), category (string), orders_per_day (number, your best "
    "estimate), growth_percent (number, 0 if not available), visual_notes "
    "(string)."
)


def _is_excluded(item: dict) -> bool:
    category = (item.get("category") or "").lower()
    name = (item.get("name") or "").lower()
    if any(cat in category for cat in EXCLUDED_CATEGORIES):
        return True
    if any(keyword in name for keyword in EXCLUDED_KEYWORDS):
        return True
    return False


def run_tiktok_sweep() -> list[dict]:
    """Returns filtered, qualifying TikTok Shop products."""
    result = run_agent_task(PRIMARY_TASK)
    raw_items = _parse_items(result.get("final_text", ""))

    if not raw_items and result.get("halted_reason") not in ("captcha", "2fa_wall"):
        logger.warning("Primary TikTok Shop sweep returned no data, trying fallback")
        fallback_result = run_agent_task(FALLBACK_TASK)
        raw_items = _parse_items(fallback_result.get("final_text", ""))

    if not raw_items:
        logger.error("TikTok sweep produced no usable data from any source")
        return []

    captured_at = datetime.now(timezone.utc).isoformat()
    filtered = []
    for item in raw_items:
        if _is_excluded(item):
            continue
        orders_per_day = int(item.get("orders_per_day", 0) or 0)
        growth_percent = float(item.get("growth_percent", 0) or 0)
        if orders_per_day < config.MIN_TIKTOK_ORDERS_PER_DAY:
            continue
        if item.get("growth_percent") and growth_percent < config.MIN_TIKTOK_GROWTH_PERCENT:
            continue
        filtered.append({
            "name": item.get("name", "Unknown"),
            "category": item.get("category", "unknown"),
            "orders_per_day": orders_per_day,
            "growth_percent": growth_percent,
            "source": "tiktok_shop",
            "raw_data": item,
            "captured_at": captured_at,
        })

    logger.info("TikTok sweep: %s raw items, %s passed filters", len(raw_items), len(filtered))
    return filtered


def _parse_items(text: str) -> list[dict]:
    if not text:
        return []
    data = parse_json_response(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("products"), list):
        return data["products"]
    return []
