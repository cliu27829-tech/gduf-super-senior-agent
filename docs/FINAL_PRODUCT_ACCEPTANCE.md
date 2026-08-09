# 广金大师兄最终产品验收

验收日期：2026-08-09（Asia/Shanghai）

分支：`codex/2026-campus-map-agent`

原则：校园事实只使用工具与结构化数据；缺少入口坐标或内部路径证据时明确拒绝猜测。

## 验收总表

| 模块 | 结果 | 证据 |
| --- | --- | --- |
| Chat UI | PASS | 桌面会话侧栏、自然正文、底部编辑器、复制、停止、重新生成、附件和移动抽屉均已浏览器验证；390×844 与 412×915 截图已人工复核。 |
| Markdown | PASS | 使用 `react-markdown + remark-gfm + rehype-sanitize`；粗体、列表、表格、脚本过滤和危险 URL 测试通过。 |
| Streaming | PASS | `POST /api/agent/chat/stream` 返回 `stage/tool/token/final/error` SSE；浏览器真实请求 200，无请求失败。 |
| Reasoning | PASS | `deepseek-v4-flash` 使用官方 thinking 配置和 `reasoning_effort=high`；思考模式不传 temperature；`reasoning_content` 在后端丢弃，不返回、不持久化、不记录。 |
| Agent Planner | PASS | 严格 `AgentPlan`、模型计划、最多 4 步、工具观察、失败重规划和验证已接通；复杂行程实际调用地点、饭堂、快递和路线 4 个工具。提醒/便签/通知计划被强制约束为安全预览。 |
| Notifications | PASS | TXT/PDF/正文解析后可编辑、保存任务，并继续设置提醒、添加便签和使用 ICS。 |
| Tasks | PASS | 增删改查、通知/流程转任务、刷新持久化和用户隔离通过 API 与 Playwright。 |
| Reminders | PASS | `Reminder` 迁移、自然语言时间预览、确认写入、列表、到期检查、站内 Toast、浏览器授权通知和取消均已实现；人工验证生成未来 `scheduled` 记录。 |
| Notes | PASS | `Note` 迁移、自然语言预览、确认写入、搜索、置顶、编辑、删除和用户隔离通过；人工验证已真实持久化。 |
| ICS | PASS | E2E 下载内容包含 `Asia/Shanghai` 和两个 `VALARM`（提前 24 小时、3 小时）。 |
| Map | PASS | 真实高德 JS 底图、校区 Marker、点位详情、地址/步行路线和自建校园 POI 叠加通过高德 E2E；管理员支持卫星图、点击、拖动、坐标微调、证据和核验状态。 |
| Qingyuan Data | PASS | 结构化导入 13 个“2+2”学院、1 个全学段学院、4 个产业学院，并录入教学楼、图书馆、饭堂、宿舍、体育、快递和地标的来源/状态。 |
| Canteens | PASS | 北区饭堂/北饭、南区饭堂/南饭使用官方来源；西饭作为用户报告的小吃街别名保持待核验；无可靠实时菜单时明确说明。 |
| Processes | PASS | 校园流程查询、来源展示、确认转任务及持久化 E2E 通过。 |
| Mobile | PASS | `VITE_API_BASE_URL` 留空并走同源代理；`0.0.0.0` 监听；局域网 `192.168.1.42:5173` 的 `/api/agent/status` 返回 200。390×844、393×852、412×915 无页面横向溢出。 |
| Auth | PASS | 注册、登录、HttpOnly Cookie、刷新、退出、删除账户、限流和用户数据隔离通过。重复 E2E 注册触发 429 的情况已确认是预期安全限流。 |
| Admin | PASS | 地点校准、来源/核验、事实研究 URL→候选→人工确认、审计日志可用；临时管理员审核 E2E 通过，测试账号和审计记录随后删除。 |
| Security | PASS | DeepSeek Key 只由后端 `.env` 读取；真实 `.env`、数据库、运行日志和构建产物均被忽略；npm 完整依赖树 0 个已知漏洞。 |
| Build | PASS | Python compileall、Alembic current/head、ESLint、TypeScript、Vitest 和 Vite 正式构建全部通过。 |
| E2E | PASS | 桌面完整 MVP、移动核心流程、真实高德、知识路由和管理员审核均通过；每个 E2E 临时用户均已清理。 |

可由代码解决的 `FAIL`：**0**。

## 自动化结果

- 后端：`93 passed`；唯一提示为测试客户端兼容层的弃用警告，不影响运行。
- 数据库：当前迁移与唯一 head 均为 `20260809_07`。
- 前端：3 个测试文件、23 项测试全部通过。
- `npm run lint`：通过。
- `npm run typecheck`：通过。
- `npm run build`：通过；仅有单包超过 500 kB 的性能建议，不影响构建或功能。
- `npm audit`：0 vulnerabilities。
- Playwright：桌面完整业务流 1/1 通过；知识与三尺寸移动 2/2 通过；真实高德 1/1 通过；管理员审核 1/1 通过。

## 真实 DeepSeek 与 Agent 冒烟

| 请求 | 结果 |
| --- | --- |
| 大一高数跟不上怎么办？ | 返回真实、自然的学习建议，非 Mock。 |
| 清远校区有多少个学院？ | 命中校园事实与学院口径工具；说明 13 只指“2+2”，另有全学段和 4 个产业学院。 |
| 清远校区有几个学院？ | 同义表达回归后命中相同工具；浏览器 SSE 200，回答包含 13 与 2+2，显示 2 张自然工具卡。 |
| 清远有哪些饭堂？ | 返回北区饭堂/北饭、南区饭堂/南饭；西饭明确为用户称呼和待核验数据。 |
| 北区教学楼在哪里？ | 命中自建地点数据，说明北区与精确入口待核验，不生成坐标。 |
| 北区教学楼怎么去北饭？ | 调用地点、饭堂和路线工具；因两端入口未核验而明确拒绝猜路线。 |
| 我从北教下课后想先吃东西，再去拿快递，怎么走？ | 调用 `search_campus_locations`、`list_canteens`、`search_express_locations`、`calculate_walking_route`；使用前三项事实，路线失败时说明缺少核验入口。 |
| 我叫小明 / 我刚才说我叫什么？ | 同一会话正确回答“小明”，数据库历史持久化。 |
| 明天下午3点提醒我交高数作业 | 强制使用提醒预览，页面出现确认按钮；确认后数据库存在未来 `scheduled` 记录。 |
| 把高数复习计划记一下 | 页面出现便签预览与确认按钮；确认后便签持久化。 |

## 清远资料来源与边界

- [广东金融学院清远校区情况](https://qyxq.gduf.edu.cn/info/1128/1396.htm)：学院培养口径、产业学院与校区设施。
- [关于清远校区教学楼封闭考场的通知](https://qyxq.gduf.edu.cn/info/1024/2306.htm)：北/南教学楼名称。
- [清远校区上新，图书馆和实验教学楼投入使用](https://xsc.gduf.edu.cn/info/1032/2014.htm)：图书馆、敏学楼、笃行楼。
- [清远校区开展秋季学期开学检查和防疫演练](https://qyxq.gduf.edu.cn/info/1047/1389.htm)：北区饭堂、南区饭堂。
- [清远校区开展 2025 年“五一”假期前校园安全检查工作](https://qyxq.gduf.edu.cn/info/1047/2233.htm)：快递驿站存在性。

“西饭”、明湖、木兰广场和南区球场目前保留为用户提供线索，不升格为官方事实；北教、北饭等多数内部入口尚无可审计精确坐标。

## BLOCKED_EXTERNAL

| 项目 | 状态 | 原因与后续 |
| --- | --- | --- |
| 清远北教→北饭精确内部路线 | BLOCKED_EXTERNAL | 缺少官方校园图或现场核验的两端入口坐标与步道节点；模型和地图均不会猜测。管理员取得证据后可用校准工具和 `CampusPathNode/Edge` 入库。 |
| 网站关闭后的 Web Push | BLOCKED_EXTERNAL | localhost/LAN 是 HTTP，无法提供可靠后台 Push。当前可用站内提醒、网页打开时的已授权浏览器通知和 ICS；需 HTTPS、公网 Push 服务和订阅端点。 |
| 正式公网 HTTPS 部署 | BLOCKED_EXTERNAL | 本机无 Render/Vercel/Railway CLI 会话、目标服务或生产数据库配置，不能仅凭网页已登录安全推断部署目标。Docker、迁移与环境模板已准备。 |
