# 广金大师兄：校园地图、饭堂数据与 Agent 重构

## 摘要

将原有的校园聊天/日历/消费/资讯工具集合重构为“广金大师兄”校园信息执行与位置服务 Agent。主路径现在由中国时区时间服务、结构化地点/饭堂数据、来源与新鲜度、本地工具编排、经确认的通知任务和持久化状态组成。

## 主要改动

- 新增 `core/time_service.py`，动态获取 `Asia/Shanghai` 时间，支持注入 `reference_time`、相对日期和风险年份确认。
- 新增 `CampusLocation`、`CanteenInfo`、`SourceReference`、`TaskItem` 与 SQLite 表，建立地点—饭堂—档口关联。
- 新增三校严格隔离的地点服务，支持别名/分类搜索、附近、导航、纠错、导入、核验、逻辑停用和回滚。
- 新增官方源配置化刷新，具备超时、重试、缓存、抓取/发布时间、哈希差异与失败保留。
- 新增校园地图页和数据管理页，支持示意坐标降级、地点详情、来源、底图上传、地点/档口编辑与过期数据处理。
- 用共享 `ui/campus_page.py` 替代三份重复页面业务逻辑。
- 通知改为“提取草稿 → 预览 → 用户确认 → 持久化 → ICS → 任务状态”闭环。
- 移除 Fake Embeddings 和进程级 API Key 写入；消费 CSV 降级到 `tools/experimental/`。
- 移动端移除写死明文 IP，改为首次启动输入 HTTPS 部署地址。
- 从 Git 移除已跟踪 `mobile/node_modules` 生成依赖，保留 `package-lock.json`。

## 数据真实性

内置点位不声称完整或实时。历史页面线索标为 `historical_seed`，占位档口标为 `demo_fixture`，无当日可靠源时 `today_menu=[]`。过期阈值按菜单/营业/档口/营业时间/固定地点分类配置。

## 验证

```text
python -m compileall -q app.py config.py core services tools rag ui pages deploy.py
pytest -q
19 passed
python -m pip check
No broken requirements found.
python deploy.py
Git: OK; 必需文件: OK; Python 编译: OK
```

Streamlit 冒烟测试使用真实 Streamlit 脚本运行器执行 `app.py` 和六个 `pages/*.py`，均无未捕获异常。

## 需要人工后续

- 按 `docs/DATA_VERIFICATION_CHECKLIST.md` 完成三校点位、饭堂、档口、营业时间、支付方式和坐标核验。
- 为生产数据管理页接入 SSO/反向代理访问控制。
- 如需多设备任务同步，接入真实用户身份，替代会话 UUID。
- 如需真实“今日菜单”，接入校方/饭堂当日系统或审核通过的当日现场提交。
