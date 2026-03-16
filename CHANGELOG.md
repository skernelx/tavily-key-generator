# 项目更新日志

## 2026-03-16 - 添加 Firecrawl 支持

### 新增功能

1. **Firecrawl 自动注册**
   - 新增 `firecrawl_browser_solver.py` - Firecrawl 浏览器自动化模块
   - 新增 `firecrawl_core.py` - Firecrawl 注册统一入口
   - 支持邮件验证链接自动处理
   - 支持 API Key 自动提取和验证

2. **服务选择功能**
   - 启动时可选择 Tavily 或 Firecrawl
   - 根据服务自动调整流程（Firecrawl 不需要 Solver）
   - 独立的输出文件（`accounts.txt` vs `firecrawl_accounts.txt`）

3. **文档更新**
   - 更新主 README 说明多服务支持
   - 新增 `docs/FIRECRAWL.md` 详细说明
   - 新增 `test_firecrawl.py` 测试脚本

### 技术改进

1. **代码重构**
   - `run.py` 支持服务参数传递
   - `register_one()` 根据服务调用不同注册函数
   - `do_register_parallel()` 支持服务选择
   - 条件性启动 Solver（仅 Tavily 需要）

2. **邮箱验证增强**
   - `mail_provider.py` 已支持验证链接提取
   - 适配 Firecrawl 的邮件验证流程

3. **API 验证**
   - Firecrawl API v2 验证
   - 使用 `/v2/scrape` 端点测试
   - Bearer token 认证方式

### 文件变更

**新增文件**:
- `firecrawl_browser_solver.py` - Firecrawl 注册核心逻辑
- `firecrawl_core.py` - Firecrawl 入口模块
- `test_firecrawl.py` - 测试脚本
- `docs/FIRECRAWL.md` - Firecrawl 使用文档
- `CHANGELOG.md` - 本文件

**修改文件**:
- `run.py` - 添加服务选择和条件性 Solver 启动
- `README.md` - 更新为多服务说明
- `.gitignore` - 添加 `firecrawl_accounts.txt`

**备份**:
- 原项目已备份至 `/Users/wf/tavily-key-generator-backup`

### 使用示例

```bash
# 启动程序
python3 run.py

# 选择服务
请选择要注册的服务：
  1. Tavily
  2. Firecrawl
请输入选项 (1-2，默认 1): 2

# 后续流程与原来相同
```

### 兼容性

- 完全向后兼容原有 Tavily 功能
- 不影响现有配置和脚本
- 可独立使用 Tavily 或 Firecrawl

### 已知限制

1. Firecrawl API Key 提取依赖页面结构，可能需要根据网站更新调整
2. 免费账号有使用限制
3. 首次运行建议单账号测试

### 下一步计划

- [ ] 添加更多服务支持
- [ ] 优化 API Key 提取逻辑
- [ ] 添加更详细的错误处理
- [ ] 支持自定义 API 验证端点
