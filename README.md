# Tavily Key Generator

自动批量注册 Tavily 账户并获取 API Key。

## 功能

- Playwright 浏览器自动化，全流程无人值守
- 自动解决 Cloudflare Turnstile 验证码（CapSolver API）
- 自动接收验证邮件并完成邮箱验证
- 可插拔邮箱后端：Cloudflare Email Worker / DuckMail
- 批量注册，结果自动保存

## 快速开始

```bash
git clone https://github.com/skernelx/tavily-key-generator.git
cd tavily-key-generator
pip install -r requirements.txt
playwright install firefox
cp config.example.py config.py
# 编辑 config.py 填写配置
python main.py
```

## 配置说明

### 验证码（必配）

Tavily 注册页使用 Cloudflare Turnstile 验证码。本工具提供两种解决方式：

| 模式 | 配置值 | 成本 | 成功率 | 说明 |
|------|--------|------|--------|------|
| **CapSolver** | `"capsolver"` | ~$0.001/次 | **高** | **推荐**，稳定可靠，支持后台模式 |
| 浏览器点击 | `"browser"` | 免费 | 低 | 依赖 stealth 补丁，容易被检测，仅供尝试 |

**推荐使用 CapSolver**，注册即送余额，每次解决不到 1 分钱：

```python
CAPTCHA_SOLVER = "capsolver"
CAPSOLVER_API_KEY = "CAP-xxx"   # 从 capsolver.com 获取
```

如果想先试试免费模式（必须前台运行，成功率不高）：

```python
CAPTCHA_SOLVER = "browser"
HEADLESS = False                # 免费模式必须前台运行
```

### 邮箱后端（必配）

需要一个能接收邮件的后端来获取验证链接，二选一：

**方案 A：Cloudflare Email Worker**（自建，免费）

需要自己的域名 + Cloudflare Email Worker（catch-all 模式）。

```python
EMAIL_PROVIDER = "cloudflare"
EMAIL_DOMAIN = "example.com"
EMAIL_PREFIX = "tavily"
EMAIL_API_URL = "https://mail.example.com"
EMAIL_API_TOKEN = "your-token"
```

**方案 B：DuckMail**（第三方临时邮箱）

```python
EMAIL_PROVIDER = "duckmail"
DUCKMAIL_API_BASE = "https://api.duckmail.sbs"
DUCKMAIL_BEARER = "dk_xxx"
DUCKMAIL_DOMAIN = "duckmail.sbs"
```

## 输出

注册成功的账户保存在 `api_keys.md`：

```
邮箱,密码,API Key,时间;
```

## FAQ

**浏览器启动失败？**
运行 `playwright install firefox`。

**验证码失败？**
切换到 `CAPTCHA_SOLVER = "capsolver"`，免费浏览器模式成功率较低。

**收不到验证邮件？**
Cloudflare 模式检查 Worker 是否部署正确；DuckMail 模式检查 API Key 是否有效。

## License

MIT
