"""Pure-Python margin math. No API or browser calls."""
import logging

import config

logger = logging.getLogger("brand_engine.analysis.margin")

SALES_SCENARIOS = (100, 200, 500)
PRICE_MULTIPLIERS = (3.0, 3.5, 4.0)


def calculate_margins(cogs: float, product_data: dict | None = None) -> dict:
    """Computes recommended pricing and margin viability for a given COGS.

    Disqualification is absolute: failing either the minimum gross margin
    percentage or the minimum COGS multiplier kills the product regardless
    of every other signal.
    """
    product_data = product_data or {}

    if cogs <= 0:
        return {
            "cogs": cogs,
            "recommended_price": 0.0,
            "gross_margin_dollars": 0.0,
            "gross_margin_percent": 0.0,
            "cogs_multiplier": 0.0,
            "margin_rules_met": False,
            "disqualified": True,
            "disqualification_reason": "Invalid or zero COGS",
            "price_scenarios": [],
        }

    recommended_price = round(cogs * config.MIN_COGS_MULTIPLIER, 2)
    gross_margin_dollars = round(recommended_price - cogs, 2)
    gross_margin_percent = round((gross_margin_dollars / recommended_price) * 100, 2)
    cogs_multiplier = round(recommended_price / cogs, 2)

    margin_ok = gross_margin_percent >= config.MIN_GROSS_MARGIN
    multiplier_ok = cogs_multiplier >= config.MIN_COGS_MULTIPLIER
    margin_rules_met = margin_ok and multiplier_ok

    disqualified = not margin_rules_met
    if disqualified:
        reasons = []
        if not margin_ok:
            reasons.append(
                f"Gross margin {gross_margin_percent}% below minimum {config.MIN_GROSS_MARGIN}%"
            )
        if not multiplier_ok:
            reasons.append(
                f"Price is only {cogs_multiplier}x COGS, below minimum {config.MIN_COGS_MULTIPLIER}x"
            )
        disqualification_reason = "; ".join(reasons)
    else:
        disqualification_reason = ""

    price_scenarios = []
    for multiplier in PRICE_MULTIPLIERS:
        price = round(cogs * multiplier, 2)
        margin_dollars = round(price - cogs, 2)
        margin_percent = round((margin_dollars / price) * 100, 2)
        scenario = {
            "multiplier": multiplier,
            "price": price,
            "margin_dollars": margin_dollars,
            "margin_percent": margin_percent,
            "monthly_profit": {
                str(sales): round(margin_dollars * sales, 2) for sales in SALES_SCENARIOS
            },
        }
        price_scenarios.append(scenario)

    result = {
        "cogs": cogs,
        "recommended_price": recommended_price,
        "gross_margin_dollars": gross_margin_dollars,
        "gross_margin_percent": gross_margin_percent,
        "cogs_multiplier": cogs_multiplier,
        "margin_rules_met": margin_rules_met,
        "disqualified": disqualified,
        "disqualification_reason": disqualification_reason,
        "price_scenarios": price_scenarios,
    }

    logger.info(
        "Margin calc for COGS=$%.2f: price=$%.2f margin=%.1f%% disqualified=%s",
        cogs, recommended_price, gross_margin_percent, disqualified,
    )
    return result
