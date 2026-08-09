# 广金大师兄最终可用性审计

审计时间：2026-08-09（Asia/Shanghai）

审计范围：`/chat`、`/map`、`/canteens`、`/notifications`、`/tasks`、`/processes`、`/profile`、`/admin`、认证、移动端、后端 Agent、数据库与外部服务配置。

## 运行证据

- 前端监听：`127.0.0.1:5173`，Vite 开发代理已把 `/api` 与 `/health` 转发到 `127.0.0.1:8000`。
- 后端监听：`127.0.0.1:8000`；`GET /health` 返回 `ok`，`GET /api/agent/status` 返回后端、数据库正常，模型为 `deepseek-v4-flash` 且已配置。
- 数据库：当前本地开发环境使用 SQLite；未发现 5432 端口上的 PostgreSQL 监听。这不妨碍本地功能验收，但生产环境仍应使用 PostgreSQL。
- 密钥边界：前端 API 客户端未读取 DeepSeek Key；模型 Key 由后端 Settings 从 `.env` 读取；状态接口不返回 Key。
- 官方模型资料：DeepSeek 官方文档确认 V4 的思考模式通过 `extra_body.thinking.type=enabled` 开启，OpenAI 格式的强度参数为 `reasoning_effort=high|max`；思考模式不使用 temperature。旧名 `deepseek-chat`/`deepseek-reasoner` 已于 2026-07-24 到期，应继续使用 `deepseek-v4-flash` 或 `deepseek-v4-pro`。

## P0：阻碍核心闭环

1. `/chat` 只有非流式 `POST /api/agent/chat`；页面在完整响应返回前没有真实进度，无法停止生成。
2. 消息使用纯 `<p>` 渲染，Markdown 标记被原样显示，缺少脚本/恶意链接的渲染边界。
3. Agent Planner 由 intent 的固定映射生成，分类器返回的计划没有成为执行依据；一次请求只执行一轮，不能根据工具结果重规划。
4. DeepSeek 客户端显式关闭 thinking，未使用用户要求的 `reasoning_effort`；页面也没有安全的阶段进度。
5. 通知可解析并保存任务，但没有真正的“设提醒、加入日历、保存便签”动作面板。
6. 数据库没有独立 Reminder、Note、CampusCollege、CampusFact、CampusPathNode/Edge 模型，导致提醒触发、便签持久化、学院口径与校内路线都无法形成可靠闭环。
7. 清远现有数据不足以回答 13 个“2+2”学院的统计口径、北饭/南饭/西饭的不同核验状态，也无法可靠计算“北区教学楼→北饭”。

## P1：明显影响体验和移动可用性

1. 桌面聊天头部占用过高，技术状态、intent 与工具数据默认暴露；助手消息像大卡片，不符合成熟聊天产品的阅读节奏。
2. 输入框不自动增高，不支持 PDF/TXT 拖放；无复制、重新生成、快捷动作与移动端会话抽屉。
3. 移动端把会话列表直接堆在消息区上方；软键盘出现时编辑区可能挤压内容，缺少 `100dvh` 和安全区适配。
4. 工具卡默认呈现技术字段，用户看不到自然的“已找到/已完成”摘要。
5. 首页/仪表盘没有统一呈现今日任务、即将提醒、最近便签和常用地点。
6. localhost 下不能真实提供 Web Push；现状也没有明确区分站内提醒、浏览器通知与 HTTPS Web Push。

## P2：产品化与运营能力

1. 管理端缺少从官方 URL 提取“事实候选→人工确认→结构化 CampusFact”的研究工作台。
2. 地图地点维护已有坐标质量字段，但缺少校内路径图节点和边的可视化维护。
3. 生产 HTTPS 部署、移动真机通知和公网域名依赖外部平台状态，若本轮无法访问应标为 `BLOCKED_EXTERNAL`，不能宣称已完成。
4. 当前缺少覆盖桌面 1440×900 与移动 390×844 的完整持久化 E2E 证据。

## 本轮修复顺序

1. 先补数据模型、迁移、统一 API 与测试边界。
2. 接通流式 Agent，启用 DeepSeek thinking，只输出安全阶段，不保存或展示 `reasoning_content`。
3. 重做聊天呈现和编辑器，并把通知、任务、提醒、便签串成真实动作。
4. 导入有来源、有口径、有核验状态的清远结构化事实，校内路径只在节点/边可核验时返回。
5. 完成 LAN 启动脚本、响应式与 E2E 验证，再进行安全扫描、提交和推送。
