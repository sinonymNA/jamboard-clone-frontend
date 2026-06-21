"""Tracks product outcomes and adjusts scoring weights based on what actually
predicted success, so the system improves with every completed product."""
import json
import logging

import config
import storage.database as db

logger = logging.getLogger("brand_engine.scoring.learner")

DEFAULT_WEIGHTS = {
    "demand_signal": 1.0,
    "market_timing": 1.0,
    "margin_viability": 1.0,
    "purple_ocean_clarity": 1.0,
    "organic_content_potential": 1.0,
}

OUTCOMES_PER_RECALC = 5

POSITIVE_OUTCOMES = {"profitable", "scaling"}
NEGATIVE_OUTCOMES = {"killed_no_sales", "killed_low_roas", "killed_organic_fail", "paused"}


def load_weights() -> dict:
    if not config.SCORING_WEIGHTS_PATH.exists():
        save_weights(DEFAULT_WEIGHTS)
        return dict(DEFAULT_WEIGHTS)
    try:
        return json.loads(config.SCORING_WEIGHTS_PATH.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load scoring weights, using defaults: %s", exc)
        return dict(DEFAULT_WEIGHTS)


def save_weights(weights: dict) -> None:
    try:
        config.SCORING_WEIGHTS_PATH.write_text(json.dumps(weights, indent=2))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save scoring weights: %s", exc)


def log_outcome(product_slug: str, outcome: str, data: dict | None = None) -> None:
    """Records a terminal (or scaling) outcome for a product and triggers a
    weight recalculation every OUTCOMES_PER_RECALC outcomes."""
    product = db.get_product_by_slug(product_slug)
    if not product:
        logger.warning("log_outcome called for unknown product slug: %s", product_slug)
        return

    db.update_scoring_outcome(product["id"], outcome)
    db.log_system_event(
        "INFO", "scoring.learner",
        f"Outcome logged for {product_slug}: {outcome}", data or {},
    )

    total = db.count_terminal_outcomes_since_last_update()
    if total and total % OUTCOMES_PER_RECALC == 0:
        logger.info("Reached %s terminal outcomes, recalculating scoring weights", total)
        update_scoring_weights()


def update_scoring_weights() -> dict:
    """Analyzes historical score_data vs outcome to nudge dimension weights
    toward whatever best separated winners from losers. Conservative,
    bounded adjustment - this is directional learning, not a model fit."""
    history = db.get_scoring_history_with_outcomes()
    if len(history) < 2:
        return load_weights()

    weights = load_weights()
    dimensions = list(DEFAULT_WEIGHTS.keys())

    dimension_totals = {d: {"win_sum": 0.0, "win_n": 0, "loss_sum": 0.0, "loss_n": 0} for d in dimensions}

    for record in history:
        score_data = record.get("score_data") or {}
        breakdown = score_data.get("breakdown", {})
        outcome = record.get("outcome")
        bucket = "win" if outcome in POSITIVE_OUTCOMES else ("loss" if outcome in NEGATIVE_OUTCOMES else None)
        if bucket is None:
            continue
        for dim in dimensions:
            value = breakdown.get(dim, 0)
            dimension_totals[dim][f"{bucket}_sum"] += value
            dimension_totals[dim][f"{bucket}_n"] += 1

    for dim in dimensions:
        stats = dimension_totals[dim]
        if stats["win_n"] == 0 or stats["loss_n"] == 0:
            continue
        win_avg = stats["win_sum"] / stats["win_n"]
        loss_avg = stats["loss_sum"] / stats["loss_n"]
        if win_avg <= 0:
            continue
        separation = (win_avg - loss_avg) / win_avg
        # Bounded nudge: dimensions that separate winners from losers well
        # get weighted up slightly, weak ones get weighted down slightly.
        adjustment = max(-0.1, min(0.1, separation * 0.2))
        weights[dim] = max(0.5, min(1.5, weights[dim] + adjustment))

    save_weights(weights)
    logger.info("Scoring weights updated: %s", weights)
    return weights


def get_performance_context() -> str:
    """Formats a short summary of historical learnings for inclusion in
    Claude API prompts (blind spot analysis, scoring)."""
    history = db.get_scoring_history_with_outcomes()
    autopsies = db.get_all_autopsies()

    if not history and not autopsies:
        return "Historical performance data: none yet. This system has no completed products to learn from."

    lines = ["Historical performance data:"]

    if history:
        wins = [h for h in history if h.get("outcome") in POSITIVE_OUTCOMES]
        losses = [h for h in history if h.get("outcome") in NEGATIVE_OUTCOMES]
        total = len(wins) + len(losses)
        if total:
            hit_rate = round(100 * len(wins) / total, 1)
            lines.append(f"- {len(wins)} of {total} validated products were profitable/scaling ({hit_rate}% hit rate).")

        confidences = [
            (h.get("score_data") or {}).get("blind_spot_confidence")
            for h in history if (h.get("score_data") or {}).get("blind_spot_confidence") is not None
        ]
        low_conf_losses = [
            h for h in losses
            if ((h.get("score_data") or {}).get("blind_spot_confidence") or 1) < 0.7
        ]
        if confidences and low_conf_losses:
            lines.append(
                f"- {len(low_conf_losses)} of {len(losses) or 1} killed products had blind spot "
                f"confidence below 0.7 at validation time."
            )

    if autopsies:
        patterns = [a.get("pattern_identified") for a in autopsies if a.get("pattern_identified")]
        for pattern in patterns[:5]:
            lines.append(f"- {pattern}")

    return "\n".join(lines)
