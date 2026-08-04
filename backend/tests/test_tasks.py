from icalendar import Calendar
from fastapi.testclient import TestClient


def _task(title: str = "完成课程报告") -> dict:
    return {
        "title": title,
        "description": "注意格式",
        "deadline": "2099-09-03T17:00:00+08:00",
        "location": "教学平台",
        "course": "测试课程",
        "task_type": "assignment",
        "materials": ["课程报告", "附件"],
        "submission_target": "任课老师",
        "submission_method": "在线提交",
        "file_naming": "学号-姓名",
        "source_text": "测试通知",
        "confirmed": True,
        "reminder_minutes": [1440, 180],
    }


def test_task_crud_complete_reopen(client: TestClient, register_user):
    register_user("tasks")
    created = client.post("/api/tasks", json=_task())
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["submission_target"] == "任课老师"
    assert created.json()["file_naming"] == "学号-姓名"
    assert client.get(f"/api/tasks/{task_id}").status_code == 200
    assert client.patch(f"/api/tasks/{task_id}", json={"title": "未确认修改"}).status_code == 422
    updated = client.patch(f"/api/tasks/{task_id}", json={"title": "修改后的任务", "confirmed": True})
    assert updated.json()["title"] == "修改后的任务"
    assert client.post(f"/api/tasks/{task_id}/complete").status_code == 422
    assert client.post(f"/api/tasks/{task_id}/complete?confirmed=true").json()["status"] == "completed"
    assert client.post(f"/api/tasks/{task_id}/reopen?confirmed=true").json()["status"] == "pending"
    assert client.delete(f"/api/tasks/{task_id}").status_code == 422
    assert client.delete(f"/api/tasks/{task_id}?confirmed=true").status_code == 204
    assert client.get(f"/api/tasks/{task_id}").status_code == 404


def test_task_requires_confirmation(client: TestClient, register_user):
    register_user("confirm")
    payload = _task()
    payload["confirmed"] = False
    assert client.post("/api/tasks", json=payload).status_code == 422


def test_user_task_isolation(client: TestClient, register_user):
    owner = register_user("owner")
    task_id = client.post("/api/tasks", json=_task("私有任务")).json()["id"]
    other = register_user("other")
    assert owner["email"] != other["email"]
    assert client.get(f"/api/tasks/{task_id}").status_code == 404
    assert all(item["id"] != task_id for item in client.get("/api/tasks").json())


def test_ics_has_timezone_and_two_alarms(client: TestClient, register_user):
    register_user("ics")
    task_id = client.post("/api/tasks", json=_task("带提醒任务")).json()["id"]
    response = client.get(f"/api/tasks/export/ics?task_ids={task_id}")
    assert response.status_code == 200
    assert "text/calendar" in response.headers["content-type"]
    calendar = Calendar.from_ical(response.content)
    events = list(calendar.walk("VEVENT"))
    assert len(events) == 1
    alarms = list(events[0].walk("VALARM"))
    assert len(alarms) == 2
    assert b"Asia/Shanghai" in response.content
    assert "任课老师" in response.text
    assert "学号-姓名" in response.text


def test_bulk_task_actions(client: TestClient, register_user):
    register_user("bulk")
    ids = [client.post("/api/tasks", json=_task(f"批量任务{i}")).json()["id"] for i in range(2)]
    assert client.post("/api/tasks/bulk", json={"task_ids": ids, "action": "complete"}).status_code == 422
    assert client.post("/api/tasks/bulk", json={"task_ids": ids, "action": "complete", "confirmed": True}).status_code == 204
    assert all(item["status"] == "completed" for item in client.get("/api/tasks?status=completed").json() if item["id"] in ids)
