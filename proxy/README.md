# Multi-Service API Proxy

把多个 **Tavily** 和 **Firecrawl** API Key 做成统一代理池，对外暴露固定入口、独立 Token，并提供一个更适合日常维护的可视化控制台。

当前这版 `proxy/` 已支持：

- Tavily / Firecrawl **分服务隔离**
- 独立 Key 池、独立 Token 池
- 顶部卡片切换 + 单服务详情面板
- Tavily 真实额度同步：`GET /usage`
- Firecrawl 真实额度同步：
  - `GET /v2/team/credit-usage`
  - `GET /v2/team/credit-usage/historical?byApiKey=true`
- 本地代理调用统计、成功率、延迟统计

## 控制台截图

### 工作台切换

![Proxy Workspace Switcher](../docs/screenshots/proxy-workspace-switcher.jpg)

### Key 池详情

![Proxy Key Pool](../docs/screenshots/proxy-key-pool.jpg)

## Docker Image

当前兼容镜像名仍沿用旧名字：

```text
docker.io/skernelx/tavily-proxy:latest
```

拉取方式：

```bash
docker pull skernelx/tavily-proxy:latest
```

## 功能概览

- Tavily 独立代理入口：
  - `POST /api/search`
  - `POST /api/extract`
- Firecrawl 独立代理入口：
  - `/firecrawl/*`
  - 示例：`POST /firecrawl/v2/scrape`
- 独立代理 Token：
  - Tavily Token 前缀：`tvly-`
  - Firecrawl Token 前缀：`fctk-`
- 控制台支持：
  - 按服务导入 Key
  - 按服务创建 Token
  - 按服务同步真实额度
  - 按服务查看 Key 池与用量
  - 顶部一键切换 Tavily / Firecrawl 工作台

## 和注册器如何联动

注册器上传到 proxy 时，会直接调用：

```json
{
  "key": "fc-xxxx",
  "email": "fc-xxx@example.com",
  "service": "firecrawl"
}
```

也就是说：

- Tavily 注册结果上传时会写入 Tavily 池
- Firecrawl 注册结果上传时会写入 Firecrawl 池
- 服务器不需要再靠 key 前缀猜测服务

这条链路已经做过真实验证：Firecrawl 上传后会被 `/api/keys`
识别成 `service=firecrawl`，不会落到 Tavily 池里。

## 推荐部署方式

### 1. 直接使用 Docker Hub 镜像

```bash
mkdir -p tavily-proxy-data

docker run -d \
  --name tavily-proxy \
  --restart unless-stopped \
  -p 9874:9874 \
  -e ADMIN_PASSWORD=your-admin-password \
  -v $(pwd)/tavily-proxy-data:/app/data \
  skernelx/tavily-proxy:latest
```

启动后访问：

```text
http://localhost:9874
```

### 2. 使用 docker compose

```bash
cd proxy
docker compose up -d
```

默认 compose 会：

- 暴露端口 `9874`
- 将数据库挂载到 `./data`
- 使用 `ADMIN_PASSWORD` 作为控制台密码

### 3. 本地源码运行

```bash
cd proxy
pip install -r requirements.txt
ADMIN_PASSWORD=your-admin-password uvicorn server:app --host 0.0.0.0 --port 9874
```

## 更新方式

如果你已经在服务器上跑了旧版本，推荐直接拉新镜像后重启容器：

```bash
docker pull skernelx/tavily-proxy:latest

docker rm -f tavily-proxy

docker run -d \
  --name tavily-proxy \
  --restart unless-stopped \
  -p 9874:9874 \
  -e ADMIN_PASSWORD=your-admin-password \
  -v /your/data/path:/app/data \
  skernelx/tavily-proxy:latest
```

只要保留原来的数据卷目录，Key、Token 和控制台密码都会继续保留。旧库会自动迁移出 `service` 字段，历史 Tavily 数据会被标记为 `tavily`。

## 控制台里能看到什么

控制台现在不是上下两个长栏目硬堆，而是：

- 顶部服务卡片切换区
- 首屏当前工作台概览
- 下方当前服务的完整详情面板

每个服务面板里都能看到：

### 1. Tavily 栏目

- Key 池
- Token 池
- 真实额度汇总
- Tavily `/usage` 同步状态
- 代理侧成功 / 失败 / 月度统计

### 2. Firecrawl 栏目

- Key 池
- Token 池
- Firecrawl credits 汇总
- Firecrawl credits 同步状态
- 代理侧成功 / 失败 / 月度统计

## 使用流程

1. 启动 proxy
2. 打开控制台并登录
3. 在 Tavily 或 Firecrawl 栏目导入对应 Key
4. 在对应栏目创建 Token
5. 把该 Token 发给你的下游程序
6. 用对应的代理端点发起请求
7. 在控制台查看该服务的真实额度和代理统计

## API 调用方式

认证方式支持两种：

- `Authorization: Bearer YOUR_TOKEN`
- body 里传 `api_key`

### Tavily 示例

```bash
curl -X POST http://localhost:9874/api/search \
  -H "Authorization: Bearer YOUR_TAVILY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "hello world", "max_results": 1}'
```

```bash
curl -X POST http://localhost:9874/api/extract \
  -H "Authorization: Bearer YOUR_TAVILY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'
```

### Firecrawl 示例

```bash
curl -X POST http://localhost:9874/firecrawl/v2/scrape \
  -H "Authorization: Bearer YOUR_FIRECRAWL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "formats": ["markdown"]}'
```

```bash
curl -X GET http://localhost:9874/firecrawl/v2/team/credit-usage \
  -H "Authorization: Bearer YOUR_FIRECRAWL_TOKEN"
```

## 管理 API

所有管理 API 需要：

- `X-Admin-Password: your-admin-password`

或者：

- `Authorization: Bearer your-admin-password`

### 常用管理端点

- `GET /api/stats`
  返回 Tavily / Firecrawl 双服务概览

- `GET /api/keys?service=tavily`
- `GET /api/keys?service=firecrawl`
  返回指定服务的 Key 列表

- `POST /api/keys`
  body 里传 `service`

- `PUT /api/keys/{id}/toggle`
  启用 / 禁用某个 Key

- `DELETE /api/keys/{id}`
  删除 Key

- `GET /api/tokens?service=tavily`
- `GET /api/tokens?service=firecrawl`
  返回指定服务的 Token 列表

- `POST /api/tokens`
  body 里传 `service`

- `DELETE /api/tokens/{id}`
  删除 Token

- `POST /api/usage/sync`
  body 里传 `service`

- `PUT /api/password`
  修改控制台密码

## 配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ADMIN_PASSWORD` | `admin` | 控制台登录密码 |
| `USAGE_SYNC_TTL_SECONDS` | `300` | 真实额度缓存秒数 |
| `USAGE_SYNC_CONCURRENCY` | `4` | 并发同步额度的最大 Key 数 |

## 数据持久化

SQLite 数据库默认保存在：

```text
/app/data/proxy.db
```

所以容器部署时一定要挂载数据卷，例如：

```bash
-v /your/data/path:/app/data
```

## 适合什么场景

- 你有多组 Tavily / Firecrawl Key，想统一出口
- 你不想把真实 API Key 直接发给下游程序
- 你希望 Tavily 和 Firecrawl 各自独立统计、独立授权
- 你想让注册器自动把新拿到的 Key 上传进对应池子

## 注意事项

- Tavily 真实额度依赖官方 `/usage`
- Firecrawl 当前主要返回账户级 credits 视图，控制台会优先展示账户额度
- 旧数据库会自动迁移 `service` 字段，但旧数据默认视为 Tavily
