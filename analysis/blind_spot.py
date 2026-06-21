"""Identifies the underserved demographic ('blind spot') for a proven
product and generates the four foundational marketing docs for it."""
import logging

import config
from agent.llm import complete
from scoring.learner import get_performance_context
from utils import parse_json_response, slugify

logger = logging.getLogger("brand_engine.analysis.blind_spot")

BLIND_SPOT_SYSTEM_PROMPT = (
    "You are an expert ecommerce market analyst specializing in demographic "
    "segmentation and purple ocean positioning. You identify underserved "
    "customer segments within proven markets."
)


def find_blind_spot(product_data: dict) -> dict:
    """Returns the blind-spot demographic analysis for a product as a dict."""
    performance_context = get_performance_context()

    user_prompt = (
        f"{performance_context}\n\n"
        f"Product description: {product_data.get('description', product_data.get('name', ''))}\n"
        f"Current advertiser's apparent target demographic: "
        f"{product_data.get('current_target_demographic', 'unknown, infer from ad copy/visuals below')}\n"
        f"Category: {product_data.get('category', 'unknown')}\n"
        f"Price point: {product_data.get('price_point', 'unknown')}\n"
        f"Ad copy / visual notes: {product_data.get('ad_copy', '')}\n\n"
        "Identify an underserved demographic segment for this product that "
        "the current advertiser is NOT targeting. Respond with ONLY a JSON "
        "object with exactly these keys: current_target (string), "
        "blind_spot_demographic (string), why_underserved (string), "
        "purple_ocean_angle (string), positioning_statement (string), "
        "estimated_demographic_size (string), confidence (float 0-1), "
        "supporting_evidence (string), visual_product (boolean - is this "
        "product visually interesting/easy to film), problem_relatable "
        "(boolean - is the problem it solves highly relatable), "
        "tiktok_angle_obvious (boolean - is there an obvious short-form "
        "video angle)."
    )

    raw = complete(BLIND_SPOT_SYSTEM_PROMPT, user_prompt, max_tokens=1500)
    data = parse_json_response(raw)

    if not data:
        logger.error("Blind spot analysis failed for product '%s'", product_data.get("name"))
        return {
            "current_target": "unknown",
            "blind_spot_demographic": "unknown",
            "why_underserved": "",
            "purple_ocean_angle": "",
            "positioning_statement": "",
            "estimated_demographic_size": "unknown",
            "confidence": 0.0,
            "supporting_evidence": "",
            "visual_product": False,
            "problem_relatable": False,
            "tiktok_angle_obvious": False,
        }

    data["confidence"] = float(data.get("confidence", 0) or 0)
    logger.info(
        "Blind spot found for '%s': %s (confidence=%.2f)",
        product_data.get("name"), data.get("blind_spot_demographic"), data["confidence"],
    )
    return data


def generate_foundational_docs(product_data: dict, blind_spot_data: dict) -> str:
    """Generates the four foundational docs and saves them as markdown.
    Returns the path to the foundational_docs directory."""
    slug = product_data.get("slug") or slugify(product_data.get("name", "product"))
    docs_dir = config.REPORTS_DIR / slug / "foundational_docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    context = (
        f"Product: {product_data.get('name')}\n"
        f"Category: {product_data.get('category', 'unknown')}\n"
        f"Blind spot demographic: {blind_spot_data.get('blind_spot_demographic')}\n"
        f"Purple ocean angle: {blind_spot_data.get('purple_ocean_angle')}\n"
        f"Positioning statement: {blind_spot_data.get('positioning_statement')}\n"
        f"Supporting evidence: {blind_spot_data.get('supporting_evidence')}\n"
    )

    docs = {
        "deep_research.md": (
            "You write comprehensive ecommerce market research documents.",
            f"{context}\n\nWrite a comprehensive deep research document on the "
            "blind spot demographic identified above. Cover: pain points, "
            "buying triggers, emotional drivers, the specific language they "
            "use to describe their problem, where they spend time online, "
            "and what makes them buy vs. not buy. Format as markdown with "
            "clear headers.",
        ),
        "avatar.md": (
            "You write hyper-specific customer avatar documents for direct response marketing.",
            f"{context}\n\nWrite a hyper-specific customer avatar for the "
            "blind spot demographic. Give them a name, age, occupation, a "
            "description of their daily life, specific frustrations related "
            "to this product category, likely objections to buying, and "
            "core desires. Format as markdown.",
        ),
        "offer.md": (
            "You write direct-response offer and positioning documents.",
            f"{context}\n\nWrite the offer document: the positioning "
            "statement, value proposition, a price anchoring strategy, and "
            "the purple ocean angle articulated as a single punchy brand "
            "statement. Format as markdown.",
        ),
        "necessary_beliefs.md": (
            "You write belief-shift maps for direct response marketing campaigns.",
            f"{context}\n\nWrite the necessary beliefs document: the beliefs "
            "the customer must hold to buy, the false beliefs they likely "
            "hold now, how to shift each false belief to a true one, the key "
            "messaging angles that accomplish this, and what proof elements "
            "(testimonials, demos, stats) are needed. Format as markdown.",
        ),
    }

    for filename, (system_prompt, user_prompt) in docs.items():
        content = complete(system_prompt, user_prompt, max_tokens=2000)
        if not content:
            content = f"# Generation failed\n\nCould not generate this document for {product_data.get('name')}."
            logger.error("Failed to generate %s for '%s'", filename, product_data.get("name"))
        (docs_dir / filename).write_text(content, encoding="utf-8")

    logger.info("Foundational docs saved to %s", docs_dir)
    return str(docs_dir)
