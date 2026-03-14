"""
SQLite 数据库管理
"""
import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "proxy.db")


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
            token TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT '',
            hourly_limit INTEGER DEFAULT 100,
            daily_limit INTEGER DEFAULT 500,
            monthly_limit INTEGER DEFAULT 5000,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY,
            token_id INTEGER,
            api_key_id INTEGER,
            endpoint TEXT,
            success INTEGER,
            latency_ms INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_usage_token ON usage_logs(token_id);
    """)
    conn.commit()
    conn.close()


# ═══ API Keys ═══

def add_key(key, email=""):
    conn = get_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO api_keys (key, email) VALUES (?, ?)", (key, email))
        conn.commit()
        return conn.execute("SELECT * FROM api_keys WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()


def get_all_keys():
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM api_keys ORDER BY id").fetchall()
    finally:
        conn.close()


def get_active_keys():
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM api_keys WHERE active = 1 ORDER BY id").fetchall()
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
            # 连续失败 3 次自动禁用
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


def import_keys_from_text(text):
    """从 api_keys.md 格式文本批量导入 key"""
    import re
    count = 0
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # 格式: email,password,tvly-xxx,timestamp;
        match = re.search(r"(tvly-[A-Za-z0-9\-_]{20,})", line)
        if match:
            key = match.group(1)
            parts = line.split(",")
            email = parts[0] if len(parts) >= 3 else ""
            add_key(key, email)
            count += 1
    return count


# ═══ Tokens ═══

def create_token(name=""):
    import random
    import string
    token = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    conn = get_conn()
    try:
        conn.execute("INSERT INTO tokens (token, name) VALUES (?, ?)", (token, name))
        conn.commit()
        return conn.execute("SELECT * FROM tokens WHERE token = ?", (token,)).fetchone()
    finally:
        conn.close()


def get_all_tokens():
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM tokens ORDER BY id").fetchall()
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

def log_usage(token_id, api_key_id, endpoint, success, latency_ms):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO usage_logs (token_id, api_key_id, endpoint, success, latency_ms) VALUES (?, ?, ?, ?, ?)",
            (token_id, api_key_id, endpoint, success, latency_ms),
        )
        conn.commit()
    finally:
        conn.close()


def get_usage_stats(token_id=None):
    """获取用量统计"""
    conn = get_conn()
    try:
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        month = now.strftime("%Y-%m")
        hour_ago = now.replace(minute=0, second=0, microsecond=0).isoformat()

        where = ""
        params = []
        if token_id:
            where = "AND token_id = ?"
            params = [token_id]

        def count(condition, extra_params=None):
            p = (extra_params or []) + list(params)
            row = conn.execute(
                f"SELECT COUNT(*) as c FROM usage_logs WHERE {condition} {where}", p
            ).fetchone()
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


def check_quota(token_id, hourly_limit, daily_limit, monthly_limit):
    """检查 token 配额是否超限，返回 (ok, reason)"""
    stats = get_usage_stats(token_id)
    if hourly_limit and stats["hour_count"] >= hourly_limit:
        return False, "hourly quota exceeded"
    if daily_limit and stats["today_count"] >= daily_limit:
        return False, "daily quota exceeded"
    if monthly_limit and stats["month_count"] >= monthly_limit:
        return False, "monthly quota exceeded"
    return True, ""
