"""Prepares dark-post and scaling ad briefs for operator approval. The
system cannot operate Ads Manager itself (2FA), so it hands over a complete,
step-by-step brief instead."""
import logging

import config
import storage.database as db
from agent.llm import complete
from notifications.discord import send_message
from utils import parse_json_response

logger = logging.getLogger("brand_engine.workflows.ads")

AD_SYSTEM_PROMPT = (
    "You are a senior paid social media buyer. You write precise, "
    "step-by-step Meta Ads Manager setup instructions that a non-technical "
    "operator can follow exactly."
)


def prepare_ad_brief(product_slug: str, organic_post_data: dict) -> dict:
    product = db.get_product_by_slug(product_slug)
    if not product:
        logger.error("prepare_ad_brief called for unknown slug '%s'", product_slug)
        return {"success": False, "reason": "unknown_product"}

    blind_spot = product.get("blind_spot_data") or {}
    prompt = (
        f"Product: {product['name']}\n"
        f"Blind spot demographic: {blind_spot.get('blind_spot_demographic', '')}\n"
        f"Best performing organic post: {organic_post_data.get('description', '')} "
        f"(save rate: {organic_post_data.get('save_rate', 0)})\n"
        f"Daily budget cap: ${config.MAX_DAILY_AD_SPEND}\n\n"
        "Write a $20/day dark post test brief. Respond with ONLY a JSON "
        "object with keys: creative_to_use (string), target_audience "
        "(object with age_range, gender, interests as array), "
        "campaign_objective (string), daily_budget (number, do not exceed "
        "20), schedule (string), expected_results_range (string), "
        "setup_steps (array of strings, exact Ads Manager steps in order)."
    )

    raw = complete(AD_SYSTEM_PROMPT, prompt, max_tokens=1500)
    brief = parse_json_response(raw)
    if not brief:
        logger.error("Ad brief generation failed for '%s'", product_slug)
        return {"success": False, "reason": "generation_failed"}

    steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(brief.get("setup_steps", [])))
    audience = brief.get("target_audience", {})

    message = (
        f"💰 AD BRIEF READY — {product['name']}\n\n"
        f"Creative: {brief.get('creative_to_use', '')}\n"
        f"Audience: {audience.get('age_range', '')} {audience.get('gender', '')}, "
        f"interests: {', '.join(audience.get('interests', []))}\n"
        f"Objective: {brief.get('campaign_objective', '')}\n"
        f"Budget: ${brief.get('daily_budget', 20)}/day\n"
        f"Schedule: {brief.get('schedule', '')}\n"
        f"Expected results: {brief.get('expected_results_range', '')}\n\n"
        f"SETUP STEPS:\n{steps}\n\n"
        f"Reply APPROVE ${brief.get('daily_budget', 20)}/day {product_slug} to confirm."
    )
    send_message(message)

    logger.info("Ad brief prepared for '%s'", product_slug)
    return {"success": True, "brief": brief}


def prepare_scale_brief(product_slug: str, current_roas: float) -> dict:
    product = db.get_product_by_slug(product_slug)
    if not product:
        logger.error("prepare_scale_brief called for unknown slug '%s'", product_slug)
        return {"success": False, "reason": "unknown_product"}

    prompt = (
        f"Product: {product['name']}\n"
        f"Current ROAS: {current_roas}\n"
        f"Daily budget cap: ${config.MAX_DAILY_AD_SPEND}\n\n"
        "This product has sustained ROAS above the scale threshold. Write a "
        "scaling recommendation. Respond with ONLY a JSON object with keys: "
        "recommended_new_daily_budget (number, do not exceed the cap), "
        "new_creative_variations (array of strings, ideas to test), "
        "audience_expansion_suggestions (array of strings), "
        "risk_assessment (string)."
    )

    raw = complete(AD_SYSTEM_PROMPT, prompt, max_tokens=1200)
    brief = parse_json_response(raw)
    if not brief:
        logger.error("Scale brief generation failed for '%s'", product_slug)
        return {"success": False, "reason": "generation_failed"}

    new_budget = min(
        float(brief.get("recommended_new_daily_budget", 0) or 0), config.MAX_DAILY_AD_SPEND
    )
    variations = "\n".join(f"- {v}" for v in brief.get("new_creative_variations", []))
    expansions = "\n".join(f"- {e}" for e in brief.get("audience_expansion_suggestions", []))

    message = (
        f"📈 SCALE RECOMMENDATION — {product['name']}\n\n"
        f"Current ROAS: {current_roas:.2f}x (above scale threshold)\n"
        f"Recommended new daily budget: ${new_budget:.2f}\n\n"
        f"New creative to test:\n{variations}\n\n"
        f"Audience expansion ideas:\n{expansions}\n\n"
        f"Risk: {brief.get('risk_assessment', '')}\n\n"
        f"Reply APPROVE ${new_budget:.2f}/day {product_slug} to confirm."
    )
    send_message(message)

    logger.info("Scale brief prepared for '%s' at ROAS %.2f", product_slug, current_roas)
    return {"success": True, "brief": brief, "recommended_new_daily_budget": new_budget}
