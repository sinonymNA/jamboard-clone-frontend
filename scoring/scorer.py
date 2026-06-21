"""Implements the 100-point scoring framework and Discord approval formatting."""
import logging

from scoring.learner import load_weights

logger = logging.getLogger("brand_engine.scoring.scorer")

KILL_THRESHOLD = 60
WEAK_THRESHOLD = 60
STRONG_THRESHOLD = 75
PRIORITY_THRESHOLD = 85


def _demand_signal(surveillance_data: dict) -> float:
    tiktok = surveillance_data.get("tiktok") or {}
    meta = surveillance_data.get("meta") or {}
    points = 0.0

    orders = tiktok.get("orders_per_day", 0) or 0
    if orders >= 500:
        points += 15
    elif orders >= 200:
        points += 8

    days_running = meta.get("days_running", 0) or 0
    if days_running >= 180:
        points += 10
    elif days_running >= 90:
        points += 5

    if surveillance_data.get("overlap"):
        points += 5

    return min(points, 25.0)


def _market_timing(surveillance_data: dict) -> float:
    tiktok = surveillance_data.get("tiktok") or {}
    meta = surveillance_data.get("meta") or {}
    points = 0.0

    growth = tiktok.get("growth_percent", 0) or 0
    if growth >= 200:
        points += 10
    elif growth >= 100:
        points += 6

    interactions = meta.get("interactions", 0) or 0
    if interactions >= 50000:
        points += 10
    elif interactions >= 10000:
        points += 5

    return min(points, 20.0)


def _margin_viability(margin_data: dict) -> tuple[float, bool, str]:
    if margin_data.get("disqualified"):
        return 0.0, True, margin_data.get("disqualification_reason", "Margin rules not met")
    if margin_data.get("margin_rules_met"):
        return 20.0, False, ""
    return 0.0, True, "Margin rules not met"


def _purple_ocean_clarity(blind_spot_data: dict) -> float:
    confidence = blind_spot_data.get("confidence", 0) or 0
    if confidence >= 0.8:
        return 20.0
    if confidence >= 0.6:
        return 12.0
    return 5.0


def _organic_content_potential(blind_spot_data: dict, product_data: dict) -> float:
    points = 0.0
    if blind_spot_data.get("visual_product") or product_data.get("visual_product"):
        points += 5
    if blind_spot_data.get("problem_relatable") or product_data.get("problem_relatable"):
        points += 5
    if blind_spot_data.get("tiktok_angle_obvious") or product_data.get("tiktok_angle_obvious"):
        points += 5
    return min(points, 15.0)


def _threshold_label(score: float, disqualified: bool) -> str:
    if disqualified:
        return "KILLED"
    if score < KILL_THRESHOLD:
        return "AUTO-KILL"
    if score < STRONG_THRESHOLD:
        return "WEAK"
    if score < PRIORITY_THRESHOLD:
        return "STRONG"
    return "PRIORITY"


def score_product(
    product_data: dict,
    blind_spot_data: dict,
    margin_data: dict,
    surveillance_data: dict,
) -> dict:
    """Scores a product 0-100 across five weighted dimensions.

    Margin viability is pass/fail: failing either margin rule auto-
    disqualifies the product regardless of every other dimension.
    """
    weights = load_weights()

    margin_points, disqualified, disqualification_reason = _margin_viability(margin_data)

    breakdown = {
        "demand_signal": round(_demand_signal(surveillance_data) * weights.get("demand_signal", 1.0), 2),
        "market_timing": round(_market_timing(surveillance_data) * weights.get("market_timing", 1.0), 2),
        "margin_viability": margin_points,
        "purple_ocean_clarity": round(
            _purple_ocean_clarity(blind_spot_data) * weights.get("purple_ocean_clarity", 1.0), 2
        ),
        "organic_content_potential": round(
            _organic_content_potential(blind_spot_data, product_data)
            * weights.get("organic_content_potential", 1.0),
            2,
        ),
    }

    total_score = round(sum(breakdown.values()), 1) if not disqualified else 0

    result = {
        "total_score": total_score,
        "breakdown": breakdown,
        "threshold": _threshold_label(total_score, disqualified),
        "disqualified": disqualified,
        "disqualification_reason": disqualification_reason,
        "blind_spot_confidence": blind_spot_data.get("confidence", 0),
        "weights_used": weights,
    }

    logger.info(
        "Scored product '%s': %s/100 (%s)%s",
        product_data.get("name", "unknown"),
        total_score,
        result["threshold"],
        f" - DISQUALIFIED: {disqualification_reason}" if disqualified else "",
    )
    return result


def format_approval_request(
    score_data: dict,
    product_data: dict,
    blind_spot_data: dict,
    margin_data: dict,
) -> str:
    priority_label = "OVERLAP DETECTED" if product_data.get("overlap") else "SINGLE FEED"
    name = product_data.get("name", "Unknown product")

    tiktok = product_data.get("tiktok_summary", "N/A")
    meta = product_data.get("meta_summary", "N/A")

    blind_spot_summary = (
        f"{blind_spot_data.get('blind_spot_demographic', 'Unknown demographic')}. "
        f"{blind_spot_data.get('why_underserved', '')} "
        f"{blind_spot_data.get('purple_ocean_angle', '')}"
    ).strip()

    cogs = margin_data.get("cogs", 0)
    sell_price = margin_data.get("recommended_price", 0)
    gross_margin = margin_data.get("gross_margin_dollars", 0)
    multiplier = margin_data.get("cogs_multiplier", 0)
    margin_ok = "✓" if margin_data.get("margin_rules_met") else "✗"

    threshold = score_data.get("threshold", "UNKNOWN")
    recommendation = {
        "PRIORITY": "Immediate review recommended — strong signal across all dimensions.",
        "STRONG": "Solid candidate, recommend approval.",
        "WEAK": "Marginal — only worth approving if pipeline is empty.",
    }.get(threshold, "Review carefully before approving.")

    return (
        f"🔥 BRAND ENGINE — {threshold} FIND\n"
        f"{priority_label}\n\n"
        f"Product: {name}\n"
        f"TikTok: {tiktok}\n"
        f"Meta: {meta}\n"
        f"Score: {score_data.get('total_score', 0)}/100 — {threshold}\n\n"
        f"BLIND SPOT:\n{blind_spot_summary}\n\n"
        f"MARGINS:\n"
        f"COGS: ${cogs:.2f} | Sell price: ${sell_price:.2f}\n"
        f"Gross margin: ${gross_margin:.2f} ({multiplier:.1f}x COGS) {margin_ok}\n\n"
        f"RECOMMENDATION: {recommendation}\n\n"
        f"Reply APPROVE, SKIP, or REPORT {product_data.get('slug', name)}"
    )
