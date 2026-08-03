# 数据库设计

正式数据库为 PostgreSQL 16；SQLite 只用于快速测试。SQLAlchemy 负责 ORM，Alembic 负责迁移，容器入口先执行 `alembic upgrade head`。

## 表

- 认证：`users`、`refresh_tokens`。
- 校园：`campuses`、`campus_maps`、`locations`、`canteens`、`food_stalls`、`campus_processes`。
- 来源：`sources`、`location_sources`、`verification_records`、`data_refresh_logs`。
- 用户事项：`tasks`、`task_reminders`、`conversations`、`messages`、`feedback_submissions`。
- 运维：`admin_audit_logs`、`system_logs`。

## 约束与隔离

邮箱和用户名唯一；关键外键有索引；任务和对话查询必须同时匹配 `user_id`；Refresh Token 只存哈希。删除用户级联删除 Token、任务、提醒、会话和消息；校园引用按实体采用级联、置空或软停用。管理员操作记录操作者、动作、实体、摘要和时间。

## 时间

应用层使用 aware datetime；业务解释统一按 `Asia/Shanghai`，数据库列使用 `DateTime(timezone=True)`。SQLite 测试驱动可能返回无时区值，服务边界会补齐；正式 PostgreSQL 使用带时区时间。

## 迁移命令

```bash
cd backend
alembic upgrade head
alembic current
alembic revision --autogenerate -m "describe change"
```

首个迁移以当前 `Base.metadata` 建立全量结构。后续必须使用新的、可审查的 Alembic revision，不在生产启用 `AUTO_CREATE_SCHEMA`。
