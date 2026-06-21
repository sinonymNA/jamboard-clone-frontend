"""SQLite persistence layer. All other modules go through these functions
rather than touching sqlite3 directly."""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path

import config

logger = logging.getLogger("brand_engine.storage.database")

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT,
    slug TEXT UNIQUE,
    status TEXT,
    priority INTEGER,
    validation_score INTEGER,
    validation_threshold TEXT,
    tiktok_data JSON,
    meta_data JSON,
    blind_spot_data JSON,
    margin_data JSON,
    foundational_docs_path TEXT,
    store_url TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    killed_at TIMESTAMP,
    kill_reason TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS surveillance_runs (
    id INTEGER PRIMARY KEY,
    run_time TIMESTAMP,
    tiktok_results JSON,
    meta_results JSON,
    cross_reference_results JSON,
    products_found INTEGER,
    products_escalated INTEGER,
    products_filtered INTEGER
);

CREATE TABLE IF NOT EXISTS performance_data (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    date DATE,
    ad_spend FLOAT,
    revenue FLOAT,
    roas FLOAT,
    sales INTEGER,
    organic_views INTEGER,
    organic_saves INTEGER,
    save_rate FLOAT,
    entered_by TEXT,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS monitoring_checks (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    check_time TIMESTAMP,
    roas_7day_avg FLOAT,
    roas_trend TEXT,
    action_recommended TEXT,
    alert_sent BOOLEAN,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS autopsies (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    kill_reason TEXT,
    failure_point TEXT,
    misleading_signals JSON,
    lessons_learned TEXT,
    pattern_identified TEXT,
    created_at TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS scoring_history (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    score_data JSON,
    weights_used JSON,
    outcome TEXT,
    created_at TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS system_log (
    id INTEGER PRIMARY KEY,
    log_time TIMESTAMP,
    level TEXT,
    module TEXT,
    message TEXT,
    data JSON
);
"""


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


def _dumps(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=_json_default)


def _loads(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


@contextmanager
def get_connection():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    Path(config.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    logger.info("Database initialized at %s", config.DATABASE_PATH)


# ---------------------------------------------------------------- products --

def upsert_product(data: dict) -> int:
    """Inserts a new product or updates an existing one by slug. Returns id."""
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM products WHERE slug = ?", (data["slug"],)
        ).fetchone()
        json_fields = {"tiktok_data", "meta_data", "blind_spot_data", "margin_data"}
        if existing:
            fields = []
            values = []
            for key, value in data.items():
                if key in ("slug",):
                    continue
                fields.append(f"{key} = ?")
                values.append(_dumps(value) if key in json_fields else value)
            fields.append("updated_at = ?")
            values.append(now)
            values.append(data["slug"])
            conn.execute(
                f"UPDATE products SET {', '.join(fields)} WHERE slug = ?", values
            )
            return existing["id"]

        columns = list(data.keys()) + ["created_at", "updated_at"]
        values = [
            _dumps(v) if k in json_fields else v for k, v in data.items()
        ] + [now, now]
        placeholders = ", ".join("?" for _ in columns)
        cursor = conn.execute(
            f"INSERT INTO products ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        return cursor.lastrowid


def get_product_by_slug(slug: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE slug = ?", (slug,)).fetchone()
        return _row_to_product(row) if row else None


def get_product_by_id(product_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _row_to_product(row) if row else None


def get_products_by_status(status: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM products WHERE status = ?", (status,)).fetchall()
        return [_row_to_product(r) for r in rows]


def count_active_stores() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM products WHERE status IN "
            "('store_building', 'live', 'scaling')"
        ).fetchone()
        return row["c"]


def update_product_status(slug: str, status: str, **extra) -> None:
    with get_connection() as conn:
        fields = ["status = ?", "updated_at = ?"]
        values = [status, datetime.utcnow().isoformat()]
        for key, value in extra.items():
            fields.append(f"{key} = ?")
            values.append(value)
        values.append(slug)
        conn.execute(f"UPDATE products SET {', '.join(fields)} WHERE slug = ?", values)


def kill_product(slug: str, reason: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET status = 'killed', kill_reason = ?, killed_at = ?, "
            "updated_at = ? WHERE slug = ?",
            (reason, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), slug),
        )


def _row_to_product(row: sqlite3.Row) -> dict:
    record = dict(row)
    for key in ("tiktok_data", "meta_data", "blind_spot_data", "margin_data"):
        record[key] = _loads(record.get(key))
    return record


# ------------------------------------------------------------- surveillance --

def log_surveillance_run(
    tiktok_results: list,
    meta_results: list,
    cross_reference_results: dict,
    products_found: int,
    products_escalated: int,
    products_filtered: int,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO surveillance_runs (run_time, tiktok_results, meta_results, "
            "cross_reference_results, products_found, products_escalated, "
            "products_filtered) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.utcnow().isoformat(),
                _dumps(tiktok_results),
                _dumps(meta_results),
                _dumps(cross_reference_results),
                products_found,
                products_escalated,
                products_filtered,
            ),
        )
        return cursor.lastrowid


# ----------------------------------------------------------- performance ---

def log_performance(product_id: int, entry: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO performance_data (product_id, date, ad_spend, revenue, "
            "roas, sales, organic_views, organic_saves, save_rate, entered_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                product_id,
                entry.get("date", date.today().isoformat()),
                entry.get("ad_spend", 0.0),
                entry.get("revenue", 0.0),
                entry.get("roas", 0.0),
                entry.get("sales", 0),
                entry.get("organic_views", 0),
                entry.get("organic_saves", 0),
                entry.get("save_rate", 0.0),
                entry.get("entered_by", "operator"),
            ),
        )


def get_recent_performance(product_id: int, days: int = 7) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM performance_data WHERE product_id = ? "
            "ORDER BY date DESC LIMIT ?",
            (product_id, days),
        ).fetchall()
        return [dict(r) for r in rows]


# ----------------------------------------------------------- monitoring ----

def log_monitoring_check(product_id: int, check: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO monitoring_checks (product_id, check_time, roas_7day_avg, "
            "roas_trend, action_recommended, alert_sent) VALUES (?, ?, ?, ?, ?, ?)",
            (
                product_id,
                datetime.utcnow().isoformat(),
                check.get("roas_7day_avg", 0.0),
                check.get("roas_trend", "unknown"),
                check.get("action_recommended", "none"),
                check.get("alert_sent", False),
            ),
        )


# ------------------------------------------------------------- autopsies ---

def log_autopsy(product_id: int, autopsy: dict) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO autopsies (product_id, kill_reason, failure_point, "
            "misleading_signals, lessons_learned, pattern_identified, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                product_id,
                autopsy.get("kill_reason"),
                autopsy.get("failure_point"),
                _dumps(autopsy.get("misleading_signals", [])),
                autopsy.get("lessons_learned"),
                autopsy.get("pattern_identified"),
                datetime.utcnow().isoformat(),
            ),
        )
        return cursor.lastrowid


def get_all_autopsies() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM autopsies ORDER BY created_at DESC").fetchall()
        records = [dict(r) for r in rows]
        for r in records:
            r["misleading_signals"] = _loads(r.get("misleading_signals"))
        return records


def count_autopsies() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM autopsies").fetchone()["c"]


# --------------------------------------------------------- scoring history -

def log_scoring(product_id: int, score_data: dict, weights_used: dict) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO scoring_history (product_id, score_data, weights_used, "
            "outcome, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                product_id,
                _dumps(score_data),
                _dumps(weights_used),
                "pending",
                datetime.utcnow().isoformat(),
            ),
        )
        return cursor.lastrowid


def update_scoring_outcome(product_id: int, outcome: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE scoring_history SET outcome = ? WHERE product_id = ? "
            "AND outcome = 'pending'",
            (outcome, product_id),
        )


def get_scoring_history_with_outcomes() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM scoring_history WHERE outcome != 'pending'"
        ).fetchall()
        records = [dict(r) for r in rows]
        for r in records:
            r["score_data"] = _loads(r.get("score_data"))
            r["weights_used"] = _loads(r.get("weights_used"))
        return records


def count_terminal_outcomes_since_last_update() -> int:
    with get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM scoring_history WHERE outcome != 'pending'"
        ).fetchone()["c"]


# ------------------------------------------------------------- system_log --

def log_system_event(level: str, module: str, message: str, data: dict | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO system_log (log_time, level, module, message, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), level, module, message, _dumps(data)),
        )


def get_recent_system_logs(hours: int = 24) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM system_log WHERE log_time >= datetime('now', ?) "
            "ORDER BY log_time DESC",
            (f"-{hours} hours",),
        ).fetchall()
        return [dict(r) for r in rows]
