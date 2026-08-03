from __future__ import annotations

from datetime import timedelta

from icalendar import Alarm, Calendar, Event

from app.models.entities import Task
from app.services.time_service import CHINA_TZ, now_china


def generate_ics(tasks: list[Task], reminder_minutes: list[int] | None = None) -> bytes:
    reminders = sorted(set(reminder_minutes or [1440, 180]), reverse=True)
    calendar = Calendar()
    calendar.add("prodid", "-//GDUF Super Senior//Tasks//CN")
    calendar.add("version", "2.0")
    calendar.add("name", "广金大师兄任务日历")
    calendar.add("X-WR-TIMEZONE", "Asia/Shanghai")
    for task in tasks:
        if not task.deadline:
            continue
        deadline = task.deadline.replace(tzinfo=CHINA_TZ) if task.deadline.tzinfo is None else task.deadline.astimezone(CHINA_TZ)
        event = Event()
        event.add("uid", f"{task.id}@gduf-super-senior")
        event.add("summary", task.title)
        event.add("dtstart", deadline)
        event.add("dtend", deadline + timedelta(hours=1))
        event.add("dtstamp", now_china())
        if task.location:
            event.add("location", task.location)
        description = []
        if task.materials:
            description.append("材料：" + "、".join(task.materials))
        if task.submission_target:
            description.append("提交对象：" + task.submission_target)
        if task.submission_method:
            description.append("提交方式：" + task.submission_method)
        if task.file_naming:
            description.append("文件命名：" + task.file_naming)
        if task.source_url:
            description.append("来源：" + task.source_url)
        if task.source_text:
            description.append("原始通知：" + task.source_text[:1000])
        if task.description:
            description.append("备注：" + task.description)
        event.add("description", "\n".join(description))
        for minutes in reminders:
            if minutes <= 0:
                continue
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", f"任务提醒：{task.title}")
            alarm.add("trigger", timedelta(minutes=-minutes))
            event.add_component(alarm)
        calendar.add_component(event)
    payload = calendar.to_ical()
    parsed = Calendar.from_ical(payload)
    events = list(parsed.walk("VEVENT"))
    if not events:
        raise ValueError("没有包含截止时间的任务可导出")
    if any(len(list(event.walk("VALARM"))) != len(reminders) for event in events):
        raise ValueError("ICS 提醒校验失败")
    if b"Asia/Shanghai" not in payload:
        raise ValueError("ICS 时区校验失败")
    return payload
