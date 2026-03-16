"""
SQLite 数据库管理
"""
import os
import random
import re
import sqlite3
import string
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "proxy.db")
SUPPORTED_SERVICES = ("tavily", "firecrawl")
TOKEN_PREFIX = {
    "tavily": "tvly-",
    "firecrawl": "fctk-",
}
KEY_PATTERNS = {
    "tavily": r"(tvly-[A-Za-z0-9\-_]{20,})",
    "firecrawl": r"(fc-[A-Za-z0-9\-_]{20,})",
}

KEY_USAGE_COLUMNS = {
    "usage_key_used": "INTEGER",
    "usage_key_limit": "INTEGER",
    "usage_key_remaining": "INTEGER",
    "usage_account_plan": "TEXT DEFAULT ''",
    "usage_account_used": "INTEGER",
    "usage_account_limit": "INTEGER",
    "usage_account_remaining": "INTEGER",
    "usage_synced_at": "TEXT",
    "usage_sync_error": "TEXT DEFAULT ''",
}


def normalize_service(service):
    service = (service or "tavily").strip().lower()
    if service not in SUPPORTED_SERVICES:
        raise ValueError(f"unsupported service: {service}")
    return service


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY,
            service TEXT NOT NULL DEFAULT 'tavily',
            key TEXT UNIQUE NOT NULL,
            email TEXT,
            active INTEGER DEFAULT 1,
            total_used INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            consecutive_fails INTEGER DEFAULT 0,
            last_used_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY,
            service TEXT NOT NULL DEFAULT 'tavily',
            token TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT '',
            hourly_limit INTEGER DEFAULT 0,
            daily_limit INTEGER DEFAULT 0,
            monthly_limit INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY,
            service TEXT NOT NULL DEFAULT 'tavily',
            token_id INTEGER,
            api_key_id INTEGER,
            endpoint TEXT,
            success INTEGER,
            latency_ms INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_usage_token ON usage_logs(token_id);

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    _ensure_service_columns(conn)
    _ensure_usage_columns(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_service_created ON usage_logs(service, created_at)")
    conn.commit()
    conn.close()


def _table_columns(conn, table_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _ensure_service_columns(conn):
    service_columns = {
        "api_keys": "TEXT NOT NULL DEFAULT 'tavily'",
        "tokens": "TEXT NOT NULL DEFAULT 'tavily'",
        "usage_logs": "TEXT NOT NULL DEFAULT 'tavily'",
    }
    for table_name, definition in service_columns.items():
        existing = _table_columns(conn, table_name)
        if "service" not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN service {definition}")


def _ensure_usage_columns(conn):
    existing = _table_columns(conn, "api_keys")
    for name, definition in KEY_USAGE_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE api_keys ADD COLUMN {name} {definition}")


def _service_where(service):
    if not service:
        return "", []
    return " WHERE service = ?", [normalize_service(service)]


def _query_all(conn, table_name, service=None):
    where_sql, params = _service_where(service)
    return conn.execute(f"SELECT * FROM {table_name}{where_sql} ORDER BY id", params).fetchall()


# ═══ Settings ═══

def get_setting(key, default=None):
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key, value):
    conn = get_conn()
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()


# ═══ API Keys ═══

def add_key(key, email="", service="tavily"):
    service = normalize_service(service)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO api_keys (service, key, email) VALUES (?, ?, ?)",
            (service, key, email),
        )
        conn.commit()
        return conn.execute("SELECT * FROM api_keys WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()


def get_all_keys(service=None):
    conn = get_conn()
    try:
        return _query_all(conn, "api_keys", service)
    finally:
        conn.close()


def get_key_by_id(key_id):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    finally:
        conn.close()


def get_active_keys(service=None):
    conn = get_conn()
    try:
        where_sql, params = _service_where(service)
        sql = f"SELECT * FROM api_keys{where_sql}"
        if where_sql:
            sql += " AND active = 1"
        else:
            sql += " WHERE active = 1"
        sql += " ORDER BY id"
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def update_key_usage(key_id, success):
    conn = get_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        if success:
            conn.execute(
                "UPDATE api_keys SET total_used = total_used + 1, consecutive_fails = 0, last_used_at = ? WHERE id = ?",
                (now, key_id),
            )
        else:
            conn.execute(
                "UPDATE api_keys SET total_failed = total_failed + 1, consecutive_fails = consecutive_fails + 1, last_used_at = ? WHERE id = ?",
                (now, key_id),
            )
            row = conn.execute("SELECT consecutive_fails FROM api_keys WHERE id = ?", (key_id,)).fetchone()
            if row and row["consecutive_fails"] >= 3:
                conn.execute("UPDATE api_keys SET active = 0 WHERE id = ?", (key_id,))
        conn.commit()
    finally:
        conn.close()


def toggle_key(key_id, active):
    conn = get_conn()
    try:
        conn.execute("UPDATE api_keys SET active = ?, consecutive_fails = 0 WHERE id = ?", (active, key_id))
        conn.commit()
    finally:
        conn.close()


def delete_key(key_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        conn.commit()
    finally:
        conn.close()


def import_keys_from_text(text, service="tavily"):
    """从批量文本导入不同服务的 key。"""
    service = normalize_service(service)
    pattern = KEY_PATTERNS[service]
    count = 0
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.search(pattern, line)
        if not match:
            continue
        key = match.group(1)
        parts = line.split(",")
        email = parts[0].strip() if len(parts) >= 3 else ""
        add_key(key, email, service=service)
        count += 1
    return count


def update_key_remote_usage(
    key_id,
    *,
    key_used=None,
    key_limit=None,
    key_remaining=None,
    account_plan="",
    account_used=None,
    account_limit=None,
    account_remaining=None,
    synced_at=None,
):
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE api_keys
            SET usage_key_used = ?,
                usage_key_limit = ?,
                usage_key_remaining = ?,
                usage_account_plan = ?,
                usage_account_used = ?,
                usage_account_limit = ?,
                usage_account_remaining = ?,
                usage_synced_at = ?,
                usage_sync_error = ''
            WHERE id = ?
            """,
            (
                key_used,
                key_limit,
                key_remaining,
                account_plan or "",
                account_used,
                account_limit,
                account_remaining,
                synced_at or datetime.now(timezone.utc).isoformat(),
                key_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_key_remote_usage_error(key_id, error_message):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE api_keys SET usage_sync_error = ? WHERE id = ?",
            ((error_message or "").strip(), key_id),
        )
        conn.commit()
    finally:
        conn.close()


# ═══ Tokens ═══

def create_token(name="", service="tavily"):
    service = normalize_service(service)
    token = TOKEN_PREFIX[service] + "".join(random.choices(string.ascii_letters + string.digits, k=32))
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO tokens (service, token, name) VALUES (?, ?, ?)",
            (service, token, name),
        )
        conn.commit()
        return conn.execute("SELECT * FROM tokens WHERE token = ?", (token,)).fetchone()
    finally:
        conn.close()


def get_all_tokens(service=None):
    conn = get_conn()
    try:
        return _query_all(conn, "tokens", service)
    finally:
        conn.close()


def get_token_by_value(token_value):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM tokens WHERE token = ?", (token_value,)).fetchone()
    finally:
        conn.close()


def delete_token(token_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM tokens WHERE id = ?", (token_id,))
        conn.commit()
    finally:
        conn.close()


# ═══ Usage Logs ═══

def log_usage(token_id, api_key_id, endpoint, success, latency_ms, service="tavily"):
    service = normalize_service(service)
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO usage_logs (service, token_id, api_key_id, endpoint, success, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (service, token_id, api_key_id, endpoint, success, latency_ms),
        )
        conn.commit()
    finally:
        conn.close()


def get_usage_stats(token_id=None, service=None):
    """获取用量统计。"""
    conn = get_conn()
    try:
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        month = now.strftime("%Y-%m")
        hour_ago = now.replace(minute=0, second=0, microsecond=0).isoformat()

        filters = []
        filter_params = []
        if service:
            filters.append("service = ?")
            filter_params.append(normalize_service(service))
        if token_id is not None:
            filters.append("token_id = ?")
            filter_params.append(token_id)

        def count(condition, extra_params=None):
            where_parts = [condition] + filters
            sql = "SELECT COUNT(*) as c FROM usage_logs WHERE " + " AND ".join(where_parts)
            params = list(extra_params or []) + filter_params
            row = conn.execute(sql, params).fetchone()
            return row["c"]

        return {
            "today_success": count("success = 1 AND created_at >= ?", [today]),
            "today_failed": count("success = 0 AND created_at >= ?", [today]),
            "month_success": count("success = 1 AND created_at >= ?", [month]),
            "hour_count": count("created_at >= ?", [hour_ago]),
            "today_count": count("created_at >= ?", [today]),
            "month_count": count("created_at >= ?", [month]),
        }
    finally:
        conn.close()


def check_quota(token_id, hourly_limit, daily_limit, monthly_limit, service=None):
    """检查 token 配额是否超限，返回 (ok, reason)。"""
    stats = get_usage_stats(token_id=token_id, service=service)
    if hourly_limit and stats["hour_count"] >= hourly_limit:
        return False, "hourly quota exceeded"
    if daily_limit and stats["today_count"] >= daily_limit:
        return False, "daily quota exceeded"
    if monthly_limit and stats["month_count"] >= monthly_limit:
        return False, "monthly quota exceeded"
    return True, ""
