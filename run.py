#!/usr/bin/env python3
import os
import sys
import subprocess

# ──────────────────────────────────────────────
# 启动前自动检查并安装依赖
# ──────────────────────────────────────────────

def _ensure_venv():
    """确保虚拟环境存在并激活"""
    _HERE = os.path.dirname(os.path.abspath(__file__))
    venv_dir = os.path.join(_HERE, "venv")

    # 如果已经在虚拟环境中，直接返回
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        return

    # 创建虚拟环境
    if not os.path.exists(venv_dir):
        print("创建虚拟环境...")
        subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
        print("✅ 虚拟环境创建完成\n")

    # 重新启动脚本在虚拟环境中
    python_exe = _get_venv_python(venv_dir)

    os.execv(python_exe, [python_exe] + sys.argv)

def _get_venv_python(venv_dir):
    candidates = []
    if sys.platform == "win32":
        candidates.append(os.path.join(venv_dir, "Scripts", "python.exe"))
    else:
        candidates.extend([
            os.path.join(venv_dir, "bin", "python"),
            os.path.join(venv_dir, "bin", "python3"),
        ])

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(f"未找到虚拟环境 Python: {venv_dir}")

def _ensure_deps():
    _HERE = os.path.dirname(os.path.abspath(__file__))
    req_file = os.path.join(_HERE, "requirements.txt")
    missing = []
    pkg_map = {
        "camoufox": "camoufox",
        "patchright": "patchright",
        "psutil": "psutil",
        "quart": "quart",
        "requests": "requests",
        "rich": "rich",
    }
    for mod, pkg in pkg_map.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"正在安装依赖: {', '.join(missing)}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "-q"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file, "-q"])
        print("✅ 依赖安装完成\n")

_ensure_venv()
_ensure_deps()

import time
import signal
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import requests as std_requests
from config import (
    DEFAULT_UPLOAD,
    DEFAULT_CONCURRENCY,
    DUCKMAIL_API_KEY,
    DUCKMAIL_API_URL,
    DUCKMAIL_DOMAINS,
    EMAIL_PROVIDER,
    SERVER_URL,
    SERVER_ADMIN_PASSWORD,
    EMAIL_API_URL,
    EMAIL_API_TOKEN,
    EMAIL_DOMAINS,
    SUPPORTED_EMAIL_PROVIDERS,
    DEFAULT_COUNT,
    DEFAULT_DELAY,
    is_placeholder_env_value,
    SOLVER_PORT,
    SOLVER_THREADS,
    LOCAL_SOLVER_URL,
)
from tavily_core import create_email as create_tavily_email, register as register_tavily
from firecrawl_core import register as register_firecrawl
from exa_core import register as register_exa
from mail_provider import create_email, get_active_domain, get_configured_domains, set_selected_domain

# ──────────────────────────────────────────────
# Solver 管理
# ──────────────────────────────────────────────

solver_proc = None

def _camoufox_browser_ready():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "camoufox", "path"],
            capture_output=True,
            check=True,
            text=True,
        )
    except Exception:
        return False

    install_dir = result.stdout.strip()
    if not install_dir:
        return False

    if os.path.isfile(install_dir):
        return True

    if not os.path.isdir(install_dir):
        return False

    try:
        return bool(os.listdir(install_dir))
    except OSError:
        return False

def _default_patchright_browser_root():
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env_path:
        if env_path == "0":
            import patchright
            return os.path.join(os.path.dirname(patchright.__file__), "driver", "package", ".local-browsers")
        return os.path.expanduser(env_path)

    home = os.path.expanduser("~")
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return os.path.join(local_app_data, "ms-playwright")
        return os.path.join(home, "AppData", "Local", "ms-playwright")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Caches", "ms-playwright")
    return os.path.join(home, ".cache", "ms-playwright")

def _patchright_expected_browser_paths():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "patchright", "install", "--dry-run", "chromium"],
            capture_output=True,
            text=True,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    paths = []
    prefix = "Install location:"
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith(prefix):
            continue
        install_path = line[len(prefix):].strip()
        if install_path:
            paths.append(install_path)
    return paths

def _patchright_browser_ready():
    expected_paths = _patchright_expected_browser_paths()
    if expected_paths:
        for install_path in expected_paths:
            if os.path.basename(install_path).startswith("chromium-") and os.path.isdir(install_path):
                return True
        return False

    browser_root = _default_patchright_browser_root()
    if not os.path.isdir(browser_root):
        return False

    try:
        entries = os.listdir(browser_root)
    except OSError:
        return False

    for entry in entries:
        if entry.startswith("chromium-"):
            return True
    return False

def _ensure_camoufox_browser():
    if _camoufox_browser_ready():
        return

    print("正在下载 Camoufox 浏览器...")
    subprocess.check_call([sys.executable, "-m", "camoufox", "fetch"])
    print("✅ 浏览器下载完成\n")

def _ensure_patchright_browser():
    if _patchright_browser_ready():
        return

    print("正在安装 Patchright 浏览器...")
    if sys.platform.startswith("linux"):
        try:
            subprocess.check_call([sys.executable, "-m", "patchright", "install", "--with-deps", "chromium"])
        except subprocess.CalledProcessError:
            print("⚠️  Patchright --with-deps 安装失败，尝试退回普通安装 chromium...")
            subprocess.check_call([sys.executable, "-m", "patchright", "install", "chromium"])
    else:
        subprocess.check_call([sys.executable, "-m", "patchright", "install", "chromium"])
    print("✅ Patchright 浏览器安装完成\n")

def _ensure_service_browsers(service):
    _ensure_camoufox_browser()
    if service == "tavily":
        _ensure_patchright_browser()

def validate_runtime_config(upload, show_provider_summary=True):
    if EMAIL_PROVIDER not in SUPPORTED_EMAIL_PROVIDERS:
        print(f"❌ 不支持的 EMAIL_PROVIDER: {EMAIL_PROVIDER}")
        print(f"   当前仅支持: {', '.join(SUPPORTED_EMAIL_PROVIDERS)}")
        return False

    missing = []
    placeholder = []
    required = {}

    def append_unique(items, value):
        if value not in items:
            items.append(value)

    if EMAIL_PROVIDER == "duckmail":
        required["DUCKMAIL_API_URL"] = DUCKMAIL_API_URL
        if any(is_placeholder_env_value("DUCKMAIL_DOMAINS", item) for item in DUCKMAIL_DOMAINS):
            append_unique(placeholder, "DUCKMAIL_DOMAIN / DUCKMAIL_DOMAINS")
    else:
        required.update({
            "EMAIL_API_URL": EMAIL_API_URL,
            "EMAIL_API_TOKEN": EMAIL_API_TOKEN,
        })
        if not EMAIL_DOMAINS:
            missing.append("EMAIL_DOMAIN / EMAIL_DOMAINS")
        elif any(is_placeholder_env_value("EMAIL_DOMAINS", item) for item in EMAIL_DOMAINS):
            append_unique(placeholder, "EMAIL_DOMAIN / EMAIL_DOMAINS")

    if upload:
        required.update({
            "SERVER_URL": SERVER_URL,
            "SERVER_ADMIN_PASSWORD": SERVER_ADMIN_PASSWORD,
        })

    for key, value in required.items():
        if not value:
            missing.append(key)
        elif is_placeholder_env_value(key, value):
            append_unique(placeholder, key)

    if missing or placeholder:
        if missing:
            print("❌ 缺少必要环境变量/配置：")
        for key in missing:
            print(f"   - {key}")
        if placeholder:
            print("❌ 检测到 .env.example 占位值尚未替换：")
            for key in placeholder:
                print(f"   - {key}")
        print("   请先配置 .env 或系统环境变量，并把示例占位值替换成真实配置。")
        return False

    if show_provider_summary:
        if EMAIL_PROVIDER == "duckmail":
            configured = ", ".join(DUCKMAIL_DOMAINS) if DUCKMAIL_DOMAINS else "未配置，启动时自动选择"
            api_hint = "已配置 API Key" if DUCKMAIL_API_KEY else "未配置 API Key（仅可使用公开域名）"
            print(f"📧 当前邮箱 provider: duckmail")
            print(f"   域名配置: {configured}")
            print(f"   API: {api_hint}")
        else:
            print(f"📧 当前邮箱 provider: cloudflare")
            print(f"   域名配置: {', '.join(EMAIL_DOMAINS)}")

    return True

def print_runtime_summary(service="tavily"):
    service_name = {
        "tavily": "Tavily",
        "firecrawl": "Firecrawl",
        "exa": "Exa",
    }.get(service, "Tavily")
    output_file = {
        "tavily": "accounts.txt",
        "firecrawl": "firecrawl_accounts.txt",
        "exa": "exa_accounts.txt",
    }.get(service, "accounts.txt")
    account_prefix = {
        "tavily": "tavily-",
        "firecrawl": "fc-",
        "exa": "exa-",
    }.get(service, "tavily-")
    print(f"""
┌──────────────────────────────────────────┐
│      多服务自动注册启动台                │
├──────────────────────────────────────────┤
│  当前服务: {service_name:<10}               │
│  自动检查环境 / 依赖 / 邮箱配置             │
└──────────────────────────────────────────┘
""")
    print("当前默认配置：")
    print(f"  账号前缀: {account_prefix}")
    print(f"  输出文件: {output_file}")
    print(f"  邮箱链路: {EMAIL_PROVIDER}")
    print(f"  注册间隔: {DEFAULT_DELAY}s")
    print(f"  默认并发: {DEFAULT_CONCURRENCY}")
    print(f"  默认上传: {'开启' if DEFAULT_UPLOAD else '关闭'}")
    if service == "tavily":
        print(f"  Solver 端口: {SOLVER_PORT}")

def prompt_domain_choice():
    domains = get_configured_domains()
    if not domains:
        print(f"📮 当前域名: {get_active_domain() or '自动选择'}")
        return

    if len(domains) == 1:
        set_selected_domain(domains[0])
        print(f"📮 当前域名: {domains[0]}")
        return

    print("\n检测到多个可选域名：")
    for index, domain in enumerate(domains, start=1):
        print(f"  {index}. {domain}")

    while True:
        print(f"请选择本轮使用的域名 (1-{len(domains)}，默认 1): ", end="")
        raw = input().strip()
        if raw == "":
            choice = 1
        elif raw.isdigit() and 1 <= int(raw) <= len(domains):
            choice = int(raw)
        else:
            print("❌ 请输入有效编号")
            continue

        selected = domains[choice - 1]
        set_selected_domain(selected)
        print(f"📮 已选择域名: {selected}")
        return

def prompt_register_count():
    while True:
        print(f"\n请输入注册数量 (默认 {DEFAULT_COUNT}): ", end="")
        raw = input().strip()
        if raw == "":
            return DEFAULT_COUNT
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("❌ 请输入大于 0 的整数")

def prompt_concurrency(count):
    default_concurrency = min(DEFAULT_CONCURRENCY, count)
    while True:
        print(f"请输入并发数 (默认 {default_concurrency}): ", end="")
        raw = input().strip()
        if raw == "":
            return default_concurrency
        if raw.isdigit():
            value = int(raw)
            if value > 0:
                return min(value, count)
        print("❌ 请输入大于 0 的整数")

def prompt_upload_choice():
    default_label = "Y/n" if DEFAULT_UPLOAD else "y/N"
    while True:
        print(f"是否自动上传到服务器? [{default_label}]: ", end="")
        raw = input().strip().lower()
        if raw == "":
            return DEFAULT_UPLOAD
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("❌ 请输入 y 或 n")

def start_solver(thread_count=None):
    global solver_proc
    actual_threads = max(SOLVER_THREADS, thread_count or 1)
    
    # 清理旧进程
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                if any('api_solver.py' in str(c) for c in cmdline):
                    print(f"清理旧 Solver 进程 (PID: {proc.pid})")
                    proc.kill()
                    time.sleep(1)
            except:
                pass
    except ImportError:
        print("⚠️  未安装 psutil，跳过旧 Solver 进程清理")
    
    # 启动 Solver
    print(f"启动 Turnstile Solver... (threads={actual_threads})")
    
    # 获取 Python 路径
    if os.path.exists('venv'):
        python_path = _get_venv_python('venv')
    else:
        python_path = sys.executable
    
    solver_proc = subprocess.Popen(
        [python_path, 'api_solver.py', '--browser_type', 'chromium', '--thread', str(actual_threads), '--port', SOLVER_PORT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # 等待启动
    for i in range(30):
        try:
            r = std_requests.get(f"{LOCAL_SOLVER_URL}/", timeout=1)
            if r.status_code == 200:
                print("✅ Solver 已启动\n")
                return True
        except:
            pass
        time.sleep(1)
        if i % 5 == 0:
            print(f"等待 Solver 启动... ({i}s)")
    
    print("❌ Solver 启动超时")
    return False

def stop_solver():
    global solver_proc
    if solver_proc:
        solver_proc.terminate()
        try:
            solver_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            solver_proc.kill()
            solver_proc.wait(timeout=5)
        solver_proc = None

def signal_handler(sig, frame):
    print("\n\n正在退出...")
    stop_solver()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, signal_handler)

# ──────────────────────────────────────────────
# 上传到代理服务器
# ──────────────────────────────────────────────

def upload_key(email, api_key, service="tavily"):
    try:
        r = std_requests.post(
            f"{SERVER_URL}/api/keys",
            json={"key": api_key, "email": email, "service": service},
            headers={"Authorization": f"Bearer {SERVER_ADMIN_PASSWORD}"},
            timeout=15,
        )
        if r.status_code in (200, 201):
            print("✅ 已上传服务器")
            return True
        print(f"⚠️  上传失败 {r.status_code}: {r.text[:100]}")
        return False
    except Exception as e:
        print(f"⚠️  上传失败: {e}")
        return False

# ──────────────────────────────────────────────
# 注册流程
# ──────────────────────────────────────────────

def do_register(count, delay, upload, service="tavily"):
    return do_register_parallel(count, delay, upload, 1, service)

def register_one(index, total, upload, service="tavily"):
    print(f"{'='*60}")
    print(f"📧 注册 ({index}/{total})")
    print(f"{'='*60}\n")

    try:
        email, password = create_email(service=service)

        if service == "tavily":
            result = register_tavily(email, password)
        elif service == "firecrawl":
            result = register_firecrawl(email, password)
        else:
            result = register_exa(email, password)

        if result and result != "SUCCESS_NO_KEY":
            if upload:
                upload_key(email, result, service=service)
            return "success"
        if result == "SUCCESS_NO_KEY":
            return "success_no_key"
        return "failed"
    except Exception as e:
        print(f"❌ 注册异常: {e}")
        return "failed"

def do_register_parallel(count, delay, upload, concurrency, service="tavily"):
    success = 0
    failed = 0
    actual_concurrency = max(1, min(concurrency, count))
    print(f"⚙️  本轮并发: {actual_concurrency}")

    if actual_concurrency == 1:
        for i in range(count):
            if i > 0:
                print(f"\n⏳ 等待 {delay} 秒...\n")
                time.sleep(delay)
            status = register_one(i + 1, count, upload, service)
            if status in {"success", "success_no_key"}:
                success += 1
            else:
                failed += 1
    else:
        print("🧵 已启用并发注册模式")
        with ThreadPoolExecutor(max_workers=actual_concurrency) as executor:
            futures = {}
            next_index = 1

            while next_index <= count and len(futures) < actual_concurrency:
                future = executor.submit(register_one, next_index, count, upload, service)
                futures[future] = next_index
                next_index += 1

            while futures:
                done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)
                for future in done:
                    futures.pop(future, None)
                    status = future.result()
                    if status in {"success", "success_no_key"}:
                        success += 1
                    else:
                        failed += 1

                    if next_index <= count:
                        if delay > 0:
                            print(f"\n⏳ 等待 {delay} 秒后补充新任务...\n")
                            time.sleep(delay)
                        next_future = executor.submit(register_one, next_index, count, upload, service)
                        futures[next_future] = next_index
                        next_index += 1

    print(f"\n{'='*60}")
    print(f"✅ 成功: {success}  ❌ 失败: {failed}")
    print(f"{'='*60}\n")

def run_register_flow(count, delay, upload, concurrency, service="tavily"):
    if count <= 0:
        print("❌ 注册数量必须大于 0")
        return
    if delay < 0:
        print("❌ 间隔秒数不能小于 0")
        return
    if concurrency <= 0:
        print("❌ 并发数必须大于 0")
        return
    print(f"\n🚀 开始注册: 数量={count} 并发={min(concurrency, count)} 间隔={delay}s 上传={'是' if upload else '否'}")
    do_register_parallel(count, delay, upload, concurrency, service)

def prompt_service_choice():
    """选择要注册的服务"""
    print("\n请选择要注册的服务：")
    print("  1. Tavily")
    print("  2. Firecrawl")
    print("  3. Exa")

    while True:
        print("请输入选项 (1-3，默认 1): ", end="")
        raw = input().strip()
        if raw == "" or raw == "1":
            return "tavily"
        elif raw == "2":
            return "firecrawl"
        elif raw == "3":
            return "exa"
        else:
            print("❌ 请输入有效编号")
            continue

def main():
    service = prompt_service_choice()
    print_runtime_summary(service)

    # 目前只有 Tavily 需要 Solver
    need_solver = (service == "tavily")

    if not validate_runtime_config(False, show_provider_summary=True):
        return

    prompt_domain_choice()
    count = prompt_register_count()
    concurrency = prompt_concurrency(count)
    upload = prompt_upload_choice()

    if upload and not validate_runtime_config(True, show_provider_summary=False):
        return

    _ensure_service_browsers(service)

    if need_solver and not start_solver(thread_count=concurrency):
        print("无法启动 Solver，退出")
        return

    try:
        run_register_flow(count, DEFAULT_DELAY, upload, concurrency, service)
    finally:
        if need_solver:
            stop_solver()

if __name__ == "__main__":
    main()
