# 安全说明

## 已实现控制

- 密码：`pwdlib[argon2]`，数据库只保存 Argon2 哈希。
- 会话：短期 Access JWT、可轮换/撤销 Refresh JWT；Refresh 数据库只存 SHA-256 哈希；HttpOnly Cookie，不存 localStorage。
- 权限：实体查询按 `user_id`；所有管理员接口使用后端角色依赖，前端守卫只是体验层。
- 输入：Pydantic 长度/格式/范围校验；SQLAlchemy 参数化；上传最多 5 MB，TXT/PDF 类型白名单，文件在内存处理且不公开落盘。
- 网络：精确 CORS、凭据模式、安全响应头、生产 HTTPS Cookie 强制。
- 滥用：注册/登录采用进程内基础频率限制；失败登录统一提示。
- 日志：错误只记录异常类型和 request ID；不记录密码、JWT、DeepSeek Key 或完整通知正文。
- 管理：已核验必须有证据；写操作记录审计日志。
- 地图：浏览器只接收可公开的高德 JS Key；`securityJsCode` 与 WebService Key 由后端读取，JS API 通过受限同源代理加载。
- 文档：上传内容在内存解析，只保存文件元数据、SHA-256 与解析状态，不保存原文件或全文。

## Secret 扫描

2026-08-04 检查当前工作区、所有跟踪文件和可遍历 Git 历史中的 `sk-`、GitHub Token、管理员明文密码、`.env`、`secrets.toml`，未发现真实凭据。没有执行公共历史重写。`.env`、数据库、上传与前端构建目录均被忽略，`.env.example` 只含占位符/本地示例。

用户曾经暴露的 API Key 不应继续使用，应在提供方控制台吊销并重新创建。新 Key 只能写入服务器/部署平台的 `DEEPSEEK_API_KEY`。

## 生产要求

- 两个 JWT Secret 必须不同、随机、至少 32 字符；`ENVIRONMENT=production` 会拒绝弱值。
- `COOKIE_SECURE=true`；跨站部署才用 `SameSite=None`，同源优先 `Lax`。
- `ALLOWED_ORIGINS` 只列实际 HTTPS 前端域名。
- 首次登录后修改管理员密码，并从平台移除 bootstrap 密码。
- PostgreSQL 不对公网开放；启用备份、TLS、最小权限账户。
- 平台日志、错误追踪和代理访问日志不得记录 Cookie/Authorization/请求正文。

## 已知安全边界

进程内频率限制不适合多副本，需要 Redis/网关限流；尚未实现 MFA、邮箱验证、密码重置邮件和 CSRF Token。当前 Cookie `SameSite`、仅接受 JSON/受限 multipart 与精确 CORS 可降低 CSRF 风险，但高风险公网上线前建议增加 Origin 校验/CSRF Token、集中限流、依赖漏洞扫描和安全告警。

2026-08-04 的 `npm audit --omit=dev` 对 React Router 7.18.2 报告一个高危 RSC Mode Action/Server Action CSRF 公告（GHSA-qwww-vcr4-c8h2）。当前前端是 Vite + BrowserRouter 纯客户端 SPA，不使用 React Server Components、SSR、Action 或 Server Action，因此受影响代码路径未启用；回退 7.11.0 会重新引入更多已修复的 XSS/开放重定向公告。现阶段固定当前注册表最新的 7.18.2 并持续跟踪上游修复，若未来启用 RSC/SSR 必须先升级并重新审计。
