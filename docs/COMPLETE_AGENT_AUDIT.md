# 广金大师兄完整 Agent 审计

审计日期：2026-08-04

审计对象：`codex/2026-campus-map-agent`，现有 PR #1

审计原则：以当前代码、数据库迁移、自动测试和本机运行结果为证据；没有外部凭据或可靠数据的能力不记作已上线。

## 结论

项目已是 React + FastAPI 的真实全栈网站，不再由 Streamlit 提供入口。核心闭环包括账户、Agent 多轮对话、校园事实工具、通知转任务、任务管理、ICS、办事流程和管理员知识维护。Agent 已从单个服务类拆为明确的编排管线，工具执行与校验结果可持久化审计。

真实 DeepSeek 四轮对话和隔离 Mock 的完整浏览器流程均已通过。真实高德地图代码、后端安全代理、地理编码和步行路线已经实现，但本机没有高德三项凭据，且种子地点没有经核验 GPS，因此当前页面诚实显示“需要配置高德地图凭据”，不把示意点当真实地图。

## 功能审计矩阵

| 范围 | 当前状态 | 证据与边界 |
| --- | --- | --- |
| 注册/登录/退出 | 可用 | HttpOnly Cookie、短 Access、可撤销 Refresh；E2E 覆盖刷新与重登 |
| 用户隔离 | 可用 | 任务、对话、上传记录按 `user_id` 查询；后端测试覆盖 |
| 用户偏好 | 可用 | 称呼、称呼风格、常用地点、无障碍说明可保存；校区/地点一致性校验 |
| 真实模型聊天 | 可用 | 后端读取 DeepSeek 环境变量；四轮人工冒烟 200，`degraded=false` |
| 多轮记忆 | 可用 | 最近 20 条历史进入模型；消息按会话落库；小明记忆测试通过 |
| Agent 编排 | 可用 | observe/classify/plan/execute/verify/confirm/remember/respond |
| 校园地点 | 有条件可用 | 文本搜索、详情、分类可用；真实地图依赖高德凭据和核验坐标 |
| 饭堂与餐品 | 历史查询可用 | 只返回有来源/状态的历史档口资料；无可靠当日菜单时明确告知 |
| 通知转任务 | 可用 | TXT/PDF 解析、可编辑预览、逐项确认、批量保存；原文件不落盘 |
| 任务/日历 | 可用 | CRUD、批量状态、临期/逾期、ICS 单/多任务、双提醒 |
| 校园办事 | 可用但数据有限 | 检索、结构化详情、来源、确认后转任务；当前只有少量待核验资料 |
| 知识检索 | 可用但语料有限 | 校区过滤、低匹配抑制、来源/状态返回；管理员 CRUD |
| 管理后台 | 可用 | RBAC；用户、校区、地点、饭堂、流程、来源、知识、反馈、日志 |
| OCR/语音/主动推送 | 未实现 | UI 不再把占位按钮表示为可用；需要外部服务和产品授权 |
| 公网部署 | 未完成 | 当前没有已验证公开 URL；本轮只准备代码与容器配置 |

## Agent 架构

`backend/app/agents/` 的职责如下：

- `memory.py`：读取用户、校区、偏好、最近历史和待办观察。
- `intent_classifier.py`：使用模型结构化分类，解析失败时有确定性回退。
- `planner.py`：将意图映射到工具，标注知识需求、副作用确认、缺失信息和风险。
- `executor.py`：只经注册表执行工具，不允许模型直接访问数据库或网络。
- `verifier.py`：检查校区一致性、来源和工具结果完整性。
- `persona.py` / `prompts.py`：动态中国时间、校区、称呼与事实边界。
- `orchestrator.py`：编排全流程，保存消息、来源、工具卡片和 `ToolExecution`。

支持的意图共 15 类：`general_chat`、`learning_guidance`、`campus_life_guidance`、`campus_location_search`、`nearby_location_search`、`campus_navigation`、`canteen_search`、`food_search`、`notification_to_tasks`、`task_management`、`campus_process`、`document_analysis`、`calendar_export`、`data_feedback`、`out_of_scope`。

注册工具共 41 个，分为地点/路线、饭堂、任务、通知、日历、流程、知识和用户偏好八组。统一返回 `tool_name`、`success`、`data`、`summary`、`sources`、`verification`、`error`、`requires_user_action`。写操作必须由 API/UI 显式传入确认，不允许 Agent 静默删除、完成或批量写入。

## 数据与真实性

- 新增 `KnowledgeDocument`、`UploadedDocument`、`ToolExecution`、`UserPreference`，以及办事流程的适用人群、地点、开放时间、线上入口、可信度和数据状态字段。
- 上传文件仅保存文件名、类型、大小、SHA-256 和解析状态；不保存原始正文或文件。
- 地点只有同时具备经核验 GPS 且非 `needs_verification` 时才创建地图 Marker。
- 高德 `securityJsCode` 和 WebService Key 只在后端；浏览器只持有允许公开的 JS Key，并经 `/_AMapService` 同源代理。
- 当前没有可靠实时饭堂菜单、价格、营业状态或完整三校区坐标。管理员必须补充来源和核验证据后才能把记录标为已核验。

## 安全审计

- `.env`、数据库、上传、前端构建和测试产物均在 `.gitignore`；浏览器代码不读取 DeepSeek Key。
- 生产环境拒绝弱 JWT Secret 和非安全 Cookie；CORS 不使用带凭据的通配符。
- 密码 Argon2 哈希；Refresh Token 仅存哈希；管理员权限由后端依赖强制。
- Key 模式扫描未发现真实 `sk-` 凭据；响应、状态接口和日志不返回 Key。
- `npm audit --omit=dev` 仍报告 React Router RSC 专用 CSRF 公告。当前应用是 BrowserRouter 纯 SPA，不使用 RSC、SSR 或 Server Action，因此受影响路径未启用；上游发布可用修复版本后应立即升级。不能把该告警记作“扫描全绿”。

## 验证结果

- Python compileall：通过。
- 后端 Pytest：56 passed。
- TypeScript：通过。
- ESLint：0 warning / 0 error。
- 前端 Vitest：20 passed。
- Vite production build：通过。
- Playwright：1 passed，覆盖完整用户闭环。
- 本机真实 DeepSeek：四轮 200，多轮记忆通过。
- Alembic：本地库与隔离空库均升级到 `20260804_03`。
- Docker：本机无 Docker CLI，未伪造运行结果；Compose 仍由 CI/有 Docker 的环境验证。

## 外部阻塞

真正开放以下能力仍需项目所有者或学校提供：高德 JS Key、securityJsCode、WebService Key；三校区经核验 GPS/营业数据/办事资料；邮件或 Push 服务；生产 PostgreSQL 与部署平台权限。DeepSeek Key 已在本机配置，严禁复制到文档、前端或 Git。
