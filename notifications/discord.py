"""All Discord I/O. Sending uses the webhook URL. Reading replies requires an
optional bot token + channel id (a plain webhook cannot read channel
messages) - see README for setup. If those aren't configured, reply reading
is skipped gracefully and outbound notifications still work.
"""
import json
import logging
import time

import requests

import config

logger = logging.getLogger("brand_engine.notifications.discord")

_LAST_SEEN_PATH = config.DATA_DIR / "discord_last_seen.json"

DISCORD_MESSAGE_LIMIT = 1900  # leave headroom under the 2000 char hard limit


def _chunk(text: str) -> list[str]:
    if len(text) <= DISCORD_MESSAGE_LIMIT:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        chunks.append(remaining[:DISCORD_MESSAGE_LIMIT])
        remaining = remaining[DISCORD_MESSAGE_LIMIT:]
    return chunks


def send_message(content: str) -> bool:
    if not config.DISCORD_WEBHOOK_URL:
        logger.error("DISCORD_WEBHOOK_URL not configured, cannot send: %s", content[:80])
        return False
    ok = True
    for chunk in _chunk(content):
        try:
            response = requests.post(
                config.DISCORD_WEBHOOK_URL, json={"content": chunk}, timeout=15
            )
            if response.status_code >= 300:
                logger.error("Discord webhook returned %s: %s", response.status_code, response.text[:200])
                ok = False
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send Discord message: %s", exc)
            ok = False
        time.sleep(0.3)
    return ok


def send_urgent_alert(reason: str, explanation: str) -> bool:
    return send_message(f"🚨 URGENT — {reason}\n{explanation}")


def send_discovery_alert(formatted_message: str) -> bool:
    return send_message(formatted_message)


def send_daily_brief(brief_text: str) -> bool:
    return send_message(brief_text)


def send_weekly_summary(summary_text: str) -> bool:
    return send_message(summary_text)


def send_startup_notification(next_surveillance_time: str) -> bool:
    return send_message(
        f"✅ Brand Engine online. Next surveillance: {next_surveillance_time}"
    )


def send_data_entry_prompt(store_names: list[str], date_str: str) -> bool:
    lines = [f"📊 DAILY DATA ENTRY — {date_str}", "", "Reply with today's results for each store:"]
    for name in store_names:
        lines.append(f"{name}: $XXX spend / $XXX revenue")
    lines.append("")
    lines.append("Or reply SKIP to use yesterday's numbers.")
    return send_message("\n".join(lines))


def reply_reading_available() -> bool:
    return bool(config.DISCORD_BOT_TOKEN and config.DISCORD_CHANNEL_ID)


def _load_last_seen() -> str | None:
    if not _LAST_SEEN_PATH.exists():
        return None
    try:
        return json.loads(_LAST_SEEN_PATH.read_text()).get("last_message_id")
    except Exception:  # noqa: BLE001
        return None


def _save_last_seen(message_id: str) -> None:
    try:
        _LAST_SEEN_PATH.write_text(json.dumps({"last_message_id": message_id}))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist last_seen discord message id: %s", exc)


def fetch_new_replies() -> list[dict]:
    """Returns new operator messages since the last poll, oldest first.

    Each item: {"id": str, "content": str, "author": str, "timestamp": str}
    Requires DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID. Returns [] if not
    configured or on any error (never raises).
    """
    if not reply_reading_available():
        logger.debug("Discord reply reading not configured, skipping poll")
        return []

    last_seen = _load_last_seen()
    url = f"https://discord.com/api/v10/channels/{config.DISCORD_CHANNEL_ID}/messages"
    params = {"limit": 50}
    if last_seen:
        params["after"] = last_seen

    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bot {config.DISCORD_BOT_TOKEN}"},
            params=params,
            timeout=15,
        )
        if response.status_code != 200:
            logger.error("Discord message fetch failed: %s %s", response.status_code, response.text[:200])
            return []
        messages = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch Discord replies: %s", exc)
        return []

    if not messages:
        return []

    # Discord returns newest-first; reverse for chronological processing.
    messages = list(reversed(messages))
    bot_authored = [m for m in messages if not m.get("author", {}).get("bot")]
    _save_last_seen(messages[-1]["id"])

    return [
        {
            "id": m["id"],
            "content": m.get("content", ""),
            "author": m.get("author", {}).get("username", "unknown"),
            "timestamp": m.get("timestamp", ""),
        }
        for m in bot_authored
    ]
