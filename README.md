[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/skernelx-tavily-key-generator-badge.png)](https://mseep.ai/app/skernelx-tavily-key-generator)

# API Key Generator - Multi-Service Edition

[English Guide](./README_EN.md)

这是一个多服务注册器与聚合 API 上游工具，聚焦三件事：

- 注册 `Tavily（暂时无法注册）` / `Firecrawl` / `Exa` key
- 验证 key 是否真实可用，并把可用 key 提供给统一搜索层

## 当前状态

- `Firecrawl`：可用
- `Exa`：可用
- `Tavily`：按当前项目这轮本地测试，官网已关闭邮件注册入口，暂不可用

它不是 `MySearch` 的正式产品仓库。  
如果你要部署公开可用的统一搜索控制台、MCP、Skill 和 Social / X
接入，请直接使用独立项目：

- [MySearch-Proxy](https://github.com/skernelx/MySearch-Proxy)

## 这个仓库负责什么

- 本地真实浏览器注册
- 本地 Turnstile Solver
- 邮箱 API 自动收验证码 / 验证链接
- 提取到 API Key 后立刻做真实调用验证
- 可选自动上传到统一代理池
- 可作为 `MySearch` / `MySearch-Proxy` 的 provider 上游之一

## Features

- 多服务启动台：启动时可选择 Tavily / Firecrawl / Exa
- 自动环境准备：自动检查 `venv`、依赖和浏览器
- 邮箱链路统一：支持 Cloudflare Mail API 和 DuckMail
- 多域名可选：启动时选择本轮注册用的域名
- 并发注册：支持批量和并发执行
- 后台浏览器模式：默认 headless，必要时可切前台排查
- 真实可用性验证：拿到 key 后马上调用官方接口
- 自动上传到代理池：上传时会带上服务标记，服务端能自动识别 Firecrawl / Exa / Tavily 并写入对应池子
- 适合作为统一搜索网关的上游：给 `MySearch-Proxy` 提供稳定的 key 来源
- 跨平台启动：Windows / macOS / Linux 都能直接跑

## 配套工作台预览

### MySearch Proxy 首屏

![MySearch Console Hero](./docs/screenshots/mysearch-console-hero.jpg)

### MySearch Proxy 工作台

![MySearch Console Workspaces](./docs/screenshots/mysearch-console-workspaces.jpg)

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

编辑 `.env`，填好邮箱配置和可选上传配置。

如果已经配置了 `SERVER_URL` 和 `SERVER_ADMIN_PASSWORD`，注册成功后可以自动上传。

### 3. Run

macOS / Linux:

```bash
python3 run.py
```

或者：

```bash
./start_auto.sh
```

Windows:

```bat
start_auto.bat
```

启动后当前可选：

```text
1. Tavily
2. Firecrawl
3. Exa
```

补充说明：

- `Exa` 注册成功后会保存到 `exa_accounts.txt`
- `Exa` 的格式是 `email,EMAIL_OTP_ONLY,api_key`
- `Tavily` 选项目前仍保留在启动台里，但当前状态暂不可用

## 推荐搭配方式

如果你希望把注册出来的 key 接成公开可用的统一搜索服务，推荐直接搭配：

- [MySearch-Proxy](https://github.com/skernelx/MySearch-Proxy)

它负责：

- 统一控制台
- Tavily / Firecrawl / Social / X 统一接线
- MCP + Skill 安装说明
- 官方接口与 compatible 网关双接入
- 面向 Codex / Claude Code 的最终接入方式

当前仓库则继续专注于：

- 注册可用 key
- 做真实可用性验证
- 提供聚合 API 上游能力

`proxy/` 目录现在只保留一份迁移说明 README，不再包含本地可运行实现。

## MySearch 的关系

这里的 `tavily-key-generator` 只负责：

- 注册 Firecrawl / Exa key
- 验证 key 是否真实可用
- 提供可选聚合 API，供 `MySearch` / `MySearch-Proxy` 调用

`MySearch` 自己的安装、MCP 工具、统一控制台、social gateway、Codex /
Claude Code 接入说明，统一放在：

- [MySearch-Proxy](https://github.com/skernelx/MySearch-Proxy)
