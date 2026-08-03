"""Notification extraction compatibility helpers and China-time ICS generation."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable
import uuid

from icalendar import Calendar, Event

from core.time_service import CHINA_TZ, now_china, parse_datetime_value
from services.notification_service import NotificationService


def extract_tasks_from_text(text: str, openai_api_key: str = "", reference_time=None) -> list[dict[str, Any]]:
    drafts = NotificationService().extract(text, openai_api_key, reference_time)
    return [
        {
            "name": draft.title,
            "title": draft.title,
            "deadline": draft.deadline,
            "location": draft.location,
            "materials": draft.materials,
            "submission_method": draft.submission_method,
            "source_text": draft.source_text,
            "needs_confirmation": draft.needs_confirmation,
            "date_explanation": draft.date_explanation,
        }
        for draft in drafts
    ]


def generate_ics_bytes(tasks: Iterable[dict[str, Any]], reference_time=None) -> bytes:
    calendar = Calendar()
    calendar.add("prodid", "-//GDUF Super Senior Agent//Calendar//CN")
    calendar.add("version", "2.0")
    calendar.add("name", "广金大师兄任务日历")
    calendar.add("X-WR-TIMEZONE", "Asia/Shanghai")
    for task in tasks:
        deadline = parse_datetime_value(task.get("deadline"))
        if not deadline:
            continue
        event = Event()
        event.add("summary", task.get("title") or task.get("name") or "未命名任务")
        event.add("dtstart", deadline.astimezone(CHINA_TZ))
        event.add("dtend", deadline.astimezone(CHINA_TZ) + timedelta(hours=1))
        if task.get("location"):
            event.add("location", task["location"])
        details = []
        if task.get("materials"):
            details.append("材料：" + "、".join(task["materials"]))
        if task.get("submission_method"):
            details.append("提交方式：" + task["submission_method"])
        if task.get("source_text"):
            details.append("来源通知：" + task["source_text"][:500])
        if details:
            event.add("description", "\n".join(details))
        event.add("uid", f"{task.get('id') or uuid.uuid4()}@gduf-agent")
        event.add("dtstamp", now_china(reference_time))
        calendar.add_component(event)
    return calendar.to_ical()


def generate_ics_file(
    tasks: Iterable[dict[str, Any]],
    filename: str | Path | None = None,
    reference_time=None,
) -> str:
    if filename is None:
        export_dir = Path("data/exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        filename = export_dir / f"gduf-tasks-{uuid.uuid4().hex}.ics"
    output = Path(filename)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(generate_ics_bytes(tasks, reference_time))
    return str(output)


def process_notification(
    text: str,
    openai_api_key: str = "",
    output_filename: str | Path | None = None,
    reference_time=None,
):
    tasks = extract_tasks_from_text(text, openai_api_key, reference_time)
    if not tasks:
        return None, "未从文本中提取到任务信息"
    return generate_ics_file(tasks, output_filename, reference_time), tasks
