# API 说明

FastAPI 自动文档位于后端 `/docs`，OpenAPI 位于 `/openapi.json`。除公开校区/地点/饭堂/流程与健康检查外，用户 API 需要登录；`/api/admin/*` 全部需要 `role=admin`。

## 系统

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 进程健康 |
| GET | `/ready` | 数据库就绪 |
| GET | `/api/agent/status` | 后端、模型配置、模型名和数据库状态；不返回 Key |

## 认证

`POST /api/auth/register`、`login`、`refresh`、`logout`，`GET/PATCH /api/auth/me`，`POST /api/auth/change-password`，`DELETE /api/auth/account`。成功登录使用 Cookie，不在 JSON 返回 Token。注册对邮箱、用户名、密码和校区做校验；重复返回 409；统一登录失败返回 401。

## Agent 与对话

`POST /api/agent/chat` 使用当前登录用户和最近对话历史调用后端模型客户端，成功返回 `intent`、`answer`、`tool_results`、`sources`、`degraded=false`、`requires_confirmation` 和中国时间。`GET/POST /api/agent/conversations`、`GET/DELETE /api/agent/conversations/{id}` 均按用户隔离。

## 通知与任务

- `POST /api/notifications/parse`：multipart 文本或 TXT/PDF，仅预览。
- `POST /api/notifications/confirm`：明确 `confirmed=true` 后批量保存。
- `/api/tasks`：列表/创建，支持 `view`、`status`、`course`、`task_type`。
- `/api/tasks/{id}`：读取；更新请求体必须 `confirmed=true`，删除、`complete`、`reopen` 必须带确认参数。
- `POST /api/tasks/bulk`：批量完成、重开、删除。
- `GET /api/tasks/export/ics`：唯一文件名，支持 `task_ids` 与 `reminder_hours`。

## 校园数据

公开接口：`/api/campuses`、`/api/locations`、`/api/locations/search`、`/api/locations/nearby`、`/api/locations/{id}`、`/api/canteens`、`/api/canteens/{id}`、`/api/canteens/{id}/stalls`、`/api/food-search`、`/api/processes`、`/api/processes/{id}`、`/api/knowledge`。`POST /api/processes/{id}/create-tasks` 和 `POST /api/location-feedback` 需要登录及明确确认。

## 地图

- `GET /api/map/status`：只返回高德 JS/WebService 是否配置，不返回凭据。
- `GET /api/map/geocode`：由后端调用高德地理编码。
- `GET /api/map/walking-route`：由后端调用真实步行路线服务。
- `/api/map/_AMapService/{path}`：受限的高德 JS 安全代理，只允许指定 API 路径；`securityJsCode` 不进入浏览器。

## 管理后台

后台提供仪表盘、用户更新；校区、地点、地图、饭堂、档口、办事流程、知识资料和来源的管理接口；纠错批准/拒绝；陈旧数据、日志；CSV/JSON/GeoJSON 导入和 JSON 导出。写操作均审计。删除校区、地点、饭堂、档口和流程是停用语义；地图/来源/知识资料可删除。

## 错误与限制

Pydantic 校验失败为 422，未登录 401，模型限流 429，模型未配置 503，模型超时 504，模型认证或提供方失败 502。权限不足为 403，实体不存在 404，重复资源 409，超大文件 413，不支持类型 415。错误只返回公开中文说明和错误编号，不返回 Key、栈或提供方私密信息。
