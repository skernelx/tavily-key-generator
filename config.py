"""
Tavily 注册器配置
优先读取环境变量；若项目根目录存在 .env，则先载入。
"""
import os
from pathlib import Path


def _load_dotenv():
    env_path = Path(__file__).resolve().with_name(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _get_str(name, default=""):
    return os.getenv(name, default).strip()


def _get_int(name, default):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)

def _get_list(name, fallback=""):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        value = fallback
    return [item.strip() for item in value.split(",") if item.strip()]


def _get_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


_load_dotenv()

# 邮箱配置
EMAIL_PROVIDER = _get_str("EMAIL_PROVIDER", "cloudflare").lower()
SUPPORTED_EMAIL_PROVIDERS = ("cloudflare", "duckmail")
EMAIL_API_URL = _get_str("EMAIL_API_URL")
EMAIL_API_TOKEN = _get_str("EMAIL_API_TOKEN")
EMAIL_DOMAIN = _get_str("EMAIL_DOMAIN")
EMAIL_DOMAINS = _get_list("EMAIL_DOMAINS", EMAIL_DOMAIN)
DUCKMAIL_API_URL = _get_str("DUCKMAIL_API_URL", "https://api.duckmail.sbs")
DUCKMAIL_API_KEY = _get_str("DUCKMAIL_API_KEY")
DUCKMAIL_DOMAIN = _get_str("DUCKMAIL_DOMAIN")
DUCKMAIL_DOMAINS = _get_list("DUCKMAIL_DOMAINS", DUCKMAIL_DOMAIN)

# 上传目标
SERVER_URL = _get_str("SERVER_URL")
SERVER_ADMIN_PASSWORD = _get_str("SERVER_ADMIN_PASSWORD")

# 注册默认参数
DEFAULT_COUNT = _get_int("DEFAULT_COUNT", 5)
DEFAULT_CONCURRENCY = _get_int("DEFAULT_CONCURRENCY", 2)
DEFAULT_DELAY = _get_int("DEFAULT_DELAY", 10)
DEFAULT_UPLOAD = _get_bool("DEFAULT_UPLOAD", True)

# 浏览器模式
REGISTER_HEADLESS = _get_bool("REGISTER_HEADLESS", True)
# Firecrawl 未单独配置时，默认继承 REGISTER_HEADLESS，避免意外跑到前台。
FIRECRAWL_REGISTER_HEADLESS = _get_bool("FIRECRAWL_REGISTER_HEADLESS", REGISTER_HEADLESS)
EMAIL_CODE_TIMEOUT = _get_int("EMAIL_CODE_TIMEOUT", 90)
API_KEY_TIMEOUT = _get_int("API_KEY_TIMEOUT", 20)
EMAIL_POLL_INTERVAL = _get_int("EMAIL_POLL_INTERVAL", 3)

# Solver 配置
SOLVER_PORT = _get_str("SOLVER_PORT", "5073")
LOCAL_SOLVER_URL = _get_str("LOCAL_SOLVER_URL", f"http://127.0.0.1:{SOLVER_PORT}")
SOLVER_THREADS = _get_int("SOLVER_THREADS", 1)
