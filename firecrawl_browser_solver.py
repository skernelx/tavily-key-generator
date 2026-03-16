"""
使用 Camoufox 完成 Firecrawl 注册
思路：从真实注册页开始，自动处理邮箱验证和 API Key 提取
"""
import os
import re
import threading
import time
import requests as std_requests
from camoufox.sync_api import Camoufox
from config import (
    API_KEY_TIMEOUT,
    EMAIL_CODE_TIMEOUT,
    FIRECRAWL_REGISTER_HEADLESS,
)
from mail_provider import get_verification_link

_HERE = os.path.dirname(os.path.abspath(__file__))
_SAVE_FILE = os.path.join(_HERE, "firecrawl_accounts.txt")
_SAVE_LOCK = threading.Lock()
_FIRECRAWL_SIGNUP_RESULT_TIMEOUT = 15


def attach_signup_feedback_tracker(page):
    """记录注册请求的关键反馈，方便识别风控或表单错误。"""
    events = []

    def handle_response(response):
        url = response.url.lower()
        if not any(token in url for token in ("signin", "signup", "auth", "clerk")):
            return

        try:
            body = response.text()
        except Exception:
            body = ""

        events.append(
            {
                "url": response.url,
                "status": response.status,
                "body": body[:1500],
            }
        )

    page.on("response", handle_response)
    return events


def detect_signup_result(page, signup_events):
    """根据页面内容和网络响应判断注册提交是否真的成功。"""
    snapshots = []
    current_url = page.url.lower()

    if "confirm-email" in current_url or "confirm_email" in current_url:
        return ("sent", "")

    try:
        snapshots.append(page.locator("body").inner_text())
    except Exception:
        pass

    try:
        snapshots.append(page.content())
    except Exception:
        pass

    snapshots.extend(event.get("body", "") for event in signup_events[-6:])
    combined = "\n".join(snapshots).lower()

    if "security check failed" in combined or "suspicious activity" in combined:
        return (
            "blocked",
            "Firecrawl 返回了 Security check failed / suspicious activity，当前浏览器指纹或网络被风控拦截。",
        )

    if "already exists" in combined or "account already exists" in combined:
        return ("exists", "这个邮箱看起来已经注册过了。")

    if "invalid email" in combined or "email address is invalid" in combined:
        return ("invalid_email", "Firecrawl 认为这个邮箱地址无效。")

    if "password is not strong enough" in combined or "at least 12 characters" in combined:
        return (
            "weak_password",
            "Firecrawl 拒绝了当前密码强度，至少需要 12 位，并同时包含大小写、数字和特殊字符。",
        )

    success_markers = (
        "check your email",
        "confirm email",
        "confirmation link",
        "verify your email",
        "verification email",
        "email has been sent",
        "we sent you an email",
        "did not receive the email",
        "once confirmed, you may sign in",
    )
    if any(marker in combined for marker in success_markers):
        return ("sent", "")

    return ("", "")


def wait_for_signup_result(page, signup_events, timeout=_FIRECRAWL_SIGNUP_RESULT_TIMEOUT):
    """等待注册提交后的明确结果，避免被风控时继续盲等验证邮件。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, message = detect_signup_result(page, signup_events)
        if status:
            return status, message
        time.sleep(1)

    current_url = page.url.lower()
    if "confirm-email" in current_url or "confirm_email" in current_url:
        return ("sent", "")

    if "view=signup" in current_url or current_url.rstrip("/").endswith("/signin"):
        return (
            "stalled",
            "提交后页面仍停留在注册页，Firecrawl 没有明确确认已发送验证邮件。",
        )

    return ("", "")

def fill_first_input(page, selectors, value):
    """填充第一个存在的输入框"""
    for selector in selectors:
        if page.query_selector(selector):
            page.fill(selector, value)
            return selector
    return None

def extract_api_key_from_page(page):
    """从 API Keys 页面提取 API Key"""
    try:
        # 等待 API Keys 页面加载
        time.sleep(3)

        # 尝试多种选择器查找 API Key
        selectors = [
            'code:has-text("fc-")',
            '[data-testid="api-key"]',
            '.api-key',
            'input[value^="fc-"]',
            'span:has-text("fc-")',
        ]

        for selector in selectors:
            elements = page.query_selector_all(selector)
            for element in elements:
                text = element.inner_text() or element.get_attribute('value') or ''
                match = re.search(r'fc-[a-zA-Z0-9_-]{20,}', text)
                if match:
                    return match.group(0)

        # 从页面 HTML 中提取
        html = page.content()
        matches = re.findall(r'fc-[a-zA-Z0-9_-]{20,}', html)
        if matches:
            return matches[0]

        return None
    except Exception as e:
        print(f"⚠️  提取 API Key 失败: {e}")
        return None

def create_api_key(page):
    """在 Dashboard 中创建新的 API Key"""
    try:
        # 查找并点击创建 API Key 按钮
        create_selectors = [
            'button:has-text("Create")',
            'button:has-text("New API Key")',
            'button:has-text("Generate")',
            '[data-testid="create-api-key"]',
        ]

        for selector in create_selectors:
            if page.query_selector(selector):
                page.click(selector)
                time.sleep(2)
                break

        # 如果有名称输入框，填写名称
        name_input = page.query_selector('input[name="name"], input[placeholder*="name" i]')
        if name_input:
            page.fill('input[name="name"], input[placeholder*="name" i]', 'auto-generated-key')
            time.sleep(1)

        # 点击确认按钮
        confirm_selectors = [
            'button:has-text("Create")',
            'button:has-text("Generate")',
            'button:has-text("Confirm")',
            'button[type="submit"]',
        ]

        for selector in confirm_selectors:
            if page.query_selector(selector):
                page.click(selector)
                time.sleep(3)
                break

        return True
    except Exception as e:
        print(f"⚠️  创建 API Key 失败: {e}")
        return False

def save_account(email, password, api_key):
    """并发注册时串行写入 firecrawl_accounts.txt"""
    with _SAVE_LOCK:
        with open(_SAVE_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{email},{password},{api_key}\n")

def verify_api_key(api_key, timeout=30):
    """真实调用 Firecrawl API，验证新 key 可用"""
    transient_errors = (
        std_requests.exceptions.SSLError,
        std_requests.exceptions.ConnectionError,
        std_requests.exceptions.Timeout,
    )
    last_error = None

    for attempt in range(1, 4):
        try:
            response = std_requests.post(
                "https://api.firecrawl.dev/v2/scrape",
                json={
                    "url": "https://example.com",
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            break
        except transient_errors as exc:
            last_error = exc
            if attempt < 3:
                print(f"⚠️  API Key 调用测试遇到网络/TLS 异常，正在重试 ({attempt}/3): {exc}")
                time.sleep(attempt)
                continue
            print(f"⚠️  API Key 调用测试遇到网络/TLS 异常，暂时无法确认 Key 是否可用: {exc}")
            print("   这通常是本地代理 / TUN / DNS 劫持链路导致的瞬时握手失败，不一定代表 Key 无效。")
            return None
        except Exception as exc:
            print(f"❌ API Key 调用测试失败: {exc}")
            return False
    else:
        print(f"⚠️  API Key 调用测试未获得有效响应: {last_error}")
        return None

    if response.status_code == 200:
        print("✅ API Key 调用测试通过")
        return True

    preview = response.text.strip().replace("\n", " ")[:160]
    print(f"❌ API Key 调用测试失败: HTTP {response.status_code}")
    if preview:
        print(f"   响应: {preview}")
    return False

def submit_form(page, input_selector=None):
    """提交表单"""
    button_selectors = [
        'button[type="submit"]',
        'button:has-text("Sign up")',
        'button:has-text("Continue")',
        'button:has-text("Register")',
    ]

    for selector in button_selectors:
        if page.query_selector(selector):
            try:
                page.click(selector, timeout=3000)
                return True
            except Exception:
                continue

    if input_selector and page.query_selector(input_selector):
        try:
            page.press(input_selector, 'Enter')
            return True
        except Exception:
            return False

    return False

def register_with_browser(email, password):
    """使用浏览器自动化注册 Firecrawl"""
    print(f"🌐 使用浏览器模式注册 Firecrawl: {email}")

    try:
        with Camoufox(headless=FIRECRAWL_REGISTER_HEADLESS) as browser:
            page = browser.new_page()
            signup_events = attach_signup_feedback_tracker(page)

            # 1. 访问注册页
            print("🧭 进入注册页...")
            page.goto("https://firecrawl.dev/", wait_until="networkidle", timeout=30000)
            time.sleep(2)

            # 查找并点击 Sign Up 按钮
            signup_selectors = [
                'a:has-text("Sign up")',
                'a:has-text("Sign Up")',
                'button:has-text("Sign up")',
                'a[href*="signup"]',
                'a[href*="register"]',
            ]

            for selector in signup_selectors:
                if page.query_selector(selector):
                    page.click(selector)
                    time.sleep(3)
                    break

            # 2. 填写注册表单
            print("📝 填写注册信息...")

            # 填写邮箱
            email_selector = fill_first_input(
                page,
                ['input[name="email"]', 'input[type="email"]', 'input[placeholder*="email" i]'],
                email
            )
            if not email_selector:
                print("❌ 未找到邮箱输入框")
                return None

            time.sleep(1)

            # 填写密码
            password_selector = fill_first_input(
                page,
                ['input[name="password"]', 'input[type="password"]'],
                password
            )
            if not password_selector:
                print("❌ 未找到密码输入框")
                return None

            time.sleep(1)

            # 3. 提交注册表单
            print("📤 提交注册...")
            submit_form(page, email_selector)
            status, message = wait_for_signup_result(page, signup_events)
            if status != "sent":
                if message:
                    print(f"❌ {message}")
                if status in {"blocked", "stalled"}:
                    if FIRECRAWL_REGISTER_HEADLESS:
                        print("💡 建议：把 FIRECRAWL_REGISTER_HEADLESS=false，再用可见浏览器重试。")
                    else:
                        print("💡 建议：切换更干净的网络/代理后重试，或在可见浏览器里手动完成注册动作。")
                return None

            # 4. 等待邮箱验证链接
            print(f"📧 等待邮箱验证链接（最多 {EMAIL_CODE_TIMEOUT} 秒）...")
            verify_url = get_verification_link(email, timeout=EMAIL_CODE_TIMEOUT)
            if not verify_url:
                print("❌ 未收到验证邮件")
                return None

            print(f"✅ 收到验证链接: {verify_url[:50]}...")

            # 5. 访问验证链接
            print("🔗 访问验证链接...")
            page.goto(verify_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)

            # 6. 检查是否需要登录
            current_url = page.url.lower()
            if 'login' in current_url or 'signin' in current_url:
                print("🔐 需要登录...")

                # 填写邮箱
                fill_first_input(
                    page,
                    ['input[name="email"]', 'input[type="email"]'],
                    email
                )
                time.sleep(1)

                # 填写密码
                fill_first_input(
                    page,
                    ['input[name="password"]', 'input[type="password"]'],
                    password
                )
                time.sleep(1)

                # 提交登录
                submit_form(page)
                time.sleep(5)

            # 7. Firecrawl 新版会先进入 onboarding，页面 HTML 里通常已经带有 apiKey。
            print("🔍 先从当前页面提取 API Key...")
            api_key = extract_api_key_from_page(page)
            if api_key:
                print(f"✅ 当前页面已拿到 API Key: {api_key[:20]}...")
            else:
                print("ℹ️  当前页面未直接拿到 API Key，继续尝试后台入口...")

            # 8. 当前页面拿不到时，再尝试后台入口。
            if not api_key:
                print("🔑 导航到 API Keys 页面...")

                # 尝试多种方式找到 API Keys 页面
                api_key_nav_selectors = [
                    'a:has-text("API Keys")',
                    'a[href*="api-key"]',
                    'a[href*="apikey"]',
                    'a[href*="keys"]',
                    'button:has-text("API Keys")',
                ]

                found_nav = False
                for selector in api_key_nav_selectors:
                    if page.query_selector(selector):
                        page.click(selector)
                        time.sleep(3)
                        found_nav = True
                        break

                if not found_nav:
                    # 尝试直接访问常见的 API Keys URL
                    possible_urls = [
                        "https://www.firecrawl.dev/app/api-keys",
                        "https://www.firecrawl.dev/app/settings",
                        "https://www.firecrawl.dev/app",
                        "https://firecrawl.dev/dashboard/api-keys",
                        "https://firecrawl.dev/api-keys",
                        "https://app.firecrawl.dev/api-keys",
                    ]

                    for url in possible_urls:
                        try:
                            page.goto(url, wait_until="networkidle", timeout=15000)
                            time.sleep(3)
                            if 'api' in page.url.lower() and 'key' in page.url.lower():
                                found_nav = True
                                break
                        except:
                            continue

                if not found_nav:
                    print("⚠️  未找到 API Keys 页面，尝试从当前页面提取...")

                # 9. 尝试提取现有的 API Key
                print("🔍 查找 API Key...")
                api_key = extract_api_key_from_page(page)

            # 10. 如果没有找到，尝试创建新的 API Key
            if not api_key:
                print("💡 未找到现有 API Key，尝试创建新的...")
                if create_api_key(page):
                    api_key = extract_api_key_from_page(page)

            if not api_key:
                print("❌ 无法获取 API Key")
                return "SUCCESS_NO_KEY"

            print(f"✅ 获取到 API Key: {api_key[:20]}...")

            # 10. 验证 API Key
            print("🧪 验证 API Key 可用性...")
            verify_result = verify_api_key(api_key)
            if verify_result is False:
                print("⚠️  API Key 验证失败，但仍然保存")
            elif verify_result is None:
                print("⚠️  API Key 可用性暂时无法确认，但更像是网络/TLS 问题，仍然保存")

            save_account(email, password, api_key)

            print(f"🎉 注册成功")
            print(f"   邮箱: {email}")
            print(f"   密码: {password}")
            print(f"   Key : {api_key}")
            return api_key

    except Exception as e:
        print(f"❌ 注册失败: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    from tavily_core import create_email
    email, password = create_email(service="firecrawl")
    register_with_browser(email, password)
