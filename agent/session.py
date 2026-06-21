"""Persists browser sessions (cookies) across runs so the operator does not
have to manually log into Facebook / TikTok every surveillance cycle.

The operator is responsible for completing the first manual login in Chrome.
This module only reads cookies Chrome already holds and reuses them; it does
not attempt to bypass any login or 2FA challenge.
"""
import json
import logging
import time
from pathlib import Path

import browser_cookie3
import requests

import config
from notifications.discord import send_urgent_alert

logger = logging.getLogger("brand_engine.agent.session")

PLATFORM_DOMAINS = {
    "facebook": ".facebook.com",
    "tiktok": ".tiktok.com",
}

PLATFORM_CHECK_URLS = {
    "facebook": "https://www.facebook.com/ads/library/",
    "tiktok": "https://shop.tiktok.com/",
}


def _session_path(platform: str) -> Path:
    return config.SESSIONS_DIR / f"{platform}_session.json"


def save_session(platform: str) -> bool:
    """Reads current Chrome cookies for the platform's domain and saves them."""
    domain = PLATFORM_DOMAINS.get(platform)
    if not domain:
        logger.error("Unknown platform for session save: %s", platform)
        return False
    try:
        cookie_jar = browser_cookie3.chrome(domain_name=domain)
        cookies = [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "expires": c.expires,
            }
            for c in cookie_jar
        ]
        if not cookies:
            logger.warning("No cookies found for platform %s; nothing saved", platform)
            return False
        payload = {"platform": platform, "saved_at": time.time(), "cookies": cookies}
        _session_path(platform).write_text(json.dumps(payload, indent=2))
        logger.info("Saved %s cookies for platform %s", len(cookies), platform)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save session for %s: %s", platform, exc)
        return False


def load_session(platform: str) -> list[dict]:
    """Returns the saved cookie list for a platform, or [] if none saved."""
    path = _session_path(platform)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
        return payload.get("cookies", [])
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load session for %s: %s", platform, exc)
        return []


def session_valid(platform: str) -> bool:
    """Best-effort check that the saved session still authenticates.

    This does not guarantee validity (computer-use task still needs to
    visually confirm a login wall does not appear) but filters out the
    obvious case of no/expired session before spending an agent run on it.
    """
    cookies = load_session(platform)
    if not cookies:
        return False
    url = PLATFORM_CHECK_URLS.get(platform)
    if not url:
        return True
    try:
        jar = requests.cookies.RequestsCookieJar()
        for cookie in cookies:
            jar.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])
        response = requests.get(url, cookies=jar, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        return response.status_code < 400
    except Exception as exc:  # noqa: BLE001
        logger.warning("Session validity check failed for %s: %s", platform, exc)
        return False


def clear_session(platform: str) -> None:
    path = _session_path(platform)
    if path.exists():
        path.unlink()
        logger.info("Cleared session for platform %s", platform)


def require_valid_session(platform: str) -> bool:
    """Convenience guard for workflows: alerts and returns False if no valid session."""
    if session_valid(platform):
        return True
    clear_session(platform)
    send_urgent_alert(
        f"{platform.title()} session expired or missing",
        f"Brand Engine needs you to manually log into {platform.title()} in Chrome. "
        f"Once logged in, the system will capture the session automatically on the "
        f"next run. Pausing {platform.title()} tasks for this cycle.",
    )
    logger.warning("No valid session for %s; pausing related tasks", platform)
    return False
