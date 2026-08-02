# 运行与运维

## 环境

- Python 3.11+ 建议版本。
- 数据库默认为 `data/gduf_agent.db`，可通过 `GDUF_DB_PATH` 指定。
- 默认时区固定为 `Asia/Shanghai`，不依赖主机时区。

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m streamlit run app.py
```

## 配置

| 配置 | 用途 | 是否必需 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 通知模型提取 | 否 |
| `DEEPSEEK_BASE_URL` | 模型网关，默认 `https://api.deepseek.com/v1` | 否 |
| `GDUF_DB_PATH` | SQLite 文件位置 | 否 |
| `GDUF_ADMIN_TOKEN` | 数据管理页会话级校验 Token | 管理后台必需 |

部署时优先使用 Streamlit Secrets 或平台密钥管理。页面输入的 Key 只存在当前会话，不写入数据库、文件或进程级环境。

## 数据初始化与备份

首次创建 `LocationService` 时会从 `data/campuses/*/locations.json` 和 `canteens.json` 填充空数据库。这些条目多为历史线索/演示占位，需要后台核验。

备份前建议停止写入，并同时备份 `.db`、`.db-wal` 和 `.db-shm`；或使用 SQLite 在线备份 API。这些运行文件均已被 Git 忽略。

## 官方源刷新

在“数据管理 → 官方源刷新”按校区执行。正常刷新使用 6 小时缓存；仅在排障或明确需要时勾选强制刷新。

刷新不会自动改写已核验地点。看到 `changed=true` 后，管理员应比较原页、实地或职能部门说明，再通过导入/核验流程更新事实。

## 地点导入

数据管理页支持：

- CSV：`aliases`、`services`、`payment_methods` 用 `|` 分隔。
- JSON：可为数组、单对象，或 `{"locations": [...]}`。
- GeoJSON：`FeatureCollection`，点坐标顺序为 `[longitude, latitude]`。

最低必需字段为 `name`、`campus`、`category`；强烈建议主动提供稳定 `id`、来源、核验时间、置信度和数据状态。同 ID 更新前自动保存一版快照。

## 管理后台安全

数据管理页在未配置 `GDUF_ADMIN_TOKEN` 时会直接锁定，配置后使用常量时间比较在当前会话校验。该 Token 只是轻量 MVP 保护；当前 Streamlit 项目没有组织级登录系统，生产环境还必须通过反向代理、单点登录或部署平台访问策略限制。不要把未受保护的后台暴露到公网。

## 移动端

`mobile/` 是 Capacitor Android 包装器。`node_modules` 不进入 Git：

```powershell
cd mobile
npm ci
npx cap sync android
```

首次启动移动端时输入已部署的 HTTPS Streamlit URL；它只保存在本设备 `localStorage`。开发调试可使用 `http://localhost` 或 `http://127.0.0.1`，其他明文 HTTP 地址会被拒绝。

## 健康检查与测试

```powershell
.\venv\Scripts\python.exe -m compileall -q app.py config.py core services tools rag ui pages deploy.py
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\python.exe deploy.py
```

`tests/test_streamlit_smoke.py` 使用 Streamlit 测试运行时执行首页和六个子页，不只做导入测试。

## 常见故障

- 秘钥缺失：不应影响无模型功能；检查 Secrets 命名和部署平台注入。
- 官方源超时：查 `location_sources.last_error` 和 `data_refresh_logs`；已缓存内容不会丢失。
- “正在营业”筛选无结果：只有已核验且营业时间符合 `HH:MM-HH:MM` 的条目才会通过。
- 附近距离不是米：当点位只有 `map_x/map_y` 时显示“示意单位”，不应换算成真实步行距离。
