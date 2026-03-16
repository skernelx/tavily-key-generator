# Tavily Key Generator - Rebuilt Edition

[English Guide](./README_EN.md)

完全重构版 Tavily 自动注册工具。

这版不再依赖早期那种不稳定的旧脚本链路，而是统一切到：

- 本地真实浏览器注册
- 本地 Turnstile Solver
- 邮箱 API 自动收验证码
- 获取 API Key 后立即真实调用 Tavily API 验证

目标很直接：把 Tavily / Auth0 / Cloudflare 这条注册链路收口成一个真正可用、可并发、可后台运行的一键启动工具。

Cloudflare 通用无限别名域名邮箱教程见：
[Cloudflare 邮件设置详解](./docs/Cloudflare%E9%82%AE%E4%BB%B6%E8%AE%BE%E7%BD%AE%E8%AF%A6%E8%A7%A3.md)

英文版说明见：
[Cloudflare Mail Setup Guide](./docs/Cloudflare-Mail-Setup-Guide.md)

## Features

- 单启动台模式，不需要手动拼命令参数
- 启动时自动检查虚拟环境、依赖和浏览器
- 支持 Cloudflare 自定义域名邮箱 API
- 支持 DuckMail API
- 支持多域名配置，启动时可自由选择
- 支持并发注册
- 默认后台浏览器运行
- 获取到 API Key 后自动真实验证
- 可选自动上传到你的 key 池服务器
- Windows / macOS / Linux 兼容启动

## Screenshots

### 并发注册与真实验证

![Registration Success](./docs/screenshots/registration-success.jpg)

### Proxy 控制台总览

![Proxy Overview Usage](./docs/screenshots/proxy-overview-usage.jpg)

### Proxy Key 池详情

![Proxy Key Pool](./docs/screenshots/proxy-key-pool.jpg)

## Quick Start

### 1. Clone

```bash
git clone https://github.com/skernelx/tavily-key-generator.git
cd tavily-key-generator
```

### 2. Configure

```bash
cp .env.example .env
```

编辑 `.env`，填好你的邮箱链路和可选上传配置。

### 3. Run

macOS / Linux:

```bash
python3 run.py
```

或：

```bash
./start_auto.sh
```

Windows:

```bat
start_auto.bat
```

## How It Works

程序启动后会自动执行：

1. 创建或复用 `venv`
2. 安装 Python 依赖
3. 安装 Camoufox / Playwright 浏览器依赖
4. 读取 `.env`
5. 检查邮箱 provider 配置
6. 如果配置了多个域名，提示选择本轮使用的域名
7. 输入注册数量
8. 输入并发数
9. 选择是否自动上传到服务器
10. 自动启动本地 Solver
11. 自动处理邮箱验证码与密码设置
12. 遇到随机 challenge 时自动恢复
13. 提取 API Key
14. 真实调用 Tavily API 验证
15. 保存到 `accounts.txt`
16. 如已开启上传，则继续上传到服务器

## Runtime Flow

```text
run.py
  -> load .env
  -> choose domain
  -> input count / concurrency
  -> choose upload or not
  -> create mailbox
  -> open Tavily signup page
  -> solve Turnstile locally
  -> receive email code
  -> set password
  -> recover random password-page challenge
  -> enter Tavily dashboard
  -> extract API key
  -> verify API key with real API call
  -> save / upload
```

## Configuration

完整配置示例见 [`.env.example`](./.env.example)。

### Cloudflare Mail API

```env
EMAIL_PROVIDER=cloudflare
EMAIL_API_URL=https://your-mail-api.example.com
EMAIL_API_TOKEN=replace-with-your-token
EMAIL_DOMAIN=example.com
EMAIL_DOMAINS=example.com,example.org
```

说明：

- 单域名可只填 `EMAIL_DOMAIN`
- 多域名可填 `EMAIL_DOMAINS`
- 启动时会提示选择本轮使用的域名

### DuckMail API

```env
EMAIL_PROVIDER=duckmail
DUCKMAIL_API_URL=https://api.duckmail.sbs
DUCKMAIL_API_KEY=
DUCKMAIL_DOMAIN=
DUCKMAIL_DOMAINS=
```

说明：

- 可使用单域名或多域名配置
- 如果你有 DuckMail 私有域名和 API Key，直接填入即可
- 公开 DuckMail 域名可以测试收信链路，但不保证能通过 Tavily 风控

### Upload to Your Server

```env
SERVER_URL=https://your-server.example.com
SERVER_ADMIN_PASSWORD=replace-with-your-admin-password
DEFAULT_UPLOAD=true
```

说明：

- `DEFAULT_UPLOAD=true` 表示启动台默认开启自动上传
- 真正是否上传，仍以本轮启动时的选择为准

### Runtime Options

```env
DEFAULT_COUNT=1
DEFAULT_CONCURRENCY=2
DEFAULT_DELAY=10
REGISTER_HEADLESS=true
EMAIL_CODE_TIMEOUT=90
API_KEY_TIMEOUT=20
EMAIL_POLL_INTERVAL=3
SOLVER_PORT=5073
SOLVER_THREADS=1
```

说明：

- `REGISTER_HEADLESS=true` 表示浏览器后台运行
- `SOLVER_THREADS` 最终会自动取 `max(SOLVER_THREADS, 本轮并发数)`
- 普通使用场景下不需要额外传命令参数

## Output

注册成功后，结果会写入：

```text
accounts.txt
```

格式：

```text
email,password,api_key
email,password,api_key
```

## Real-World Validation

当前主线已经做过真实回归验证：

- Cloudflare 邮箱链路可跑通完整注册
- 邮箱验证码可自动读取
- 获取到 API Key 后会立即做真实 API 调用验证
- 并发注册已做过真实回归
- 密码页随机 challenge 已补恢复逻辑，并已真测通过

最近一次回归里，密码页两次都复现了“提交后未立即跳转”的随机 challenge 场景，恢复逻辑都成功拉回流程，并最终拿到可用 key。

## Known Limitations

### DuckMail Public Domains

DuckMail 公开域名当前的状态是：

- 创建邮箱可以
- 接收 6 位验证码可以
- 但 Tavily 在密码页可能直接风控拦截

常见页面提示：

```text
Suspicious activity detected
```

如果你要跑通完整注册，建议优先使用：

- Cloudflare 自定义域名邮箱
- DuckMail 私有域名 + API Key

### First Run on New Machine

首次换机器运行时，建议先单账号跑通一遍，再开并发。

因为首次运行会自动下载浏览器依赖，且不同机器的本地网络环境、代理环境、系统依赖可能不同。

## Project Structure

```text
.
├── run.py                    # 唯一推荐入口
├── tavily_core.py            # 统一注册入口，内部转发到浏览器主链路
├── tavily_browser_solver.py  # 浏览器注册主逻辑
├── api_solver.py             # 本地 Turnstile Solver
├── mail_provider.py          # 邮箱 provider 抽象
├── config.py                 # .env / 环境变量读取
├── start_auto.sh             # macOS / Linux 启动脚本
├── start_auto.bat            # Windows 启动脚本
├── proxy/                    # 可选的 Tavily key 池代理服务
└── README.md
```

## Module Notes

仓库里有一些不是主入口、但仍然是运行时依赖的模块：

- `tavily_core.py`
  现在是兼容层，负责把统一入口转发到浏览器注册主链路。

- `browser_configs.py`
  `api_solver.py` 的浏览器配置辅助模块。

- `db_results.py`
  `api_solver.py` 的结果存储辅助模块。

- `proxy/`
  独立可选模块，用于把多个 Tavily key 做成统一代理池。


## Optional Proxy Service

如果你希望把注册出来的 key 接成统一池子，可以使用 `proxy/`。

启动方式：

```bash
cd proxy
docker compose up -d
```

详细说明见 [`proxy/README.md`](./proxy/README.md)。

## Recommended Usage

如果你只是想批量拿 key，最简单的使用方式就是：

1. 配好 `.env`
2. 运行 `python3 run.py`
3. 选择域名
4. 输入注册数量
5. 输入并发数
6. 看 `accounts.txt`

如果你有自己的 key 池服务器，再把自动上传或者 `proxy/` 接上即可。

## Disclaimer

本项目仅供自动化测试、研究和个人学习使用。

请自行评估目标站点的服务条款、风控策略和账号使用风险。
