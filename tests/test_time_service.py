from datetime import datetime

from core.time_service import CHINA_TZ, format_current_time_prompt, parse_relative_datetime


REFERENCE = datetime(2026, 8, 2, 10, 30, tzinfo=CHINA_TZ)


def test_month_is_not_mistaken_for_clock_hour():
    result = parse_relative_datetime("请于9月3日下午5点前提交", REFERENCE)
    assert result.value == datetime(2026, 9, 3, 17, 0, tzinfo=CHINA_TZ)
    assert result.requires_confirmation is False


def test_missing_year_rolls_forward_with_confirmation_if_current_year_date_passed():
    result = parse_relative_datetime("1月1日前提交", REFERENCE)
    assert result.value == datetime(2027, 1, 1, 23, 59, tzinfo=CHINA_TZ)
    assert result.requires_confirmation is True
    assert "2027" in result.explanation


def test_relative_date_and_dynamic_prompt_use_injected_china_time():
    result = parse_relative_datetime("明天上午9:30截止", REFERENCE)
    assert result.value == datetime(2026, 8, 3, 9, 30, tzinfo=CHINA_TZ)
    assert "2026-08-02 10:30" in format_current_time_prompt(REFERENCE)


def test_explicit_past_date_is_not_silently_treated_as_current():
    result = parse_relative_datetime("2025年9月3日下午5点", REFERENCE)
    assert result.requires_confirmation is True
    assert "已经过去" in result.explanation
