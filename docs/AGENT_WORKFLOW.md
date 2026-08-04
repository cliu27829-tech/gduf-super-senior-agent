# Agent 工作流

## 意图路由

当前编排顺序为 `observe → classify → plan → execute → verify → confirm → remember → respond`。分类器优先使用模型结构化 JSON，并在模型输出不可解析时使用确定性回退；计划、执行与校验均由后端代码控制。

| 意图 | 典型问法 | 工具计划 |
|---|---|---|
| `campus_location_search` | “图书馆在哪里” | `search_campus_locations` → `get_location_details` |
| `canteen_search` | “广州校本部有哪些饭堂” | `list_canteens` → `get_canteen_details` |
| `food_search` | “我想吃面” | 只查已核验档口 |
| `nearby_location_search` | “附近有快递站吗” | `find_nearby_locations` |
| `campus_navigation` | “去图书馆怎么走” | `search_campus_locations` → `calculate_walking_route` |
| `notification_to_tasks` | 带截止日期/材料/提交方式的通知 | 提取 → 预览，不创建 |
| `campus_process` | 校园卡、报修、请假等 | 只返回有可验证来源的流程 |
| `task_management` | “这周有什么没完成” | 按当前用户查本周任务 |
| `learning_guidance` | “高数跟不上怎么办” | 通用建议，不虚构校园事实 |
| `calendar_export` | “导出本周任务日历” | 查询任务 → 生成/验证 ICS |
| `data_feedback` | “这个地点错了” | 返回纠错入口，不静默修改主数据 |
| `out_of_scope` | 超出产品能力 | 明确边界，不伪造结果 |

完整意图还包括 `general_chat`、`campus_life_guidance`、`document_analysis`；注册表中的 41 个工具覆盖地点/路线、饭堂、任务、通知、日历、流程、知识和用户偏好。工具统一返回成功状态、数据、摘要、来源、验证信息、错误和是否需要用户操作；执行记录写入 `tool_executions`。

## 工具执行原则

1. 校园事实问题优先调用本地结构化服务。
2. 查询必须带校区；没有校区时先要求指定，不合并三校结果。
3. 答案同时显示核验时间、来源和过期警告。
4. 食物搜索只返回已核验、非演示的档口；无数据时不生成餐品。
5. 具有写操作的任务创建只能由用户确认触发。
6. 日期默认以 `Asia/Shanghai` 解析。缺年且当年候选日期已过时，推到下一年但标记必须确认。

## 通知到任务闭环

```mermaid
sequenceDiagram
    participant U as 用户
    participant N as NotificationService
    participant UI as 预览界面
    participant T as TaskService
    participant I as ICS

    U->>N: 粘贴通知
    N-->>UI: 任务草稿 + 日期解释 + 风险标记
    UI-->>U: 展示名称/年份/截止/地点/材料/提交方式
    U->>UI: 勾选已核对并确认保存
    UI->>T: confirmed=true
    T-->>UI: 持久化任务
    UI->>I: 生成唯一名 ICS
    I-->>U: Asia/Shanghai 日历文件
```

用户可在任务中心查全部/本周/过期任务，标记完成或重新打开。所有查询和更新都同时校验 `task_id` 和 `user_id`。
