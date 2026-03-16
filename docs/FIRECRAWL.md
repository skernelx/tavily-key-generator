# Firecrawl 自动注册说明

## 功能特点

- 自动注册 Firecrawl 账号
- 自动处理邮箱验证
- 自动提取 API Key
- 真实 API 调用验证
- 支持并发注册

## 使用方法

### 1. 快速开始

```bash
python3 run.py
```

启动后选择 `2. Firecrawl`，然后按提示操作。

### 2. 单独测试

```bash
python3 test_firecrawl.py
```

### 3. 直接调用

```python
from firecrawl_core import register
from mail_provider import create_email

email, password = create_email(service="firecrawl")
api_key = register(email, password)
```

## 注册流程

1. 访问 firecrawl.dev
2. 点击 Sign Up
3. 填写邮箱和密码
4. 等待验证邮件
5. 访问验证链接
6. 自动登录（如需要）
7. 导航到 API Keys 页面
8. 提取或创建 API Key
9. 验证 API Key 可用性

## API Key 验证

使用 Firecrawl v2 API 进行验证：

```bash
curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

## 输出文件

注册成功后，账号信息会保存到：

```
firecrawl_accounts.txt
```

格式：
```
email,password,api_key
```

## 注意事项

1. **邮箱配置**：需要配置有效的邮箱 API（Cloudflare 或 DuckMail）
2. **验证链接**：Firecrawl 使用邮件验证链接，不是验证码
3. **API Key 提取**：如果自动提取失败，可能需要手动调整选择器
4. **免费额度**：Firecrawl 免费账号有使用限制
5. **学生计划**：学生可申请 20,000 免费 credits

## 常见问题

### Q: 无法找到 API Key？

A: 可能的原因：
- 页面结构变化，需要更新选择器
- 需要手动创建 API Key
- 页面加载时间不够

### Q: API Key 验证失败？

A: 可能的原因：
- Key 尚未激活
- 账号需要额外验证
- API 配额已用完

### Q: 邮件验证超时？

A: 可能的原因：
- 邮箱 API 配置问题
- Firecrawl 邮件发送延迟
- 邮件被过滤
- Firecrawl 默认后台运行；如果终端出现 `Security check failed`，再把 `FIRECRAWL_REGISTER_HEADLESS=false` 临时切到前台浏览器排查

## 技术细节

- 使用 Camoufox 反检测浏览器
- 支持 headless 模式
- 自动处理页面跳转
- 智能选择器匹配
- 并发安全的文件写入

## 与 Tavily 的区别

| 特性 | Tavily | Firecrawl |
|------|--------|-----------|
| 验证方式 | 6位验证码 | 邮件链接 |
| Captcha | Turnstile | 无 |
| Solver | 需要 | 不需要 |
| 密码页 | 有 challenge | 无 |
| API 前缀 | tvly- | fc- |

## 相关链接

- [Firecrawl 官网](https://firecrawl.dev)
- [Firecrawl API 文档](https://docs.firecrawl.dev)
- [Firecrawl 学生计划](https://www.firecrawl.dev/student-program)
