# 广金大师兄部署指南

## Streamlit Community Cloud

1. 将工作分支通过 Pull Request 合并到需要部署的分支。
2. 在 Streamlit Community Cloud 创建应用，仓库选择 `gduf-super-senior-agent`，入口为 `app.py`。
3. 在平台 Secrets 中配置：

```toml
DEEPSEEK_API_KEY = "可选：通知模型提取 Key"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
GDUF_ADMIN_TOKEN = "必需：高强度随机管理员 Token"
```

`DEEPSEEK_API_KEY` 缺失时，地图、规则通知提取、任务和 ICS 仍可运行。`GDUF_ADMIN_TOKEN` 缺失时，数据管理页会锁定。

4. 部署后验证首页、三校 Agent、校园地图、任务中心和管理员 Token 校验。
5. 数据管理页会修改 SQLite；公网环境还应在反向代理/身份层限制管理员。

## 持久化注意

Streamlit Community Cloud 的本地文件系统不适合作为多实例长期数据库。MVP 可使用默认 `data/gduf_agent.db`；真实生产环境应挂载持久卷，或把 `Database` 适配到托管数据库。迁移前不要声称管理员修改已可跨重启永久保存。

## 部署前验证

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall -q app.py core services tools ui pages rag
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\python.exe deploy.py
```

## 移动端包装器

```powershell
cd mobile
npm ci
npx cap sync android
npx cap open android
```

安装包不再写死服务器 IP。首次启动时输入已部署的 HTTPS Streamlit URL；地址只保存在当前设备。

## 故障排查

- 首页可打开但模型提取降级：检查 `DEEPSEEK_API_KEY`，规则提取仍应工作。
- 数据管理页锁定：检查 `GDUF_ADMIN_TOKEN`，不要将真实 Token 写入 Git。
- 官方源刷新失败：查看后台 `last_error`；已缓存数据应保留。
- 部署重启后数据丢失：检查部署平台是否提供持久存储。
- 地图仅显示示意坐标：这是真实 GPS 尚未核验时的设计降级，不应自动换算成步行米数。

更完整的数据备份、导入、安全与运维说明见 `docs/OPERATIONS.md`。
