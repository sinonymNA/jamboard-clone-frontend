"""Generates the post-launch content brief: TikTok concepts, image ad
concepts, organic captions, and a UGC brief for an outside creator."""
import json
import logging
from pathlib import Path

import config
import storage.database as db
from agent.llm import complete
from notifications.discord import send_message
from utils import parse_json_response

logger = logging.getLogger("brand_engine.workflows.content")

CONTENT_SYSTEM_PROMPT = (
    "You are a short-form content strategist for direct-to-consumer brands. "
    "You write hooks, scripts, and creator briefs grounded in a specific "
    "customer avatar, not generic content advice."
)


def _foundational_context(product: dict) -> str:
    docs_path = product.get("foundational_docs_path")
    blind_spot = product.get("blind_spot_data") or {}
    context = (
        f"Product: {product['name']}\n"
        f"Blind spot demographic: {blind_spot.get('blind_spot_demographic', '')}\n"
        f"Purple ocean angle: {blind_spot.get('purple_ocean_angle', '')}\n"
        f"Positioning: {blind_spot.get('positioning_statement', '')}\n"
    )
    if docs_path:
        try:
            avatar_file = Path(docs_path) / "avatar.md"
            if avatar_file.exists():
                context += f"\nAvatar:\n{avatar_file.read_text(encoding='utf-8')[:2000]}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read avatar doc: %s", exc)
    return context


def generate_content_brief(product_slug: str) -> dict:
    product = db.get_product_by_slug(product_slug)
    if not product:
        logger.error("generate_content_brief called for unknown slug '%s'", product_slug)
        return {"success": False, "reason": "unknown_product"}

    context = _foundational_context(product)
    briefs_dir = config.REPORTS_DIR / product_slug / "content_briefs"
    briefs_dir.mkdir(parents=True, exist_ok=True)

    sections = {
        "tiktok_concepts.json": (
            f"{context}\n\nWrite 5 TikTok video concepts. Respond with ONLY a "
            "JSON array of 5 objects, each with keys: hook (exact words for "
            "first 3 seconds), body (what happens in 15-30 seconds), cta "
            "(exact words for last 3 seconds), visual_description (what to "
            "film), why_this_works (the psychological mechanism)."
        ),
        "image_ad_concepts.json": (
            f"{context}\n\nWrite 3 image ad concepts. Respond with ONLY a "
            "JSON array of 3 objects, each with keys: headline, "
            "visual_description (exact scene to shoot/design), body_copy "
            "(50 words max), cta_button_text."
        ),
        "organic_captions.json": (
            f"{context}\n\nWrite 10 organic caption variations for TikTok and "
            "Instagram, mixing problem-aware, solution-aware, and social "
            "proof angles. Respond with ONLY a JSON array of 10 strings."
        ),
        "ugc_brief.json": (
            f"{context}\n\nWrite a one-page UGC creator brief formatted for "
            "sending to a creator on Billo or Fiverr. Respond with ONLY a "
            "JSON object with keys: product_description, target_demographic, "
            "tone_and_style, talking_points (array of strings), "
            "do_not_say (array of strings), example_hooks (array of strings)."
        ),
    }

    generated = {}
    for filename, prompt in sections.items():
        raw = complete(CONTENT_SYSTEM_PROMPT, prompt, max_tokens=2500)
        parsed = parse_json_response(raw)
        if not parsed:
            logger.error("Content section '%s' failed to generate for '%s'", filename, product_slug)
            parsed = {"error": "generation_failed"}
        (briefs_dir / filename).write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        generated[filename] = parsed

    send_message(
        f"🎬 CONTENT BRIEF READY — {product['name']}\n\n"
        f"5 TikTok concepts, 3 image ad concepts, 10 organic captions, and a "
        f"UGC creator brief are saved at:\n{briefs_dir}\n\n"
        f"Send ugc_brief.json to a Billo or Fiverr creator to get footage "
        f"started (24-48hr typical turnaround)."
    )

    logger.info("Content brief generated for '%s'", product_slug)
    return {"success": True, "briefs_path": str(briefs_dir), "content": generated}
