# 最终产品回归矩阵

验收时间：2026-08-09（中国标准时间）
分支：`codex/2026-campus-map-agent`

## 结果总览

| 范围 | 结果 | 实际证据 |
| --- | --- | --- |
| Chat | PASS | Playwright 使用本机后端和已配置的 `deepseek-v4-flash` 完成真实提问与“小明”两轮记忆测试；没有 Mock 回答。 |
| Map | PASS | 高德真实底图、广州 Marker、精确地点步行路线、清远/肇庆校区切换通过；坐标审计 `PASS=7 / SUSPICIOUS=0 / INVALID=0 / NEEDS_REVIEW=8`。 |
| Canteens | PASS | 饭堂通过 `location_id` 关联地点；北苑饭堂展示已核验地图入口，无可靠坐标的饭堂明确显示“位置待核验”；不生成实时菜单。 |
| Notifications | PASS | 正大杯 fixture 解析为 3 条规则和 1 个 Action Item；日期、ZIP、条件、证明材料、无邮箱地址均符合预期。通知/日期专项测试 32 条通过。 |
| Tasks | PASS | E2E 完成通知确认、保存、查看原文、编辑标题与提交方式；任务保留条件、证据、来源和过期状态。 |
| Processes | PASS | 校园卡、宿舍报修、校园网、图书馆 4 条流程可查询；来源和待核验状态可见，不补写无来源电话。 |
| Auth | PASS | 注册、登录、会话持久化、普通用户删除、用户隔离通过；管理员审计保留阻止自助删除并返回明确 409。 |
| Admin | PASS | 临时本地管理员完成内部资料审核与共享；地点校准支持高德搜索、地图/卫星切换、点击、拖动、证据和精度保存。临时账号及测试审计记录已清理。 |
| Mobile | PASS | Playwright 在 390×844 验证移动导航、聊天、通知、任务和办事流程，无整页横向溢出。 |
| Security | PASS | 密钥仅从忽略的环境文件读取；HTTP 客户端日志降级避免带密钥 URL；管理员权限、上传上限、用户隔离和安全响应头均有测试。 |

可控 `FAIL=0`。
`BLOCKED_EXTERNAL=3`，详见文末。

## 正大杯固定回归结果

以下为 `backend/tests/fixtures/real_notifications/zhengda_cup.txt` 在 2026-08-09 中国标准时间基准下的实际结构化结果（省略完整原文副本）：

```json
{
  "notice": {
    "title": "关于正大杯（全国市调赛）加分通知",
    "notice_date_text": "8.5",
    "notice_date": "2026-08-05T00:00:00+08:00",
    "publisher": "校青成",
    "campuses": ["广州校区", "清远校区"],
    "audience": ["二课负责人", "需要补录正大杯加分的相关班级和同学"],
    "category": "比赛加分"
  },
  "rules": [
    "正大杯（全国市调赛）与广东省市调赛算作同一个比赛，只加一次最高分",
    "正大杯市调【资格赛】可以加参与分",
    "正大杯资格赛初选+0.1，校赛负责人+0.3，其他成员+0.2，只取最高分补录"
  ],
  "action_items": [
    {
      "title": "收集并提交正大杯加分补录材料",
      "conditions": ["班级已经提交创新创业修正补录表", "校赛没有补录成功的同学"],
      "deadline_text": "8月6日22:00",
      "deadline": "2026-08-06T22:00:00+08:00",
      "is_expired": true,
      "submission_method": "邮件发送 ZIP 文件",
      "submission_target": "邮箱",
      "file_naming": "正大杯-24/25+学院+专业+班级",
      "evidence_requirements": [
        "证明材料需要有表头",
        "证明材料需要有公章",
        "通知所示的正大杯奖状图片可以作为证明材料"
      ],
      "needs_confirmation": false
    }
  ],
  "warnings": [
    "兄弟，这份通知的截止时间已经过了，我先帮你把要求整理出来。要是你现在需要补交，建议先确认负责人是否还接受补录。"
  ]
}
```

结果没有生成 7 个假任务，没有把 2026-08-06 推到 2027 年，也没有编造具体邮箱地址。

## 地点审计结果

已核验 7 个点位：

1. 广州校本部；
2. 广州北苑饭堂；
3. 广州北教学楼 AD 座；
4. 广州北苑学生宿舍区（区域近似点，仅展示，不进入精确路线）；
5. 清远校区；
6. 清远校区图书馆；
7. 肇庆校区。

待核验 8 个地点均没有随机坐标，不进入精确导航：广州南苑饭堂、肇庆饭堂、肇庆图书馆、清远饭堂、清远敏学楼、广州历史快递点、广州卫生所、广州校园卡部。

审计命令：

```text
python -m backend.app.cli.audit_locations
Summary: PASS=7, SUSPICIOUS=0, INVALID=0, NEEDS_REVIEW=8
```

## 自动化结果

```text
backend compileall: PASS
backend pytest:      86 PASS
frontend typecheck:  PASS
frontend Vitest:     20 PASS
frontend ESLint:     PASS (0 warnings)
frontend build:      PASS (43 modules)
Playwright E2E:      5 PASS / 0 FAIL / 0 SKIP
```

E2E 覆盖管理员内部审核、高德真实底图与路线、学生知识入口移除、390×844 手机端、真实 DeepSeek 对话、通知解析和任务中心。

## BLOCKED_EXTERNAL

1. 8 个地点仍缺少足以支持精确导航的高德明确 POI、官方校园地图交叉证据或现场 GPS；代码已将其保持为待核验且不打点。
2. 图书馆当前详细借还规则没有找到可确认时效的官方公开细则；现有流程明确标为需现场/官方确认，不补写时限或费用。
3. 本轮使用的高德凭据曾由用户通过聊天截图展示；本地调试可用，但正式发布前应由账号所有者轮换凭据并设置生产域名白名单。

这些项目不能通过猜测数据或代码伪造完成，不计入可控 FAIL。
