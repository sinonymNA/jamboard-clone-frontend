"""Executes computer-use tool actions via pyautogui.

Every action carrying a coordinate is passed through
screenshot.scale_to_real() before pyautogui touches the screen. No exceptions.
"""
import logging
import time

import pyautogui

from agent.screenshot import scale_to_real

logger = logging.getLogger("brand_engine.agent.actions")

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


class ActionError(Exception):
    """Raised when an action cannot be executed."""


def execute_action(action: dict) -> str:
    """Executes a single computer-use action dict.

    Returns a short string describing what happened, for logging / tool_result.
    Raises ActionError for unrecoverable issues (caller decides whether to
    request a fresh screenshot and retry).
    """
    action_type = action.get("action")
    try:
        if action_type == "screenshot":
            return "screenshot_requested"

        if action_type == "left_click":
            x, y = _coords(action)
            pyautogui.click(x, y)
            return f"left_click at ({x},{y})"

        if action_type == "right_click":
            x, y = _coords(action)
            pyautogui.rightClick(x, y)
            return f"right_click at ({x},{y})"

        if action_type == "double_click":
            x, y = _coords(action)
            pyautogui.doubleClick(x, y)
            return f"double_click at ({x},{y})"

        if action_type == "middle_click":
            x, y = _coords(action)
            pyautogui.middleClick(x, y)
            return f"middle_click at ({x},{y})"

        if action_type == "mouse_move":
            x, y = _coords(action)
            pyautogui.moveTo(x, y)
            return f"mouse_move to ({x},{y})"

        if action_type == "left_click_drag":
            start = action.get("start_coordinate") or action.get("coordinate")
            end = action.get("coordinate")
            sx, sy = scale_to_real(*start)
            ex, ey = scale_to_real(*end)
            pyautogui.moveTo(sx, sy)
            pyautogui.dragTo(ex, ey, duration=0.3, button="left")
            return f"drag from ({sx},{sy}) to ({ex},{ey})"

        if action_type == "scroll":
            x, y = _coords(action)
            direction = action.get("scroll_direction", "down")
            amount = action.get("scroll_amount", 3)
            pyautogui.moveTo(x, y)
            clicks = amount if direction in ("up", "left") else -amount
            if direction in ("up", "down"):
                pyautogui.scroll(clicks)
            else:
                pyautogui.hscroll(clicks)
            return f"scroll {direction} x{amount} at ({x},{y})"

        if action_type == "type":
            text = action.get("text", "")
            pyautogui.typewrite(text, interval=0.02)
            return f"typed {len(text)} chars"

        if action_type == "key":
            keys = action.get("text", "")
            _press_key_combo(keys)
            return f"key press: {keys}"

        if action_type == "hold_key":
            keys = action.get("text", "")
            duration = action.get("duration", 1)
            pyautogui.keyDown(keys)
            time.sleep(duration)
            pyautogui.keyUp(keys)
            return f"held key {keys} for {duration}s"

        if action_type == "wait":
            duration = action.get("duration", 1)
            time.sleep(min(duration, 10))
            return f"waited {duration}s"

        if action_type == "cursor_position":
            x, y = pyautogui.position()
            return f"cursor_position ({x},{y})"

        logger.warning("Unknown action type received: %s", action_type)
        raise ActionError(f"Unknown action type: {action_type}")

    except ActionError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to execute action %s: %s", action, exc)
        raise ActionError(f"Failed to execute {action_type}: {exc}") from exc


def _coords(action: dict) -> tuple[int, int]:
    coordinate = action.get("coordinate")
    if not coordinate or len(coordinate) != 2:
        raise ActionError(f"Action {action.get('action')} missing valid coordinate")
    return scale_to_real(coordinate[0], coordinate[1])


def _press_key_combo(keys: str) -> None:
    parts = [part.strip().lower() for part in keys.split("+") if part.strip()]
    if not parts:
        return
    if len(parts) == 1:
        pyautogui.press(parts[0])
    else:
        pyautogui.hotkey(*parts)
