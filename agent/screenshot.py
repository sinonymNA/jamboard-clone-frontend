"""Screenshot capture and coordinate scaling for Claude Computer Use.

Claude sees a downscaled image (SCALED_WIDTH x SCALED_HEIGHT). Every click
coordinate Claude returns is in that scaled space and must be converted back
to real screen pixels before pyautogui executes it.
"""
import logging
import time
from io import BytesIO

import pyautogui
from PIL import Image

import config

logger = logging.getLogger("brand_engine.agent.screenshot")

# Anthropic recommends capping the long edge around 1280px for computer use
# accuracy/cost. We scale down from the real screen and scale clicks back up.
MAX_DIMENSION = 1280

_scale_ratio = min(
    MAX_DIMENSION / config.SCREEN_WIDTH,
    MAX_DIMENSION / config.SCREEN_HEIGHT,
    1.0,
)
SCALED_WIDTH = int(config.SCREEN_WIDTH * _scale_ratio)
SCALED_HEIGHT = int(config.SCREEN_HEIGHT * _scale_ratio)

MAX_RETRIES = 3


def take_screenshot() -> bytes:
    """Captures the full screen, scales it down, returns PNG bytes.

    Retries up to MAX_RETRIES times on failure, then raises.
    """
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = pyautogui.screenshot()
            resized = raw.resize((SCALED_WIDTH, SCALED_HEIGHT), Image.LANCZOS)
            buffer = BytesIO()
            resized.save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception as exc:  # noqa: BLE001 - screenshot backends raise varied errors
            last_error = exc
            logger.warning(
                "Screenshot attempt %s/%s failed: %s", attempt, MAX_RETRIES, exc
            )
            time.sleep(0.5)
    logger.error("Screenshot capture failed after %s attempts: %s", MAX_RETRIES, last_error)
    raise RuntimeError(f"Could not capture screenshot: {last_error}")


def scale_to_real(x: int, y: int) -> tuple[int, int]:
    """Converts a coordinate from the scaled screenshot space to real screen pixels."""
    real_x = int(x / _scale_ratio)
    real_y = int(y / _scale_ratio)
    real_x = max(0, min(real_x, config.SCREEN_WIDTH - 1))
    real_y = max(0, min(real_y, config.SCREEN_HEIGHT - 1))
    return real_x, real_y


def real_to_scaled(x: int, y: int) -> tuple[int, int]:
    """Converts a real screen coordinate into the scaled screenshot space."""
    return int(x * _scale_ratio), int(y * _scale_ratio)
