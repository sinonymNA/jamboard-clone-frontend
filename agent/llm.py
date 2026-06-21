"""Plain (non computer-use) Claude API calls shared by analysis/workflow
modules that only need text reasoning, not browser control."""
import logging
import time

import anthropic

import config

logger = logging.getLogger("brand_engine.agent.llm")

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def complete(system: str, user: str, max_tokens: int = 2048) -> str:
    """Single-turn text completion with rate-limit backoff. Returns '' on
    unrecoverable failure rather than raising, so callers can degrade
    gracefully (skip a product, log, move on)."""
    delay = 5
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            response = _client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(block.text for block in response.content if block.type == "text").strip()
        except anthropic.RateLimitError as exc:
            logger.warning("Rate limited (attempt %s/%s), backing off %ss: %s", attempt, max_attempts, delay, exc)
            time.sleep(delay)
            delay *= 2
        except anthropic.APIError as exc:
            logger.error("Anthropic API error (attempt %s/%s): %s", attempt, max_attempts, exc)
            time.sleep(delay)
            delay *= 2
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error calling Claude API: %s", exc)
            return ""
    logger.error("Claude API call failed after %s attempts", max_attempts)
    return ""
