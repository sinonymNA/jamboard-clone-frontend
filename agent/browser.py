"""Low-level browser control helpers used by surveillance/analysis workflows."""
import base64
import logging
import subprocess
import time

import anthropic
import pyautogui

import config
from agent.screenshot import take_screenshot

logger = logging.getLogger("brand_engine.agent.browser")

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def open_url(url: str) -> bool:
    """Opens Chrome to the given URL. Reuses an existing window via OS launch."""
    try:
        subprocess.Popen(["cmd", "/c", "start", "chrome", url], shell=False)
        time.sleep(2)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("chrome launch via 'start chrome' failed (%s), trying chrome.exe", exc)
        try:
            subprocess.Popen(["chrome", url])
            time.sleep(2)
            return True
        except Exception as exc2:  # noqa: BLE001
            logger.error("Failed to open URL %s: %s", url, exc2)
            return False


def wait_for_load(timeout: int = 10) -> None:
    """Waits for the page to stabilize. Computer-use screenshots double as the
    real readiness signal, so this is a simple bounded sleep."""
    time.sleep(min(timeout, 30))


def close_browser() -> None:
    try:
        pyautogui.hotkey("alt", "f4")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to close browser window: %s", exc)


def _vision_call(prompt: str, max_tokens: int = 1024) -> str:
    screenshot_bytes = take_screenshot()
    image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    response = _client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


def extract_text() -> str:
    """Screenshots the current page and asks Claude to transcribe visible text."""
    try:
        return _vision_call(
            "Transcribe all visible text on this screen, top to bottom, left to "
            "right. Return plain text only, no commentary."
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("extract_text failed: %s", exc)
        return ""


def extract_number(label: str) -> float:
    """Finds a number associated with a given label on screen and returns it."""
    try:
        result = _vision_call(
            f"Look at this screen and find the numeric value associated with "
            f"'{label}'. Return ONLY the number (digits, optional decimal point, "
            f"no commas, no currency symbols, no units, no other text). If you "
            f"cannot find it, return exactly 0."
        )
        cleaned = "".join(ch for ch in result if ch.isdigit() or ch == ".")
        return float(cleaned) if cleaned else 0.0
    except Exception as exc:  # noqa: BLE001
        logger.error("extract_number failed for label '%s': %s", label, exc)
        return 0.0


def dismiss_overlays() -> None:
    """Best-effort dismissal of cookie banners / popups via common keys before
    the main computer-use task begins. The agent loop also handles these
    explicitly per the standard task prompt, this is just a fast first pass."""
    try:
        pyautogui.press("esc")
        time.sleep(0.3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dismiss_overlays failed: %s", exc)
