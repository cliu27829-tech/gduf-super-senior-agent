# 广金大师兄

广东金融学院校园信息执行与位置服务 Agent。它不是仅能聊天的问答页：用户可以按广州校本部、肇庆校区、清远校区查地点与饭堂，把班群通知转成经确认的持久化任务，并导出 `Asia/Shanghai` 时区的 ICS 日历。

## 核心能力

- 三校区数据层隔离，同一套共享 UI，不复制三份业务逻辑。
- 校园地图搜索、分类、饭堂、当前营业、附近、导航和纠错。
- 饭堂与档口结构化存储；不把历史资料冒充今日菜单。
- 来源等级、发布时间、抓取时间、核验时间、置信度、有效期和过期警告。
- 官方源可刷新，带超时、重试、6 小时缓存、内容哈希与失败保留旧数据。
- 通知先提取草稿、再预览确认、最后创建任务；未确认时没有写操作。
- 中国标准时间统一解析“今天/明天/今年/下周”。缺少年份且当年日期已过时，会降置信度并要求确认。
- API Key 只读取部署 Secrets 或保存在当前 Streamlit 会话，不写入进程级 `os.environ`。
- 本地知识检索使用透明可解释的词法排序，不使用虚假向量。

## 快速开始

Windows PowerShell：

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m streamlit run app.py
```

macOS/Linux：

```bash
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
./venv/bin/python -m streamlit run app.py
```

没有 DeepSeek API Key 也可运行地图、规则通知提取、任务和管理后台。需要模型提取时，在界面中输入 Key，或在 `.streamlit/secrets.toml` 配置：

```toml
DEEPSEEK_API_KEY = "..."
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
GDUF_ADMIN_TOKEN = "请使用高强度随机值"
```

`secrets.toml` 已被 Git 忽略。

## 数据诚实声明

内置点位主要是历史官方页面线索和演示占位，不是已完成实地核验的完整校园地图。页面会显示 `historical_seed`、`demo_fixture`、`needs_verification`、`expired` 等状态。没有可靠当日来源时，系统明确回答“目前没有可靠的当日菜单”。

真实点位核验清单见 `data/campuses/TODO_REAL_DATA.md`。

## Demo 流程

1. 首页选择广州校本部，进入 Agent 并输入“广州校本部有哪些饭堂？”。
2. 打开校园地图，搜索饭堂，查看历史来源、新鲜度、示意坐标和导航入口。
3. 输入“我想吃面，哪个饭堂有？”。内置数据没有已核验档口时，应看到明确的无数据说明，而不是生成菜单。
4. 在“通知执行”粘贴带截止时间、材料和提交方式的通知，先预览日期推断，勾选确认后保存，再下载 ICS。
5. 进入任务中心查本周待办、标记完成，然后回到 Agent 输入“我这周还有什么没完成？”。

完整演示话术和预期结果见 `docs/DEMO_SCRIPT.md`。

## 地图配置与已知限制

当前地图不需要高德/百度 API Key：真实经纬度使用 Streamlit 底图，不完整点位用 0–1 校内示意坐标。导航按钮生成高德 URI/搜索链接，不在服务器中保存地图 Key。

- 三校真实点位、饭堂楼层和档口仍需系统性实地核验。
- 校园底图可上传和展示，但尚未与示意点做图像叠加或点击命中。
- 官方网页抓取只做来源缓存和变化提示，不自动把自由文本转为已核验地点。
- 任务按会话用户 ID 隔离；生产多设备同步需要接入真实身份系统。
- 管理后台必须在部署层配置访问控制。

## 项目结构

```text
app.py                    首页和会话设置
core/                     时间、模型、SQLite schema、Agent 编排
services/                 地点、来源刷新、通知、任务服务
tools/                    Agent 工具适配器、ICS 和实验工具
ui/                       三校共享页面和地图纯函数
pages/                    三校 Agent、校园地图、数据管理、任务中心
data/campuses/            三校初始数据与核验 TODO
好人师兄/                  原始历史知识资料（保留，运行时加时效警告）
tests/                    时间、地点、路由、来源、任务、ICS 与七页冒烟测试
docs/                     架构、数据模型、来源、工作流与运维文档
```

## 验证

```powershell
.\venv\Scripts\python.exe -m compileall -q app.py config.py core services tools rag ui pages deploy.py
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m pip check
```

更多内容：

- `docs/ARCHITECTURE.md`
- `docs/LOCATION_SCHEMA.md`
- `docs/DATA_SOURCES.md`
- `docs/AGENT_WORKFLOW.md`
- `docs/OPERATIONS.md`
- `docs/CODEX_AUDIT.md`
