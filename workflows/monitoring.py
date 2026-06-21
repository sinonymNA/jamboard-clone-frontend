"""Daily monitoring of active products against ROAS cut/scale rules and
organic content performance, based on operator-entered performance data."""
import logging

import config
import storage.database as db
from notifications.discord import send_message
from workflows.ads import prepare_scale_brief

logger = logging.getLogger("brand_engine.workflows.monitoring")

ACTIVE_STATUSES = ("live", "scaling")


def _roas_trend(roas_series: list[float]) -> str:
    if len(roas_series) < 3:
        return "insufficient_data"
    recent = roas_series[:3]  # most recent first (query orders DESC)
    if recent[0] < recent[1] < recent[2]:
        return "declining"
    if recent[0] > recent[1] > recent[2]:
        return "improving"
    return "flat"


def _check_product(product: dict) -> dict:
    history = db.get_recent_performance(product["id"], days=7)
    roas_series = [h["roas"] for h in history if h.get("roas") is not None]

    avg_roas = round(sum(roas_series) / len(roas_series), 2) if roas_series else 0.0
    trend = _roas_trend(roas_series)

    action = "none"
    alert_sent = False

    consecutive_low = sum(
        1 for r in roas_series[: config.ROAS_CUT_CONSECUTIVE_DAYS] if r < config.ROAS_CUT_THRESHOLD
    )
    consecutive_high = sum(
        1 for r in roas_series[: config.ROAS_SCALE_CONSECUTIVE_DAYS] if r > config.ROAS_SCALE_THRESHOLD
    )

    if len(roas_series) >= config.ROAS_CUT_CONSECUTIVE_DAYS and consecutive_low >= config.ROAS_CUT_CONSECUTIVE_DAYS:
        action = "PAUSE"
        send_message(
            f"⚠️ {product['name']}: ROAS below {config.ROAS_CUT_THRESHOLD}x for "
            f"{config.ROAS_CUT_CONSECUTIVE_DAYS} consecutive days (avg {avg_roas}x). "
            f"Recommend PAUSE. Reply PAUSE {product['slug']} to confirm or KILL "
            f"{product['slug']} to end it."
        )
        alert_sent = True
    elif len(roas_series) >= config.ROAS_SCALE_CONSECUTIVE_DAYS and consecutive_high >= config.ROAS_SCALE_CONSECUTIVE_DAYS:
        action = "SCALE"
        try:
            prepare_scale_brief(product["slug"], avg_roas)
        except Exception as exc:  # noqa: BLE001
            logger.error("Scale brief failed for '%s': %s", product["slug"], exc)
        alert_sent = True
    elif trend == "declining":
        action = "WARNING"
        send_message(
            f"📉 {product['name']}: ROAS trending down over last 3 entries "
            f"(avg {avg_roas}x). Watching closely."
        )
        alert_sent = True

    organic_entries = [h for h in history if h.get("save_rate") is not None]
    if len(organic_entries) >= 2:
        recent_save_rates = [h["save_rate"] for h in organic_entries[:2]]
        if all(rate < config.ORGANIC_SAVE_RATE_THRESHOLD for rate in recent_save_rates):
            send_message(
                f"🎬 {product['name']}: organic save rate below "
                f"{config.ORGANIC_SAVE_RATE_THRESHOLD * 100:.1f}% for last 2 posts. "
                f"Recommend testing a new content angle."
            )
            alert_sent = True

    check = {
        "roas_7day_avg": avg_roas,
        "roas_trend": trend,
        "action_recommended": action,
        "alert_sent": alert_sent,
    }
    db.log_monitoring_check(product["id"], check)
    return check


def run_monitoring_check() -> dict:
    products = []
    for status in ACTIVE_STATUSES:
        products.extend(db.get_products_by_status(status))

    if not products:
        logger.info("No active products to monitor")
        return {"checked": 0, "alerts_sent": 0}

    alerts_sent = 0
    for product in products:
        try:
            result = _check_product(product)
            if result["alert_sent"]:
                alerts_sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Monitoring check crashed for '%s': %s", product.get("slug"), exc)

    logger.info("Monitoring check complete: %s products, %s alerts", len(products), alerts_sent)
    return {"checked": len(products), "alerts_sent": alerts_sent}
