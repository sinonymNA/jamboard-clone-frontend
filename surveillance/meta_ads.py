"""Surveils Meta Ad Library for long-running, high-engagement ads, cycling
through one broad product category per day."""
import logging
from datetime import datetime, timezone

import config
from agent.computer_use import run_agent_task
from agent.session import require_valid_session
from utils import parse_json_response

logger = logging.getLogger("brand_engine.surveillance.meta_ads")

TASK_TEMPLATE = (
    "Navigate to https://www.facebook.com/ads/library/ . Set the country "
    "filter to 'United States'. Set the ad category filter to 'All ads'. "
    "Search for the term '{category}'. Look through the results and "
    "identify ads that appear to have been running for a long time with "
    "high engagement. For up to the top 10 such ads, open each one and "
    "extract: the advertiser name, the ad start date, the total interaction "
    "count (likes + comments + shares, or whatever aggregate engagement "
    "number is shown), the product description from the ad copy, and a "
    "short note on the visual style of the creative. Report your findings "
    "as a single JSON array, one object per ad, with exactly these keys: "
    "advertiser (string), product_description (string), ad_start_date "
    "(string, format YYYY-MM-DD, your best reading of the date shown), "
    "interactions (number), ad_copy (string), visual_style (string)."
)


def _category_for_today() -> str:
    day_index = datetime.now(timezone.utc).timetuple().tm_yday
    categories = config.META_SEARCH_CATEGORIES
    return categories[day_index % len(categories)]


def run_meta_sweep(category: str | None = None) -> list[dict]:
    """Returns filtered, qualifying Meta Ad Library results for today's
    rotating category (or an explicit category override)."""
    if not require_valid_session("facebook"):
        return []

    search_category = category or _category_for_today()
    task = TASK_TEMPLATE.format(category=search_category)

    result = run_agent_task(task)
    if result.get("halted_reason") in ("captcha", "2fa_wall"):
        logger.warning("Meta sweep halted (%s) for category '%s'", result["halted_reason"], search_category)
        return []

    raw_items = _parse_items(result.get("final_text", ""))
    if not raw_items:
        logger.warning("Meta sweep produced no usable data for category '%s'", search_category)
        return []

    captured_at = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date()

    filtered = []
    for item in raw_items:
        days_running = _days_running(item.get("ad_start_date"), today)
        interactions = int(item.get("interactions", 0) or 0)
        if days_running < config.MIN_META_AD_AGE_DAYS:
            continue
        if interactions < config.MIN_META_AD_INTERACTIONS:
            continue
        filtered.append({
            "advertiser": item.get("advertiser", "Unknown"),
            "product_description": item.get("product_description", ""),
            "ad_start_date": item.get("ad_start_date", ""),
            "days_running": days_running,
            "interactions": interactions,
            "ad_copy": item.get("ad_copy", ""),
            "source": "meta_ads",
            "raw_data": item,
            "captured_at": captured_at,
        })

    filtered.sort(key=lambda x: x["interactions"], reverse=True)
    filtered = filtered[:10]

    logger.info(
        "Meta sweep (%s): %s raw items, %s passed filters",
        search_category, len(raw_items), len(filtered),
    )
    return filtered


def _days_running(start_date_str: str | None, today) -> int:
    if not start_date_str:
        return 0
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y"):
        try:
            start = datetime.strptime(start_date_str, fmt).date()
            return max((today - start).days, 0)
        except ValueError:
            continue
    return 0


def _parse_items(text: str) -> list[dict]:
    if not text:
        return []
    data = parse_json_response(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("ads"), list):
        return data["ads"]
    return []
