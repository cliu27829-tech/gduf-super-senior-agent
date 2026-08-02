"""China-time aware date parsing and freshness helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Any
from zoneinfo import ZoneInfo


CHINA_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class DateInference:
    """A parsed date plus the uncertainty created by natural-language inference."""

    value: datetime | None
    inferred_year: bool = False
    requires_confirmation: bool = False
    confidence: float = 1.0
    explanation: str = ""

    def isoformat(self) -> str | None:
        return self.value.isoformat() if self.value else None


def _as_china_datetime(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(CHINA_TZ)
    if value.tzinfo is None:
        return value.replace(tzinfo=CHINA_TZ)
    return value.astimezone(CHINA_TZ)


def now_china(reference_time: datetime | None = None) -> datetime:
    """Return the current China Standard Time, or a normalized injected time."""

    return _as_china_datetime(reference_time)


def today_china(reference_time: datetime | None = None) -> date:
    return now_china(reference_time).date()


def current_year_china(reference_time: datetime | None = None) -> int:
    return now_china(reference_time).year


def format_current_time_prompt(reference_time: datetime | None = None) -> str:
    current = now_china(reference_time)
    return (
        f"当前中国标准时间：{current:%Y-%m-%d %H:%M}。"
        "请以此日期理解‘今天、明天、今年、下周’等相对时间。"
    )


def infer_missing_year(
    month: int,
    day: int,
    hour: int = 23,
    minute: int = 59,
    reference_time: datetime | None = None,
) -> DateInference:
    """Infer a missing year without silently turning an already-past date into fact."""

    reference = now_china(reference_time)
    try:
        candidate = datetime(reference.year, month, day, hour, minute, tzinfo=CHINA_TZ)
    except ValueError as exc:
        return DateInference(None, True, True, 0.0, f"无效日期：{exc}")

    if candidate >= reference - timedelta(minutes=1):
        return DateInference(
            candidate,
            inferred_year=True,
            requires_confirmation=False,
            confidence=0.85,
            explanation=f"未写年份，按中国时间推断为 {reference.year} 年。",
        )

    try:
        next_year = candidate.replace(year=reference.year + 1)
    except ValueError:
        next_year = candidate.replace(year=reference.year + 1, day=28)
    return DateInference(
        next_year,
        inferred_year=True,
        requires_confirmation=True,
        confidence=0.45,
        explanation=(
            f"按 {reference.year} 年理解会落在过去，暂推断为 {reference.year + 1} 年；"
            "保存任务前请确认年份。"
        ),
    )


def _parse_clock(text: str) -> tuple[int, int]:
    # A bare number is often the month/day. Require a day-part marker or a
    # clock separator so "9月3日下午5点" resolves to 17:00, not 21:00.
    match = re.search(
        r"(?:(?P<period>上午|下午|中午|晚上|傍晚)\s*(?P<hour1>\d{1,2})"
        r"(?:[:：点时](?P<minute1>\d{1,2})?)?\s*分?|"
        r"(?P<hour2>\d{1,2})[:：点时](?P<minute2>\d{1,2})?\s*分?)",
        text,
    )
    if not match:
        return 23, 59
    hour = int(match.group("hour1") or match.group("hour2"))
    minute = int(match.group("minute1") or match.group("minute2") or 0)
    period = match.group("period") or ""
    if period in ("下午", "晚上", "傍晚") and hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    return min(hour, 23), min(minute, 59)


def parse_relative_datetime(
    text: str,
    reference_time: datetime | None = None,
) -> DateInference:
    """Parse common Chinese deadline expressions using China Standard Time."""

    reference = now_china(reference_time)
    normalized = re.sub(r"\s+", "", text or "")
    hour, minute = _parse_clock(normalized)

    explicit = re.search(
        r"(?P<year>20\d{2})[-/年](?P<month>\d{1,2})[-/月](?P<day>\d{1,2})日?",
        normalized,
    )
    if explicit:
        try:
            value = datetime(
                int(explicit.group("year")),
                int(explicit.group("month")),
                int(explicit.group("day")),
                hour,
                minute,
                tzinfo=CHINA_TZ,
            )
        except ValueError as exc:
            return DateInference(None, False, True, 0.0, f"无效日期：{exc}")
        passed = value < reference
        return DateInference(
            value,
            inferred_year=False,
            requires_confirmation=passed,
            confidence=0.6 if passed else 1.0,
            explanation="通知中的明确日期已经过去，请确认是否仍需创建任务。" if passed else "使用通知中的明确年份。",
        )

    month_day = re.search(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日?", normalized)
    if month_day:
        return infer_missing_year(
            int(month_day.group("month")),
            int(month_day.group("day")),
            hour,
            minute,
            reference,
        )

    day_offset: int | None = None
    if "大后天" in normalized:
        day_offset = 3
    elif "后天" in normalized:
        day_offset = 2
    elif "明天" in normalized or "明日" in normalized:
        day_offset = 1
    elif "今天" in normalized or "今日" in normalized:
        day_offset = 0
    if day_offset is not None:
        target = reference.date() + timedelta(days=day_offset)
        value = datetime.combine(target, time(hour, minute), CHINA_TZ)
        passed = value < reference
        return DateInference(
            value,
            inferred_year=False,
            requires_confirmation=passed,
            confidence=0.7 if passed else 0.95,
            explanation="相对日期按中国标准时间解释。" + ("该时刻已过去，请确认。" if passed else ""),
        )

    weekday_match = re.search(r"下周([一二三四五六日天])", normalized)
    if weekday_match:
        weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
        days_to_next_monday = 7 - reference.weekday()
        target = reference.date() + timedelta(
            days=days_to_next_monday + weekday_map[weekday_match.group(1)]
        )
        value = datetime.combine(target, time(hour, minute), CHINA_TZ)
        return DateInference(value, False, False, 0.9, "‘下周’按中国标准时间所在周解释。")

    return DateInference(None, False, True, 0.0, "没有识别到可验证的日期，请补充截止时间。")


def parse_datetime_value(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _as_china_datetime(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, CHINA_TZ)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _as_china_datetime(parsed)


def is_stale(
    timestamp: datetime | date | str | None,
    threshold_days: int,
    reference_time: datetime | None = None,
) -> bool:
    parsed = parse_datetime_value(timestamp)
    if parsed is None:
        return True
    return now_china(reference_time) - parsed > timedelta(days=threshold_days)
