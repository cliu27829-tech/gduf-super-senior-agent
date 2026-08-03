# 测试报告

执行日期：2026-08-03；Python 3.12.3、Node 24.13、npm 11.6.2。

## 结果

| 套件 | 结果 |
|---|---|
| 后端 Pytest | 32 passed，约 6–7 秒 |
| 前端 Vitest | 13 passed / 2 files，约 2–3 秒 |
| TypeScript | `tsc -b --pretty false` 通过 |
| 前端生产构建 | Vite 8.2.0，39 modules，JS gzip 89.38 kB，CSS gzip 6.42 kB |
| Python 编译 | `python -m compileall -q app` 通过 |
| OpenAPI | 应用导入成功，53+ 路径（新增后台 CRUD 后更多操作） |

唯一测试警告来自 FastAPI 兼容层提示 Starlette `TestClient` 未来从 httpx 迁往 httpx2，不影响当前结果，已列为依赖升级观察项。

`npm audit --omit=dev` 对 React Router 7.18.2 报告 RSC Mode 专属 CSRF 公告；本项目不启用 RSC/SSR/Server Action，已作为不适用当前运行路径的上游例外记录在 `SECURITY.md`，并保留升级跟踪。回退版本会引入更多已修复公告，因此未采用自动强制降级。

## 后端覆盖场景

注册、登录、Cookie Token/刷新、限流、修改密码、账户删除；普通/管理员权限；用户任务隔离；任务 CRUD/批量/完成/重开；相对日期与中国时区；通知规则降级和确认；ICS 重新解析、`Asia/Shanghai`、两个 `VALARM`；三校区隔离；地点/饭堂/食品无编造；Agent 工具与对话持久化；学生纠错与管理员审核；已核验证据规则；地图/来源 CRUD；导入导出和 5 MB 限制；安全响应头与敏感字段不返回。

## 前端覆盖场景

首页与诚实声明；注册字段；匿名受保护路由；普通用户后台跳转；管理员后台；饭堂列表、非实时提示与 API 失败提示；地图筛选、来源抽屉与校区切换；通知可编辑预览；任务编辑抽屉；Access 过期后刷新重试；登录接口失败不循环重试。

## 端到端业务流

后端 TestClient 完整跑通：注册 → 创建任务 → 登出 → 未授权 → 再登录 → 原任务存在；普通用户后台 403；管理员创建已核验地点必须附证据 → 普通地点 API 可见 → 审计日志存在；通知草稿确认、任务保存和 ICS 解析分别验证。真实 LLM 未被调用。

## 响应式验收

CSS 在 900px 与 640px 设置布局断点，表格/管理后台有横向容器或移动网格，输入/按钮满足触控尺寸。实际截图检查覆盖 375px 和 1440px；768px、1280px 由相同生产构建与断点规则检查。浏览器截图见 `docs/images/`。

## 未自动化项

没有真实部署平台和线上 PostgreSQL，因此线上网络、第三方 Cookie、冷启动和平台备份只能在部署后按 `ONLINE_SMOKE_TEST.md` 验证。Docker CLI 当前机器不可用，Compose 仅完成静态配置和 CI `docker compose config` 校验，不能声称本机容器已启动。
