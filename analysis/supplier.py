"""Finds a supplier and COGS estimate for a discovered product via
computer-use browsing of CJDropshipping, falling back to AliExpress."""
import logging

from agent.computer_use import run_agent_task
from utils import parse_json_response

logger = logging.getLogger("brand_engine.analysis.supplier")

CJ_TASK_TEMPLATE = (
    "Navigate to https://cjdropshipping.com and search for '{product_name}'. "
    "Find the listing with the lowest total price for a reasonable minimum "
    "order quantity (1-10 units). Open that listing and extract: the unit "
    "product price in USD, the shipping cost to the United States in USD, "
    "and the estimated delivery time in days. Report your findings as a "
    "single JSON object with exactly these keys: product_price (number), "
    "shipping_cost (number), delivery_days (integer), source_url (string, "
    "the listing URL), confidence (string: 'high', 'medium', or 'low' based "
    "on how clearly the listing matched the product)."
)

ALIEXPRESS_TASK_TEMPLATE = (
    "Navigate to https://aliexpress.com and search for '{product_name}'. "
    "Find the listing with the lowest total price for a reasonable minimum "
    "order quantity (1-10 units). Open that listing and extract: the unit "
    "product price in USD, the shipping cost to the United States in USD, "
    "and the estimated delivery time in days. Report your findings as a "
    "single JSON object with exactly these keys: product_price (number), "
    "shipping_cost (number), delivery_days (integer), source_url (string, "
    "the listing URL), confidence (string: 'high', 'medium', or 'low' based "
    "on how clearly the listing matched the product)."
)


def _run_supplier_task(task_prompt: str, supplier_name: str) -> dict | None:
    result = run_agent_task(task_prompt)
    if not result["success"]:
        logger.warning(
            "%s supplier search did not complete cleanly (%s)",
            supplier_name, result.get("halted_reason"),
        )
        if result.get("halted_reason") in ("captcha", "2fa_wall"):
            return None

    data = parse_json_response(result.get("final_text", ""))
    if not data or "product_price" not in data:
        logger.warning("%s supplier search returned no usable data", supplier_name)
        return None

    data["supplier"] = supplier_name
    return data


def find_supplier(product_name: str) -> dict:
    """Returns supplier/COGS data, trying CJDropshipping first and falling
    back to AliExpress on CAPTCHA, 2FA, or no usable result."""
    data = _run_supplier_task(CJ_TASK_TEMPLATE.format(product_name=product_name), "CJDropshipping")

    if not data:
        logger.info("Falling back to AliExpress for '%s'", product_name)
        data = _run_supplier_task(
            ALIEXPRESS_TASK_TEMPLATE.format(product_name=product_name), "AliExpress"
        )

    if not data:
        logger.error("No supplier found for '%s' on any source", product_name)
        return {
            "supplier": None,
            "product_price": 0.0,
            "shipping_cost": 0.0,
            "total_cogs": 0.0,
            "delivery_days": 0,
            "source_url": "",
            "confidence": "low",
        }

    product_price = float(data.get("product_price", 0) or 0)
    shipping_cost = float(data.get("shipping_cost", 0) or 0)

    return {
        "supplier": data.get("supplier"),
        "product_price": product_price,
        "shipping_cost": shipping_cost,
        "total_cogs": round(product_price + shipping_cost, 2),
        "delivery_days": int(data.get("delivery_days", 0) or 0),
        "source_url": data.get("source_url", ""),
        "confidence": data.get("confidence", "low"),
    }
