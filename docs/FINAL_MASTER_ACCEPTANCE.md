# Final Master Acceptance

验收日期：2026-08-09。状态只使用 `PASS`、`FAIL`、`BLOCKED_EXTERNAL`；当前没有可控 `FAIL`。

| Module | Status | Evidence |
|---|---|---|
| Agent Core | PASS | `agent_runs` / `agent_run_steps` 已迁移到 `20260809_09`；执行状态和公开步骤可查询。 |
| Agent UX | PASS | Chat 展示公开计划、工具开始/结束、核验状态和恢复动作，不暴露内部推理。 |
| Agent Tool Loop | PASS | 每步消费前序工具结果，限制最多 6 次工具调用；通知校验、日历和多点路线均使用真实前序 ID。 |
| Agent Replan | PASS | 工具缺失/失败后进入有限重规划分支；最终必须经过独立 verifier，失败不会冒充完成。 |
| Agent Memory | PASS | 最近对话历史进入模型上下文；Mock 与真实 DeepSeek 两轮“小明”测试均通过。 |
| Agent Action Cards | PASS | 提醒、便签、通知任务、流程、学习笔记和导航均返回结构化 Action Card；写入需要本次 Run 的有效确认。 |
| Chat | PASS | 真实 DeepSeek 冒烟 4/4 返回 200、`degraded=false`；Markdown、等待态、错误态和自动滚动通过构建/E2E。 |
| Current Location | PASS | 授权、拒绝、重试和低精度知情继续已实现；原始 GPS 不写入 Agent Run。 |
| Campus Navigation | PASS | 已核验目的地使用浏览器高德真实步行路线；同一 Run 可在授权位置后续跑，多目标按用户点名顺序执行。 |
| Campus POI | PASS | 清远图书馆、敏学楼、南区体育馆、快递点、明湖、木兰广场等 provider POI 已入库并保留来源状态。 |
| Qingyuan Dormitories | PASS | 官方口径南区 1–5、北区 1–8，共 13 条独立记录；聚合旧记录已停用且无别名冲突。 |
| Qingyuan Teaching Buildings | BLOCKED_EXTERNAL | 官方名称已入库；北教/南教精确入口缺少可独立复核的公开证据，保持未核验并禁止猜测路线。 |
| Qingyuan Canteens | BLOCKED_EXTERNAL | 北饭、南饭名称和分类已去重；精确入口及当前营业信息仍需管理员现场校准，西饭按小吃街而非饭堂处理。 |
| Canteens | PASS | 清远启用饭堂严格为北饭、南饭；历史占位饭堂和西饭旧饭堂记录已停用。 |
| Notifications | PASS | 通知正文可提取、校验并生成任务/提醒预览；自动测试验证 1 个任务、2 个提醒。 |
| Tasks | PASS | 用户隔离的任务列表、创建、状态变更和 Action Card 写入通过后端/E2E。 |
| Reminders | PASS | 提醒预览、确认写入、列表和取消均受用户隔离；伪造 action ID 返回 409。 |
| Notes | PASS | 便签预览/确认与学习建议保存卡片可用，写入 API 受用户隔离。 |
| ICS | PASS | 用户任务可生成日历下载，跨用户导出在 IDOR E2E 中被拒绝。 |
| Processes | PASS | 校园流程检索使用数据库工具并提供真实链接/操作卡，不生成虚构办理步骤。 |
| Mobile | PASS | 手机视口 E2E 通过；LAN 启动脚本在本机验证 5173/8000 可达。 |
| Login | PASS | 注册、登录、会话续用和退出覆盖后端及完整浏览器回归。 |
| Security | PASS | Key 只由环境变量读取；Run 公开结构无 GPS；确认动作白名单、CORS/鉴权/IDOR 测试通过。 |
| User Isolation | PASS | Conversation、Agent Run、任务、提醒、便签、知识和导出均验证所有权；跨用户 Run 返回 404。 |
| Admin | PASS | 管理员鉴权、来源证据、校准、审核、导入导出和审计日志后端测试通过；无凭据不会开放管理能力。 |
| Build | PASS | Python compileall、后端 111 项（含空数据库迁移与冲突意图）、前端 29 项、ESLint、TypeScript 和 Vite 正式构建通过。 |
| E2E | PASS | Playwright 7 项通过：Agent、AMap、定位、IDOR、知识、手机、真实 MVP；管理员浏览器场景因未提供外部测试密码跳过。 |
| Git | PASS | 安全扫描与 diff 检查通过后提交并推送到现有 PR #1 分支，不创建重复 PR、不自动合并。 |

## External evidence boundary

`BLOCKED_EXTERNAL` 只用于清远北教/南教、北饭/南饭精确入口及实时经营状态。系统明确展示待核验状态，并禁止这些记录进入正式路线计算；解除阻塞需要管理员现场定位或可审计的权威坐标证据。
