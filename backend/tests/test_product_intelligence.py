from __future__ import annotations

import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.agents.intent_classifier import IntentClassifier
from app.agents.contracts import IntentDecision
from app.agents.planner import Planner
from app.models.entities import Campus, CampusCollege, CampusFact, Note, Reminder
from app.services.time_service import now_china


def _qingyuan_id() -> str:
    with SessionLocal() as db:
        return db.scalar(select(Campus.id).where(Campus.slug == "qingyuan"))


def test_qingyuan_college_scope_and_canteen_aliases_are_structured(client: TestClient):
    del client
    with SessionLocal() as db:
        campus_id = _qingyuan_id()
        two_plus_two = list(db.scalars(select(CampusCollege).where(
            CampusCollege.campus_id == campus_id, CampusCollege.education_mode == "2+2", CampusCollege.verified.is_(True)
        )))
        assert len(two_plus_two) == 13
        assert {row.name for row in two_plus_two} >= {"金融与投资学院", "国家金融学学院"}
        scope = db.scalar(select(CampusFact).where(CampusFact.campus_id == campus_id, CampusFact.predicate == "学院统计口径"))
        assert "不等于清远校区全部教学组织" in scope.object
        canteen = db.scalar(select(CampusFact).where(CampusFact.campus_id == campus_id, CampusFact.predicate == "核验口径"))
        assert all(name in canteen.object for name in ("南区饭堂", "北区饭堂", "西饭"))
        assert "用户报告" in canteen.object


def test_college_question_synonyms_override_generic_model_routing():
    class GenericRoutingLLM:
        async def chat_completion(self, *_args, **_kwargs):
            return '{"intent":"general_chat","confidence":0.9,"query":"清远校区有几个学院？","tool_plan":[]}'

    decision = asyncio.run(IntentClassifier(GenericRoutingLLM()).classify("清远校区有几个学院？"))
    assert decision.intent == "campus_fact_search"
    assert decision.tool_plan == ["search_campus_facts", "list_campus_colleges"]


def test_reminder_plan_cannot_bypass_confirmation_preview():
    class UnsafePlannerLLM:
        async def chat_completion(self, *_args, **_kwargs):
            return (
                '{"intent":"reminder_management","goal":"设置提醒","steps":'
                '[{"tool":"parse_deadline","purpose":"解析","arguments":{}},'
                '{"tool":"create_task","purpose":"直接写入","arguments":{"confirmed":true}}],'
                '"required_tools":["parse_deadline","create_task"],"requires_knowledge":true,'
                '"requires_confirmation":false,"missing_information":[],"risk_level":"low",'
                '"risks":[],"agent_round":1}'
            )

    decision = IntentDecision(
        intent="reminder_management",
        confidence=0.99,
        query="明天下午3点提醒我交作业",
        tool_plan=["preview_reminder"],
    )
    plan = asyncio.run(Planner(UnsafePlannerLLM()).build(decision, decision.query))
    assert plan.required_tools == ["preview_reminder"]
    assert [step.tool for step in plan.steps] == ["preview_reminder"]


def test_note_crud_and_ownership(client: TestClient, register_user):
    register_user("note-owner")
    created = client.post("/api/notes", json={"title": "高数复习", "content": "先补极限", "tags": ["学习"], "confirmed": True})
    assert created.status_code == 201
    note_id = created.json()["id"]
    assert client.patch(f"/api/notes/{note_id}", json={"pinned": True, "confirmed": True}).json()["pinned"] is True
    register_user("note-other")
    assert client.patch(f"/api/notes/{note_id}", json={"title": "越权", "confirmed": True}).status_code == 404
    with SessionLocal() as db:
        assert db.get(Note, note_id).title == "高数复习"


def test_reminder_preview_crud_due_trigger_and_ownership(client: TestClient, register_user):
    owner = register_user("reminder-owner")
    preview = client.post("/api/reminders/preview", json={"text": "明天下午3点提醒我交作业"})
    assert preview.status_code == 200
    assert preview.json()["timezone"] == "Asia/Shanghai"
    assert preview.json()["remind_at"]
    created = client.post("/api/reminders", json={
        "title": "交作业", "body": "测试", "remind_at": (now_china() + timedelta(minutes=5)).isoformat(),
        "channels": ["in_app"], "confirmed": True,
    })
    assert created.status_code == 201
    reminder_id = created.json()["id"]
    register_user("reminder-other")
    assert client.patch(f"/api/reminders/{reminder_id}", json={"status": "cancelled", "confirmed": True}).status_code == 404
    with SessionLocal() as db:
        row = db.get(Reminder, reminder_id)
        row.remind_at = now_china() - timedelta(minutes=1)
        db.commit()
    login = client.post("/api/auth/login", json={"email": owner["email"], "password": owner["password"]})
    assert login.status_code == 200
    due = client.post("/api/reminders/check")
    assert due.status_code == 200
    assert due.json()[0]["id"] == reminder_id
    assert due.json()[0]["status"] == "triggered"


def test_stream_endpoint_emits_safe_stages_tokens_and_final(client: TestClient, register_user):
    register_user("stream-user")
    with client.stream("POST", "/api/agent/chat/stream", json={"message": "高数跟不上怎么办"}) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: stage" in body
    assert "event: token" in body
    assert "event: final" in body
    assert "reasoning_content" not in body


def test_notification_to_task_creates_new_reminder_records(client: TestClient, register_user):
    register_user("notification-reminder")
    deadline = (now_china() + timedelta(days=3)).isoformat()
    item = {
        "title": "提交材料", "action": "上传PDF", "audience": [], "conditions": [], "deadline_text": deadline,
        "deadline": deadline, "location": "", "submission_method": "线上", "submission_target": "", "file_naming": "",
        "materials": [], "evidence_requirements": [], "notes": [], "confidence": 1, "needs_confirmation": False,
        "is_expired": False, "date_explanation": "明确时间", "source_title": "测试通知", "source_text": "测试", "source_url": "",
    }
    response = client.post("/api/notifications/confirm", json={"action_items": [item], "confirmed": True})
    assert response.status_code == 201
    task_id = response.json()[0]["id"]
    with SessionLocal() as db:
        rows = list(db.scalars(select(Reminder).where(Reminder.task_id == task_id)))
        assert len(rows) == 2
        assert all(row.timezone == "Asia/Shanghai" for row in rows)
