"""Runs automatically whenever a product is killed: figures out what
signal misled the system and feeds that lesson back into future prompts."""
import json
import logging

import config
import storage.database as db
from agent.llm import complete
from notifications.discord import send_message
from scoring.learner import log_outcome
from utils import parse_json_response

logger = logging.getLogger("brand_engine.workflows.autopsy")

AUTOPSY_SYSTEM_PROMPT = (
    "You are a post-mortem analyst for an ecommerce product validation "
    "system. You analyze why a product that was scored as promising ended "
    "up failing, and extract a concrete, reusable pattern for future "
    "screening."
)

OUTCOME_MAP = {
    "no_sales": "killed_no_sales",
    "low_roas": "killed_low_roas",
    "organic_fail": "killed_organic_fail",
}

AUTOPSY_BATCH_SIZE = 5


def run_autopsy(product_slug: str, kill_reason: str) -> dict:
    product = db.get_product_by_slug(product_slug)
    if not product:
        logger.error("run_autopsy called for unknown slug '%s'", product_slug)
        return {"success": False, "reason": "unknown_product"}

    score_history = db.get_scoring_history_with_outcomes()
    own_score = next((s for s in score_history if s.get("product_id") == product["id"]), None)
    score_data = (own_score or {}).get("score_data") or {
        "breakdown": {}, "total_score": product.get("validation_score", 0),
    }

    prompt = (
        f"Product: {product['name']}\n"
        f"Kill reason: {kill_reason}\n"
        f"Validation score at approval time: {score_data.get('total_score')}/100\n"
        f"Score breakdown: {json.dumps(score_data.get('breakdown', {}))}\n"
        f"Blind spot data at approval time: "
        f"{json.dumps(product.get('blind_spot_data') or {})}\n"
        f"Margin data at approval time: {json.dumps(product.get('margin_data') or {})}\n\n"
        "Analyze this failure. Respond with ONLY a JSON object with exactly "
        "these keys: failure_point (string, where in the pipeline the real "
        "problem was - demand signal, margin, blind spot accuracy, "
        "execution, content, ads, etc), misleading_signals (array of "
        "strings, which specific data points looked good but were "
        "misleading), lessons_learned (string), pattern_identified "
        "(string, a short, generalizable pattern to watch for in future "
        "screening - phrase it so it can be prepended directly to future "
        "scoring prompts)."
    )

    raw = complete(AUTOPSY_SYSTEM_PROMPT, prompt, max_tokens=1200)
    autopsy_data = parse_json_response(raw)
    if not autopsy_data:
        logger.error("Autopsy generation failed for '%s'", product_slug)
        autopsy_data = {
            "failure_point": "unknown",
            "misleading_signals": [],
            "lessons_learned": "Autopsy generation failed.",
            "pattern_identified": "",
        }

    autopsy_data["kill_reason"] = kill_reason
    db.log_autopsy(product["id"], autopsy_data)

    autopsy_path = config.AUTOPSIES_DIR / f"{product_slug}.json"
    try:
        autopsy_path.write_text(json.dumps(autopsy_data, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to write autopsy file for '%s': %s", product_slug, exc)

    outcome = OUTCOME_MAP.get(kill_reason, "killed_no_sales")
    log_outcome(product_slug, outcome, autopsy_data)
    db.kill_product(product_slug, kill_reason)

    send_message(
        f"🪦 AUTOPSY — {product['name']}\n"
        f"Kill reason: {kill_reason}\n"
        f"Failure point: {autopsy_data.get('failure_point')}\n"
        f"Lesson: {autopsy_data.get('lessons_learned')}"
    )

    total_autopsies = db.count_autopsies()
    if total_autopsies and total_autopsies % AUTOPSY_BATCH_SIZE == 0:
        _send_pattern_summary()

    logger.info("Autopsy complete for '%s': %s", product_slug, autopsy_data.get("failure_point"))
    return {"success": True, "autopsy": autopsy_data}


def _send_pattern_summary() -> None:
    autopsies = db.get_all_autopsies()[:AUTOPSY_BATCH_SIZE]
    patterns = [a.get("pattern_identified") for a in autopsies if a.get("pattern_identified")]
    if not patterns:
        return

    prompt = (
        "Here are the patterns identified in the last "
        f"{len(patterns)} product autopsies:\n" + "\n".join(f"- {p}" for p in patterns) +
        "\n\nIdentify the single most important recurring pattern across "
        "these, if one exists. Respond with ONLY a JSON object with keys: "
        "pattern_detected (boolean), description (string, one sentence "
        "stating the pattern and the recommended filter adjustment - empty "
        "string if pattern_detected is false)."
    )
    raw = complete(AUTOPSY_SYSTEM_PROMPT, prompt, max_tokens=400)
    result = parse_json_response(raw)
    if result.get("pattern_detected") and result.get("description"):
        send_message(f"🔍 Pattern detected: {result['description']}")
