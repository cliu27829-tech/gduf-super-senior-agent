# 部署手册

## 推荐策略

最稳妥的是单域名反向代理：Nginx 同时提供 React 静态文件并把 `/api` 转发到 FastAPI，认证 Cookie 不跨站。仓库的 Docker Compose 已采用该结构。

托管平台拆分也可用：Vercel 前端 + Render FastAPI + Neon PostgreSQL。Render 官方支持 FastAPI 与 Docker 部署，也支持迁移用的 pre-deploy command；Neon 官方连接串可直接用于 Psycopg 3；Vercel 支持 Vite 构建、环境变量和外部 origin rewrite。参考：[Render FastAPI](https://render.com/docs/deploy-fastapi)、[Render Docker](https://render.com/docs/docker)、[Neon Python](https://neon.com/docs/guides/python)、[Vercel 环境变量](https://vercel.com/docs/environment-variables)、[Vercel rewrites](https://vercel.com/docs/routing/rewrites)。

## 方案 A：单机 Docker

1. 安装 Docker Engine/desktop 并登录服务器。
2. 克隆仓库与目标分支。
3. `cp .env.example .env`，生成两个不同的 32+ 字符随机 JWT Secret，修改数据库和管理员密码。
4. 设 `ENVIRONMENT=production`、`COOKIE_SECURE=true`、`ALLOWED_ORIGINS=https://你的域名`。
5. `docker compose up -d --build`。
6. 让公网 HTTPS 反向代理指向前端容器 8080；不要公开 PostgreSQL 端口。
7. 验证 `/health`、`/ready`、注册、Cookie、ICS 和后台 RBAC。

## 方案 B：Vercel + Render + Neon

1. Neon 创建数据库，把连接串协议改为 SQLAlchemy/Psycopg 可识别的 `postgresql+psycopg://...`，保留平台要求的 SSL 查询参数。
2. Render 创建 Docker Web Service，仓库根目录为项目根，Dockerfile 路径 `backend/Dockerfile`；健康检查 `/health`。入口脚本会先运行迁移。
3. Render 填写生产变量：

```text
ENVIRONMENT=production
DATABASE_URL=...
JWT_SECRET=...
REFRESH_TOKEN_SECRET=...
COOKIE_SECURE=true
COOKIE_SAMESITE=none
ALLOWED_ORIGINS=https://<vercel-domain>
FRONTEND_URL=https://<vercel-domain>
BACKEND_URL=https://<render-domain>
ADMIN_BOOTSTRAP_EMAIL=...
ADMIN_BOOTSTRAP_PASSWORD=...
DEEPSEEK_API_KEY=...  # 可空；空时规则降级
```

4. Vercel 新建项目，Root Directory 设为 `frontend`，Build Command `npm run build`，Output `dist`，添加 `VITE_API_BASE_URL=https://<render-domain>` 后重新部署。
5. 跨站 Cookie 依赖浏览器第三方 Cookie 策略。生产更推荐在 Vercel 配置 `/api/:path*` 到 Render 的同源 rewrite，或改用自有同主域名；生成后端域名后再把确定 URL 写入项目设置，不提交占位 URL。
6. 首次管理员登录后立即改密码，随后从平台删除 `ADMIN_BOOTSTRAP_PASSWORD` 并重新部署（已有账户不会被覆盖）。

## 发布前检查

- `.env` 未提交，生产 Secrets 均来自平台；DeepSeek Key 未设置为 Vite 变量。
- `ENVIRONMENT=production` 能启动，弱 Secret/非安全 Cookie 会故意失败。
- `alembic current` 指向 head；`/ready` 返回 200。
- CORS 只有准确前端域名，无 `*`。
- 在线执行 `docs/ONLINE_SMOKE_TEST.md` 全部流程。
- 数据库已启用备份；日志留存策略不记录通知正文。

## 当前部署状态

本机没有 `vercel`、`render`、`railway`、Docker CLI 的可用登录会话，也没有目标 PostgreSQL 凭据，因此不能诚实生成公网地址。下一步只需用户在选定平台完成交互式登录；不需要把 Token 发给协作者。
