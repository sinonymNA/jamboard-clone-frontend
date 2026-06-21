"""Full Claude Computer Use agent loop.

This is the single entry point every surveillance/analysis module uses to
drive the browser. Callers supply a task prompt describing what to extract
or do; this module handles the screenshot -> model -> action -> screenshot
cycle until Claude signals it is done (no more tool_use) or
MAX_AGENT_ITERATIONS is reached.
"""
import base64
import logging
import time

import anthropic

import config
from agent.actions import ActionError, execute_action
from agent.screenshot import SCALED_HEIGHT, SCALED_WIDTH, take_screenshot
from notifications.discord import send_urgent_alert

logger = logging.getLogger("brand_engine.agent.computer_use")

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

STANDARD_TASK_SUFFIX = (
    "\n\nAfter each step take a screenshot and verify you are on the correct "
    "page before continuing. If you encounter a popup, cookie banner, or "
    "login wall, dismiss it first before proceeding with the main task. "
    "If you encounter a CAPTCHA, state the word CAPTCHA clearly in your "
    "response and stop taking actions. If you encounter a two-factor "
    "authentication (2FA) prompt, state the words 2FA WALL clearly in your "
    "response and stop taking actions. When you have finished the task, "
    "summarize the extracted data as JSON in your final text response and "
    "do not call any further tools."
)

COMPUTER_TOOL = {
    "type": "computer_20251124",
    "name": "computer",
    "display_width_px": SCALED_WIDTH,
    "display_height_px": SCALED_HEIGHT,
    "display_number": 1,
    "enable_zoom": True,
}


class AgentHalted(Exception):
    """Raised when the agent loop must stop early (CAPTCHA, 2FA, fatal error)."""

    def __init__(self, reason: str, transcript: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.transcript = transcript


def _image_block() -> dict:
    screenshot_bytes = take_screenshot()
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(screenshot_bytes).decode("utf-8"),
        },
    }


def _call_with_backoff(messages: list, system: str):
    delay = 5
    max_attempts = 5
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _client.beta.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=4096,
                system=system,
                messages=messages,
                tools=[COMPUTER_TOOL],
                thinking={"type": "enabled", "budget_tokens": 2048},
                betas=[config.COMPUTER_USE_BETA_HEADER],
            )
        except anthropic.RateLimitError as exc:
            last_exc = exc
            logger.warning(
                "Rate limited on attempt %s/%s, backing off %ss", attempt, max_attempts, delay
            )
            time.sleep(delay)
            delay *= 2
        except anthropic.APIError as exc:
            last_exc = exc
            logger.error("Anthropic API error on attempt %s/%s: %s", attempt, max_attempts, exc)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"Claude API call failed after {max_attempts} attempts: {last_exc}")


def run_agent_task(
    task_description: str,
    max_iterations: int | None = None,
) -> dict:
    """Runs the full agent loop for one task.

    Returns:
        {
            "success": bool,
            "final_text": str,
            "iterations": int,
            "halted_reason": str | None,
        }
    """
    max_iterations = max_iterations or config.MAX_AGENT_ITERATIONS
    system = (
        "You are an autonomous browser operator completing a single, "
        "well-defined data-extraction or navigation task. Be precise with "
        "clicks. Verify page state via screenshots before acting."
    )
    full_task = task_description + STANDARD_TASK_SUFFIX

    messages: list = [{
        "role": "user",
        "content": [_image_block(), {"type": "text", "text": full_task}],
    }]

    final_text = ""

    for iteration in range(1, max_iterations + 1):
        try:
            response = _call_with_backoff(messages, system)
        except Exception as exc:  # noqa: BLE001
            logger.error("Agent loop fatal API failure: %s", exc)
            send_urgent_alert(
                "Computer Use task failed",
                f"Task aborted after API failure: {exc}",
            )
            return {"success": False, "final_text": final_text, "iterations": iteration, "halted_reason": "api_failure"}

        assistant_content = response.content
        text_blocks = [b.text for b in assistant_content if b.type == "text"]
        combined_text = "\n".join(text_blocks)
        if combined_text:
            final_text = combined_text

        if "CAPTCHA" in combined_text.upper():
            logger.error("CAPTCHA detected during task: %s", task_description[:120])
            send_urgent_alert(
                "CAPTCHA detected",
                f"Brand Engine hit a CAPTCHA during: {task_description[:200]}. "
                f"Trying alternative source if available; this run is skipped.",
            )
            return {"success": False, "final_text": final_text, "iterations": iteration, "halted_reason": "captcha"}

        if "2FA WALL" in combined_text.upper():
            logger.error("2FA wall detected during task: %s", task_description[:120])
            send_urgent_alert(
                "2FA wall detected",
                f"Brand Engine needs manual 2FA completion for: "
                f"{task_description[:200]}. Pausing this task.",
            )
            return {"success": False, "final_text": final_text, "iterations": iteration, "halted_reason": "2fa_wall"}

        tool_uses = [b for b in assistant_content if b.type == "tool_use"]

        messages.append({"role": "assistant", "content": assistant_content})

        if not tool_uses or response.stop_reason != "tool_use":
            logger.info("Agent task completed in %s iterations", iteration)
            return {"success": True, "final_text": final_text, "iterations": iteration, "halted_reason": None}

        tool_results = []
        for tool_use in tool_uses:
            action = tool_use.input
            try:
                result_text = execute_action(action)
                time.sleep(0.5)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": [_image_block(), {"type": "text", "text": result_text}],
                })
            except ActionError as exc:
                logger.warning("Action error, requesting fresh screenshot: %s", exc)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": [_image_block(), {"type": "text", "text": f"Error: {exc}. Here is the current screenshot."}],
                    "is_error": True,
                })

        messages.append({"role": "user", "content": tool_results})

    logger.warning("Agent task hit max_iterations (%s) without completing", max_iterations)
    return {
        "success": False,
        "final_text": final_text,
        "iterations": max_iterations,
        "halted_reason": "max_iterations",
    }
