from datetime import datetime

from icalendar import Calendar

from core.time_service import CHINA_TZ
from services.notification_service import NotificationService
from services.task_service import TaskService
from tools.ics_tool import generate_ics_bytes


REFERENCE = datetime(2026, 8, 2, 10, tzinfo=CHINA_TZ)


def test_confirmation_user_isolation_lifecycle_and_ics(tmp_path):
    db_path = tmp_path / "tasks.db"
    service = TaskService(db_path)
    drafts = NotificationService().extract_fallback(
        "申请表提交\n截止：9月3日下午5点\n地点：北教\n材料：申请表、学生证\n提交方式：纸质版",
        REFERENCE,
        "https://example.invalid/notice",
    )

    try:
        service.create_from_drafts("student-a", drafts, confirmed=False)
    except ValueError as exc:
        assert "必须确认" in str(exc)
    else:
        raise AssertionError("未确认的通知不应创建任务")

    created = service.create_from_drafts("student-a", drafts, confirmed=True)
    assert len(created) == 1
    assert service.list_tasks("student-b") == []
    assert service.get_task(created[0].id, "student-b") is None

    service.complete_task(created[0].id, "student-a")
    assert service.get_task(created[0].id, "student-a").status == "completed"
    service.reopen_task(created[0].id, "student-a")
    assert service.get_task(created[0].id, "student-a").status == "pending"

    payload = generate_ics_bytes([created[0].to_dict()], REFERENCE)
    calendar = Calendar.from_ical(payload)
    events = [component for component in calendar.walk() if component.name == "VEVENT"]
    assert len(events) == 1
    assert str(events[0]["summary"]) == created[0].title
    assert events[0].decoded("dtstart").utcoffset().total_seconds() == 8 * 3600


def test_task_update_requires_owner(tmp_path):
    service = TaskService(tmp_path / "tasks.db")
    item = service.create_task("owner", "任务", confirmed=True)
    try:
        service.complete_task(item.id, "other")
    except ValueError as exc:
        assert "不属于当前用户" in str(exc)
    else:
        raise AssertionError("其他用户不应能更新任务")
