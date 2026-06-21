"""Brand Engine entry point: initializes storage, loads learnings, starts
the scheduler, and handles operator replies from Discord."""
import re
import sys
import time
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import storage.database as db
from notifications.discord import (
    fetch_new_replies,
    reply_reading_available,
    send_data_entry_prompt,
    send_daily_brief,
    send_message,
    send_startup_notification,
    send_urgent_alert,
    send_weekly_summary,
)
from scoring.learner import get_performance_context
from workflows.ads import prepare_ad_brief
from workflows.autopsy import run_autopsy
from workflows.content import generate_content_brief
from workflows.discovery import run_discovery_workflow
from workflows.launch import launch_store
from workflows.monitoring import run_monitoring_check

logger = config.setup_logging()

_paused = False


def _hh_mm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


# ------------------------------------------------------------- scheduled jobs

def job_discovery() -> None:
    if _paused:
        logger.info("Skipping discovery: system paused")
        return
    try:
        run_discovery_workflow()
    except Exception as exc:  # noqa: BLE001
        logger.error("Discovery job crashed: %s", exc)
        send_urgent_alert("Discovery job crashed", str(exc))


def job_daily_brief() -> None:
    if _paused:
        return
    try:
        send_daily_brief(_build_daily_brief())
    except Exception as exc:  # noqa: BLE001
        logger.error("Daily brief job crashed: %s", exc)


def job_monitoring() -> None:
    if _paused:
        return
    try:
        run_monitoring_check()
    except Exception as exc:  # noqa: BLE001
        logger.error("Monitoring job crashed: %s", exc)
        send_urgent_alert("Monitoring job crashed", str(exc))

    try:
        store_names = [p["name"] for p in db.get_products_by_status("live")] + [
            p["name"] for p in db.get_products_by_status("scaling")
        ]
        if store_names:
            send_data_entry_prompt(store_names, date.today().isoformat())
    except Exception as exc:  # noqa: BLE001
        logger.error("Data entry prompt failed: %s", exc)


def job_content_briefs() -> None:
    if _paused:
        return
    for product in db.get_products_by_status("live"):
        briefs_dir = config.REPORTS_DIR / product["slug"] / "content_briefs"
        if briefs_dir.exists():
            continue
        try:
            generate_content_brief(product["slug"])
        except Exception as exc:  # noqa: BLE001
            logger.error("Content brief job crashed for '%s': %s", product["slug"], exc)


def job_check_replies() -> None:
    if not reply_reading_available():
        return
    try:
        for message in fetch_new_replies():
            _handle_reply(message["content"])
    except Exception as exc:  # noqa: BLE001
        logger.error("Reply check job crashed: %s", exc)


def job_weekly_summary() -> None:
    if _paused:
        return
    try:
        send_weekly_summary(_build_weekly_summary())
    except Exception as exc:  # noqa: BLE001
        logger.error("Weekly summary job crashed: %s", exc)


# ------------------------------------------------------------------ reports

def _build_daily_brief() -> str:
    lines = [f"📊 BRAND ENGINE DAILY BRIEF — {date.today().isoformat()}", "", "ACTIVE STORES"]

    active = db.get_products_by_status("live") + db.get_products_by_status("scaling")
    if not active:
        lines.append("None yet.")
    for product in active:
        perf = db.get_recent_performance(product["id"], days=1)
        if perf:
            entry = perf[0]
            roas = entry.get("roas", 0)
            status = "WARNING" if roas < config.ROAS_CUT_THRESHOLD else "HOLD"
            lines.append(
                f"• {product['name']}: ${entry.get('revenue', 0):.0f} rev / "
                f"${entry.get('ad_spend', 0):.0f} spend / {roas:.1f}x ROAS\n  Status: {status}"
            )
        else:
            lines.append(f"• {product['name']}: no data entered yet")

    lines.append("")
    lines.append("DATA ENTRY NEEDED")
    if active:
        lines.append("Reply: [Store] $spend/$revenue for yesterday")
    else:
        lines.append("None.")

    lines.append("")
    lines.append("PIPELINE")
    pending = db.get_products_by_status("pending_approval")
    if pending:
        for product in pending:
            lines.append(f"• {product['name']} — score {product.get('validation_score', 0)}/100, awaiting approval")
    else:
        lines.append("Empty.")

    lines.append("")
    lines.append("SYSTEM")
    error_logs = [l for l in db.get_recent_system_logs(24) if l.get("level") == "ERROR"]
    lines.append(f"Errors logged last 24h: {len(error_logs)}")

    return "\n".join(lines)


def _build_weekly_summary() -> str:
    week_number = date.today().isocalendar()[1]
    history = db.get_scoring_history_with_outcomes()
    wins = [h for h in history if h.get("outcome") in ("profitable", "scaling")]

    lines = [
        f"📈 WEEK {week_number} SUMMARY", "",
        f"Products tested: {len(history)}",
        f"Winners found: {len(wins)}",
        f"Hit rate: {round(100 * len(wins) / len(history), 1) if history else 0}%",
        "",
        "SYSTEM LEARNINGS",
        get_performance_context(),
        "",
        "NEXT WEEK",
        f"Pipeline: {len(db.get_products_by_status('pending_approval'))} pending approval",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------- reply logic

_REPLY_PATTERNS = [
    (re.compile(r"^APPROVE\s*\$?([\d.]+)\s*/\s*day\s*(.+)?$", re.IGNORECASE), "approve_budget"),
    (re.compile(r"^APPROVE\s*(.+)?$", re.IGNORECASE), "approve"),
    (re.compile(r"^SKIP\s+(.+)$", re.IGNORECASE), "skip_product"),
    (re.compile(r"^SKIP$", re.IGNORECASE), "skip_data_entry"),
    (re.compile(r"^REPORT\s+(.+)$", re.IGNORECASE), "report"),
    (re.compile(r"^KILL\s+(.+)$", re.IGNORECASE), "kill"),
    (re.compile(r"^LIVE\s*(.+)?$", re.IGNORECASE), "live"),
    (re.compile(r"^PAUSE\s+(.+)$", re.IGNORECASE), "pause_product"),
    (re.compile(r"^PAUSE$", re.IGNORECASE), "pause_system"),
    (re.compile(r"^RESUME$", re.IGNORECASE), "resume_system"),
    (re.compile(r"^STATUS$", re.IGNORECASE), "status"),
    (re.compile(r"^(.+?)\s+\$?([\d.]+)\s*/\s*\$?([\d.]+)$", re.IGNORECASE), "performance_entry"),
]


def _resolve_pending_slug() -> str | None:
    pending = db.get_products_by_status("pending_approval")
    return pending[0]["slug"] if len(pending) == 1 else None


def _handle_reply(content: str) -> None:
    content = content.strip()
    if not content:
        return

    for pattern, kind in _REPLY_PATTERNS:
        match = pattern.match(content)
        if not match:
            continue

        try:
            if kind == "approve":
                slug = (match.group(1) or "").strip() or _resolve_pending_slug()
                if not slug:
                    send_message("APPROVE received but I can't tell which product - reply with APPROVE <slug>.")
                    return
                launch_store(slug)
                return

            if kind == "approve_budget":
                budget = float(match.group(1))
                slug = (match.group(2) or "").strip() or _resolve_pending_slug()
                if not slug:
                    send_message("Budget approval received but I can't tell which product.")
                    return
                product = db.get_product_by_slug(slug)
                if product:
                    prepare_ad_brief(slug, {"description": "approved", "save_rate": 0})
                    db.log_system_event("INFO", "main", f"Approved ${budget}/day for {slug}")
                return

            if kind == "skip_product":
                slug = match.group(1).strip()
                db.update_product_status(slug, "skipped")
                send_message(f"Skipped {slug}.")
                return

            if kind == "skip_data_entry":
                _copy_yesterday_performance()
                send_message("Copied yesterday's numbers forward.")
                return

            if kind == "report":
                slug = match.group(1).strip()
                _send_full_report(slug)
                return

            if kind == "kill":
                slug = match.group(1).strip()
                run_autopsy(slug, "killed_no_sales")
                return

            if kind == "live":
                slug = (match.group(1) or "").strip() or _resolve_building_slug()
                if not slug:
                    send_message("LIVE received but I can't tell which store - reply with LIVE <slug>.")
                    return
                db.update_product_status(slug, "live")
                generate_content_brief(slug)
                return

            if kind == "pause_product":
                slug = match.group(1).strip()
                db.update_product_status(slug, "paused")
                send_message(f"Paused {slug}.")
                return

            if kind == "pause_system":
                _set_paused(True)
                send_message("All scheduled workflows paused. Reply RESUME to continue.")
                return

            if kind == "resume_system":
                _set_paused(False)
                send_message("Scheduled workflows resumed.")
                return

            if kind == "status":
                send_message(_build_status_report())
                return

            if kind == "performance_entry":
                store_name, spend, revenue = match.group(1).strip(), float(match.group(2)), float(match.group(3))
                _record_performance(store_name, spend, revenue)
                return
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to handle reply '%s': %s", content, exc)
            send_message(f"Couldn't process that reply ({exc}). Try again or check the logs.")
        return

    logger.info("Unrecognized operator reply: %s", content)


def _resolve_building_slug() -> str | None:
    building = db.get_products_by_status("store_building")
    return building[0]["slug"] if len(building) == 1 else None


def _set_paused(value: bool) -> None:
    global _paused
    _paused = value


def _record_performance(store_name: str, spend: float, revenue: float) -> None:
    candidates = db.get_products_by_status("live") + db.get_products_by_status("scaling")
    match = next((p for p in candidates if store_name.lower() in p["name"].lower()), None)
    if not match:
        send_message(f"Couldn't match '{store_name}' to an active store.")
        return
    roas = round(revenue / spend, 2) if spend else 0.0
    db.log_performance(match["id"], {
        "date": date.today().isoformat(),
        "ad_spend": spend,
        "revenue": revenue,
        "roas": roas,
        "entered_by": "operator",
    })
    send_message(f"Logged {match['name']}: ${spend}/${revenue} ({roas}x ROAS).")


def _copy_yesterday_performance() -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    active = db.get_products_by_status("live") + db.get_products_by_status("scaling")
    for product in active:
        history = db.get_recent_performance(product["id"], days=2)
        prior = next((h for h in history if h["date"] == yesterday), None)
        if prior:
            db.log_performance(product["id"], {
                "date": date.today().isoformat(),
                "ad_spend": prior["ad_spend"],
                "revenue": prior["revenue"],
                "roas": prior["roas"],
                "entered_by": "operator_skip",
            })


def _send_full_report(slug: str) -> None:
    product = db.get_product_by_slug(slug)
    if not product:
        send_message(f"No product found for '{slug}'.")
        return
    blind_spot = product.get("blind_spot_data") or {}
    margin = product.get("margin_data") or {}
    send_message(
        f"📄 FULL REPORT — {product['name']}\n"
        f"Status: {product['status']} | Score: {product.get('validation_score')}/100\n\n"
        f"Blind spot: {blind_spot.get('blind_spot_demographic', 'n/a')}\n"
        f"Angle: {blind_spot.get('purple_ocean_angle', 'n/a')}\n"
        f"Confidence: {blind_spot.get('confidence', 'n/a')}\n\n"
        f"COGS: ${margin.get('cogs', 0)} | Price: ${margin.get('recommended_price', 0)}\n"
        f"Margin: {margin.get('gross_margin_percent', 0)}%\n\n"
        f"Docs: {product.get('foundational_docs_path', 'n/a')}"
    )


def _build_status_report() -> str:
    active = db.get_products_by_status("live") + db.get_products_by_status("scaling")
    pending = db.get_products_by_status("pending_approval")
    building = db.get_products_by_status("store_building")
    lines = [
        "📋 PORTFOLIO STATUS",
        f"Active stores: {len(active)}/{config.MAX_ACTIVE_STORES}",
        f"Pending approval: {len(pending)}",
        f"Building: {len(building)}",
        f"System paused: {_paused}",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------- startup

def _next_run_description() -> str:
    hour, minute = _hh_mm(config.SURVEILLANCE_TIME)
    return f"{hour:02d}:{minute:02d}"


def main() -> None:
    config.validate_required_config()
    db.init_db()
    logger.info("Database ready. Loading scoring weights and performance context...")
    get_performance_context()  # warms/creates weights file if missing

    if not reply_reading_available():
        logger.warning(
            "DISCORD_BOT_TOKEN/DISCORD_CHANNEL_ID not set - operator replies "
            "will not be read automatically. See README."
        )

    scheduler = BackgroundScheduler()

    sh, sm = _hh_mm(config.SURVEILLANCE_TIME)
    scheduler.add_job(job_discovery, CronTrigger(hour=sh, minute=sm), id="surveillance_morning")

    eh, em = _hh_mm(config.EVENING_SWEEP_TIME)
    scheduler.add_job(job_discovery, CronTrigger(hour=eh, minute=em), id="surveillance_evening")

    bh, bm = _hh_mm(config.DAILY_BRIEF_TIME)
    scheduler.add_job(job_daily_brief, CronTrigger(hour=bh, minute=bm), id="daily_brief")

    mh, mm = _hh_mm(config.MONITORING_TIME)
    scheduler.add_job(job_monitoring, CronTrigger(hour=mh, minute=mm), id="monitoring")

    ch, cm = _hh_mm(config.CONTENT_BRIEF_TIME)
    scheduler.add_job(job_content_briefs, CronTrigger(hour=ch, minute=cm), id="content_briefs")

    scheduler.add_job(job_check_replies, "interval", minutes=15, id="check_replies")
    scheduler.add_job(job_weekly_summary, CronTrigger(day_of_week="sun", hour=20, minute=0), id="weekly_summary")

    scheduler.start()
    logger.info("Scheduler started.")
    send_startup_notification(_next_run_description())

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down Brand Engine...")
        scheduler.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
