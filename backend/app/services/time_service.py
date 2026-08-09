from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from zoneinfo import ZoneInfo


CHINA_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class DateInference:
    value: datetime | None
    inferred_year: bool = False
    requires_confirmation: bool = False
    confidence: float = 1.0
    explanation: str = ""


@dataclass(frozen=True)
class NoticeContext:
    notice_reference_date: datetime | None
    notice_date_text: str = ""
    source: str = "none"


def now_china(reference_time: datetime | None = None) -> datetime:
    if reference_time is None:
        return datetime.now(CHINA_TZ)
    if reference_time.tzinfo is None:
        return reference_time.replace(tzinfo=CHINA_TZ)
    return reference_time.astimezone(CHINA_TZ)


def parse_datetime(value: str | datetime | date | None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return now_china(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, CHINA_TZ)
    try:
        return now_china(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _clock(text: str) -> tuple[int, int]:
    match = re.search(r"(?:(上午|下午|中午|晚上|傍晚)\s*)?(\d{1,2})\s*[:：]\s*(\d{1,2})", text)
    if not match:
        match = re.search(r"(?:(上午|下午|中午|晚上|傍晚)\s*)?(\d{1,2})\s*[点时]\s*(\d{1,2})?\s*分?", text)
    if not match:
        match = re.search(r"(上午|下午|中午|晚上|傍晚)\s*(\d{1,2})", text)
    if not match:
        return 23, 59
    period, hour_text, minute_text = match.groups()
    hour = int(hour_text)
    minute = int(minute_text or 0)
    if period in {"下午", "晚上", "傍晚"} and hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    return min(hour, 23), min(minute, 59)


def _safe_datetime(year: int, month: int, day: int, hour: int, minute: int) -> datetime | None:
    try:
        return datetime(year, month, day, hour, minute, tzinfo=CHINA_TZ)
    except ValueError:
        return None


def parse_notice_context(
    text: str,
    reference_time: datetime | None = None,
    *,
    source_published_at: datetime | None = None,
    user_reference_date: datetime | None = None,
) -> NoticeContext:
    """Find a notice date without treating a deadline as the publication date."""
    current = now_china(reference_time)
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    title = lines[0] if lines else ""

    full_title = re.search(r"(?:【|^)[^\n】]{0,30}?(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", title)
    if full_title:
        value = _safe_datetime(*(int(item) for item in full_title.groups()), 0, 0)
        if value:
            return NoticeContext(value, full_title.group(0).strip("【"), "title")

    short_title = re.search(r"(?:【|^)\s*(\d{1,2})[.月/-](\d{1,2})(?:日)?", title)
    if short_title:
        month, day = (int(item) for item in short_title.groups())
        value = _safe_datetime(current.year, month, day, 0, 0)
        if value:
            return NoticeContext(value, short_title.group(0).strip("【"), "title")

    # Prefer explicit publisher/date lines near the end. Lines mentioning deadlines
    # are deliberately excluded so an action deadline cannot become the notice date.
    for line in reversed(lines):
        if re.search(r"截止|报名时间|提交时间|考试时间", line):
            continue
        full = re.fullmatch(r"(?:[^\d\n]{0,20})?(20\d{2})年(\d{1,2})月(\d{1,2})日", line)
        if full:
            value = _safe_datetime(*(int(item) for item in full.groups()), 0, 0)
            if value:
                return NoticeContext(value, full.group(0), "body")

    if source_published_at:
        value = now_china(source_published_at).replace(hour=0, minute=0, second=0, microsecond=0)
        return NoticeContext(value, value.strftime("%Y-%m-%d"), "source_metadata")
    if user_reference_date:
        value = now_china(user_reference_date).replace(hour=0, minute=0, second=0, microsecond=0)
        return NoticeContext(value, value.strftime("%Y-%m-%d"), "user_reference")
    return NoticeContext(None, "", "none")


_CHINESE_NUMBER = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _day_count(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value in _CHINESE_NUMBER:
        return _CHINESE_NUMBER[value]
    if value.startswith("十") and len(value) == 2:
        return 10 + _CHINESE_NUMBER.get(value[1], 0)
    return None


def parse_deadline(
    deadline_text: str,
    notice_reference_date: datetime | None = None,
    current_time: datetime | None = None,
) -> DateInference:
    current = now_china(current_time)
    anchor = now_china(notice_reference_date) if notice_reference_date else None
    normalized = re.sub(r"\s+", "", deadline_text or "")
    hour, minute = _clock(normalized)

    explicit = re.search(r"(?P<year>20\d{2})[年./-](?P<month>\d{1,2})[月./-](?P<day>\d{1,2})日?", normalized)
    if explicit:
        value = _safe_datetime(
            int(explicit.group("year")),
            int(explicit.group("month")),
            int(explicit.group("day")),
            hour,
            minute,
        )
        if not value:
            return DateInference(None, False, True, 0.0, "通知中的截止日期无效，请人工确认。")
        return DateInference(value, False, False, 1.0, "使用通知中明确写出的完整日期。")

    month_day = re.search(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日?", normalized)
    if month_day:
        month = int(month_day.group("month"))
        day = int(month_day.group("day"))
        year = (anchor or current).year
        value = _safe_datetime(year, month, day, hour, minute)
        # Only a notice anchored at year-end may naturally point into next January.
        if value and anchor and anchor.month >= 11 and month <= 2 and value < anchor - timedelta(days=30):
            value = _safe_datetime(year + 1, month, day, hour, minute)
        if not value:
            return DateInference(None, True, True, 0.0, "通知中的无年份截止日期无效，请人工确认。")
        if anchor:
            return DateInference(
                value,
                True,
                False,
                0.95,
                f"截止日期未写年份，已按通知日期锚定为 {value.strftime('%Y-%m-%d %H:%M')}。",
            )
        passed = value < current
        return DateInference(
            value,
            True,
            True,
            0.6 if passed else 0.75,
            f"截止日期未写年份且通知没有发布日期，暂按 {current.year} 年理解"
            + ("；该时间已经过去，请确认。" if passed else "；保存前请确认年份。"),
        )

    relative_base = anchor or current
    within = re.search(r"(\d+|[一二两三四五六七八九十]+)天内", normalized)
    if within and (count := _day_count(within.group(1))) is not None:
        value = datetime.combine(relative_base.date() + timedelta(days=count), time(hour, minute), CHINA_TZ)
        return DateInference(value, False, True, 0.7, f"“{within.group(0)}”按参考日期的最晚一天预览，保存前请确认。")

    after_days = re.search(r"(\d+|[一二两三四五六七八九十]+)天后", normalized)
    if after_days and (count := _day_count(after_days.group(1))) is not None:
        value = datetime.combine(relative_base.date() + timedelta(days=count), time(hour, minute), CHINA_TZ)
        return DateInference(value, False, not bool(anchor), 0.9 if anchor else 0.75, "相对天数按通知参考日期解析。")

    offsets = {"大后天": 3, "后天": 2, "明天": 1, "明日": 1, "今天": 0, "今日": 0}
    for word, offset in offsets.items():
        if word in normalized:
            value = datetime.combine(relative_base.date() + timedelta(days=offset), time(hour, minute), CHINA_TZ)
            return DateInference(value, False, not bool(anchor), 0.95 if anchor else 0.75, f"“{word}”按通知参考日期解析。")

    weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
    next_weekday = re.search(r"下周([一二三四五六日天])", normalized)
    if next_weekday:
        target = relative_base.date() + timedelta(days=7 - relative_base.weekday() + weekday_map[next_weekday.group(1)])
        return DateInference(datetime.combine(target, time(hour, minute), CHINA_TZ), False, not bool(anchor), 0.9, "“下周”按通知参考日期所在周解析。")
    this_weekday = re.search(r"(?:本周|周)([一二三四五六日天])", normalized)
    if this_weekday:
        target = relative_base.date() - timedelta(days=relative_base.weekday()) + timedelta(days=weekday_map[this_weekday.group(1)])
        value = datetime.combine(target, time(hour, minute), CHINA_TZ)
        return DateInference(value, False, not bool(anchor), 0.85, "星期表达按通知参考日期所在周解析。")

    if "月底" in normalized:
        day = monthrange(relative_base.year, relative_base.month)[1]
        value = datetime(relative_base.year, relative_base.month, day, hour, minute, tzinfo=CHINA_TZ)
        return DateInference(value, False, True, 0.7, "“月底”按通知参考日期所在月最后一天预览，保存前请确认。")

    return DateInference(None, False, True, 0.0, "没有识别到可验证的截止日期。")


def infer_missing_year(month: int, day: int, hour: int, minute: int, reference_time: datetime) -> DateInference:
    """Compatibility wrapper. Missing years no longer roll into the next year."""
    return parse_deadline(f"{month}月{day}日{hour:02d}:{minute:02d}", current_time=reference_time)


def parse_relative_datetime(text: str, reference_time: datetime | None = None) -> DateInference:
    return parse_deadline(text, current_time=reference_time)


def freshness_status(verified_at: datetime | None, threshold_days: int = 180) -> str:
    if not verified_at:
        return "needs_verification"
    return "stale" if now_china() - now_china(verified_at) > timedelta(days=threshold_days) else "current"
