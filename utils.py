"""Small shared helpers used across modules."""
import json
import logging
import re

logger = logging.getLogger("brand_engine.utils")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_response(text: str) -> dict:
    """Extracts and parses a JSON object from a Claude text response.

    Handles responses wrapped in markdown code fences or with leading/
    trailing prose. Returns {} on failure rather than raising, since callers
    should treat malformed model output as a soft failure, not a crash.
    """
    if not text:
        return {}

    candidates = []
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        candidates.append(fence_match.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start:end + 1])

    candidates.append(text)

    for candidate in candidates:
        try:
            return json.loads(candidate.strip())
        except (json.JSONDecodeError, ValueError):
            continue

    logger.warning("Failed to parse JSON from model response: %s", text[:200])
    return {}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "product"
