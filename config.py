"""Central configuration loaded exclusively from .env. No hardcoded business values."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PRODUCTS_DIR = DATA_DIR / "products"
REPORTS_DIR = DATA_DIR / "reports"
SESSIONS_DIR = DATA_DIR / "sessions"
AUTOPSIES_DIR = DATA_DIR / "autopsies"
QUEUE_FILE = DATA_DIR / "queue.txt"
DATABASE_PATH = DATA_DIR / "brand_engine.db"
SCORING_WEIGHTS_PATH = DATA_DIR / "scoring_weights.json"
LOG_FILE = BASE_DIR / "brand_engine.log"

for directory in (PRODUCTS_DIR, REPORTS_DIR, SESSIONS_DIR, AUTOPSIES_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable '{name}'. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return raw if raw not in (None, "") else default


# Required
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Optional - enables reading operator replies from the channel. Without
# these, the system can send notifications but cannot parse replies.
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "")

# Display
SCREEN_WIDTH = _int("SCREEN_WIDTH", 1920)
SCREEN_HEIGHT = _int("SCREEN_HEIGHT", 1080)

# Schedule
SURVEILLANCE_TIME = _str("SURVEILLANCE_TIME", "06:00")
DAILY_BRIEF_TIME = _str("DAILY_BRIEF_TIME", "07:00")
MONITORING_TIME = _str("MONITORING_TIME", "08:00")
CONTENT_BRIEF_TIME = _str("CONTENT_BRIEF_TIME", "10:00")
EVENING_SWEEP_TIME = _str("EVENING_SWEEP_TIME", "18:00")

# System limits
MAX_ACTIVE_STORES = _int("MAX_ACTIVE_STORES", 3)
MAX_AGENT_ITERATIONS = _int("MAX_AGENT_ITERATIONS", 50)
MIN_TIKTOK_ORDERS_PER_DAY = _int("MIN_TIKTOK_ORDERS_PER_DAY", 200)
MIN_TIKTOK_GROWTH_PERCENT = _float("MIN_TIKTOK_GROWTH_PERCENT", 100)
MIN_META_AD_AGE_DAYS = _int("MIN_META_AD_AGE_DAYS", 90)
MIN_META_AD_INTERACTIONS = _int("MIN_META_AD_INTERACTIONS", 10000)

# Thresholds
ORGANIC_SAVE_RATE_THRESHOLD = _float("ORGANIC_SAVE_RATE_THRESHOLD", 0.02)
PAID_CTR_THRESHOLD = _float("PAID_CTR_THRESHOLD", 0.03)
ROAS_CUT_THRESHOLD = _float("ROAS_CUT_THRESHOLD", 2.0)
ROAS_SCALE_THRESHOLD = _float("ROAS_SCALE_THRESHOLD", 3.0)
ROAS_CUT_CONSECUTIVE_DAYS = _int("ROAS_CUT_CONSECUTIVE_DAYS", 3)
ROAS_SCALE_CONSECUTIVE_DAYS = _int("ROAS_SCALE_CONSECUTIVE_DAYS", 2)

# Margins
MIN_GROSS_MARGIN = _float("MIN_GROSS_MARGIN", 30)
MIN_COGS_MULTIPLIER = _float("MIN_COGS_MULTIPLIER", 3.0)

# Operator
OPERATOR_NAME = _str("OPERATOR_NAME", "Operator")
MAX_DAILY_AD_SPEND = _float("MAX_DAILY_AD_SPEND", 250)

# Claude model / computer use config
CLAUDE_MODEL = "claude-sonnet-4-6"
COMPUTER_USE_BETA_HEADER = "computer-use-2025-11-24"
THINKING_EFFORT = "medium"

# Meta ad library search category rotation
META_SEARCH_CATEGORIES = [
    "fitness", "home", "beauty", "pets", "health",
    "kitchen", "sleep", "pain relief", "skincare", "supplements",
]

EXCLUDED_CATEGORIES = {"digital", "food", "age-restricted", "alcohol", "tobacco", "supplements_ingestible"}


def validate_required_config() -> None:
    """Raises EnvironmentError listing all missing required keys at once."""
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not DISCORD_WEBHOOK_URL:
        missing.append("DISCORD_WEBHOOK_URL")
    if missing:
        raise EnvironmentError(
            "Missing required .env values: " + ", ".join(missing) +
            ". Copy .env.example to .env and fill them in before running."
        )


def setup_logging() -> logging.Logger:
    """Configures root logger with rotating file handler (10MB x 5 backups) + console."""
    logger = logging.getLogger("brand_engine")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
