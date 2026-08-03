from __future__ import annotations

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


def _parse_clock(text: str) -> tuple[int, int]:
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
    if period in {"下午", "晚上", "傍晚"} and hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    return min(hour, 23), min(minute, 59)


def infer_missing_year(month: int, day: int, hour: int, minute: int, reference_time: datetime) -> DateInference:
    reference = now_china(reference_time)
    try:
        candidate = datetime(reference.year, month, day, hour, minute, tzinfo=CHINA_TZ)
    except ValueError as exc:
        return DateInference(None, True, True, 0.0, f"无效日期：{exc}")
    if candidate >= reference - timedelta(minutes=1):
        return DateInference(candidate, True, False, 0.85, f"未写年份，按中国时间推断为 {reference.year} 年。")
    try:
        next_year = candidate.replace(year=reference.year + 1)
    except ValueError:
        next_year = candidate.replace(year=reference.year + 1, day=28)
    return DateInference(
        next_year,
        True,
        True,
        0.45,
        f"按 {reference.year} 年理解会落在过去，暂推断为 {reference.year + 1} 年；保存前请确认。",
    )


def parse_relative_datetime(text: str, reference_time: datetime | None = None) -> DateInference:
    reference = now_china(reference_time)
    normalized = re.sub(r"\s+", "", text or "")
    hour, minute = _parse_clock(normalized)
    explicit = re.search(r"(?P<year>20\d{2})[-/年](?P<month>\d{1,2})[-/月](?P<day>\d{1,2})日?", normalized)
    if explicit:
        try:
            value = datetime(
                int(explicit.group("year")), int(explicit.group("month")), int(explicit.group("day")),
                hour, minute, tzinfo=CHINA_TZ,
            )
        except ValueError as exc:
            return DateInference(None, False, True, 0.0, f"无效日期：{exc}")
        passed = value < reference
        return DateInference(value, False, passed, 0.6 if passed else 1.0, "明确日期已过去，请确认。" if passed else "使用通知中的明确年份。")
    month_day = re.search(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日?", normalized)
    if month_day:
        return infer_missing_year(int(month_day.group("month")), int(month_day.group("day")), hour, minute, reference)
    offsets = {"大后天": 3, "后天": 2, "明天": 1, "明日": 1, "今天": 0, "今日": 0}
    for word, offset in offsets.items():
        if word in normalized:
            value = datetime.combine(reference.date() + timedelta(days=offset), time(hour, minute), CHINA_TZ)
            passed = value < reference
            return DateInference(value, False, passed, 0.7 if passed else 0.95, "相对日期按中国标准时间解释。" + ("该时刻已过去，请确认。" if passed else ""))
    weekday = re.search(r"下周([一二三四五六日天])", normalized)
    if weekday:
        weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
        target = reference.date() + timedelta(days=7 - reference.weekday() + weekday_map[weekday.group(1)])
        return DateInference(datetime.combine(target, time(hour, minute), CHINA_TZ), False, False, 0.9, "‘下周’按中国标准时间所在周解释。")
    return DateInference(None, False, True, 0.0, "没有识别到可验证的日期，请补充截止时间。")


def freshness_status(verified_at: datetime | None, threshold_days: int = 180) -> str:
    if not verified_at:
        return "needs_verification"
    return "stale" if now_china() - now_china(verified_at) > timedelta(days=threshold_days) else "current"

