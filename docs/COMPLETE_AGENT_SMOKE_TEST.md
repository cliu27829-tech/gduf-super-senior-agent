# 完整 Agent 冒烟测试记录

执行日期：2026-08-04

环境：Windows，本机 React `127.0.0.1:5173`、FastAPI `127.0.0.1:8000`；自动 E2E 使用隔离端口 5174/8002 和本地 OpenAI 协议 Mock 8001。

## 真实 DeepSeek 人工冒烟

真实 Key 只从后端 `.env` 读取，未打印、未提交、未进入浏览器。测试临时账号在验证后删除。

| 轮次 | 输入 | 结果 |
| --- | --- | --- |
| 1 | 你好，你能做什么？ | HTTP 200，真实模型回答，`degraded=false` |
| 2 | 大一高数跟不上怎么办？ | HTTP 200，给出通用学习建议 |
| 3 | 我叫小明，请记住。 | HTTP 200，会话保存 |
| 4 | 我刚才说我叫什么？ | HTTP 200，回答“小明” |

数据库中该会话按顺序保存 `user, assistant, user, assistant` 等消息角色；中文输入与落库内容完全一致。人工冒烟没有复用或泄露旧 Key。

## 自动浏览器端到端

命令：

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:5174'
$env:PLAYWRIGHT_CHANNEL='msedge'
npm run test:e2e
```

结果：`1 passed (7.7s)`。

覆盖项：

1. 注册并自动登录，刷新后会话仍存在。
2. 打开聊天页并确认模型状态。
3. 完成问候、学习建议、姓名记忆和饭堂事实边界四类对话。
4. 无高德凭据时显示明确配置提示，同时保留文本地点列表。
5. 查看带来源的校园卡流程，确认后生成任务。
6. 解析通知、编辑预览、确认并保存任务。
7. 编辑任务与提交方式，导出 ICS，验证两个 `VALARM` 和 `Asia/Shanghai`。
8. 退出并重新登录，确认数据持久化。
9. 删除测试任务与测试账号。
10. 断言无意外 4xx/5xx、网络失败或控制台错误。

自动流程调用真实 FastAPI、SQLite 和前端页面，但模型端使用本地 Mock，避免付费请求和测试不确定性。

## 单元与构建

```text
backend compileall     PASS
backend pytest         56 passed
frontend typecheck     PASS
frontend eslint        PASS
frontend vitest        20 passed
frontend vite build    PASS
```

## 地图验证边界

`GET /api/map/status` 在本机返回 provider 为 `amap`，安全代理与 WebService 配置状态均为 false；前端公开 JS Key 也未配置，页面因此不渲染地图。高德响应解析、错误映射、后端代理和路线服务由 Mock 单测覆盖。只有填入三项高德凭据并补齐核验坐标后，才能进行真实地图人工冒烟。

## 未执行项

本机没有 Docker CLI，不能执行 `docker compose up --build`。没有公开部署地址，因此没有声称线上验收通过。
