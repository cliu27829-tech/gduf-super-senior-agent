from __future__ import annotations

import asyncio
from datetime import datetime
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.services.notification_service import NotificationService, normalize_notice_text
from app.services.time_service import CHINA_TZ, parse_deadline, parse_notice_context, parse_relative_datetime


REFERENCE = datetime(2026, 8, 9, 12, 0, tzinfo=CHINA_TZ)
FIXTURE = Path(__file__).parent / "fixtures" / "real_notifications" / "zhengda_cup.txt"


def zhengda_result():
    return NotificationService().fallback(FIXTURE.read_text(encoding="utf-8"), reference_time=REFERENCE)


def test_normalize_notice_text_handles_emoji_fullwidth_punctuation_and_numbering():
    normalized = normalize_notice_text("🍊通知\r\n① 提交材料\r\n2、截止时间：8月6日22：00‼️")
    assert "🍊" not in normalized
    assert "‼" not in normalized
    assert "①. 提交材料" in normalized
    assert "2. 截止时间:8月6日22:00" in normalized


def test_notice_context_prefers_title_date():
    context = parse_notice_context("【8.5校青成通知——测试】\n截止时间：8月6日22:00", REFERENCE)
    assert context.source == "title"
    assert context.notice_reference_date.isoformat() == "2026-08-05T00:00:00+08:00"


def test_notice_context_reads_explicit_body_publication_date():
    context = parse_notice_context("课程通知\n截止时间：4月2日17:00\n教务处\n2026年3月10日", REFERENCE)
    assert context.source == "body"
    assert context.notice_reference_date.date().isoformat() == "2026-03-10"


def test_notice_context_does_not_treat_deadline_as_publication_date():
    context = parse_notice_context("课程通知\n截止时间：2026年4月2日17:00", REFERENCE)
    assert context.notice_reference_date is None


def test_deadline_is_anchored_to_notice_year_even_when_expired():
    parsed = parse_deadline("8月6日22：00", datetime(2026, 8, 5, tzinfo=CHINA_TZ), REFERENCE)
    assert parsed.value.isoformat() == "2026-08-06T22:00:00+08:00"
    assert parsed.requires_confirmation is False
    assert "通知日期" in parsed.explanation


def test_past_missing_year_without_notice_stays_in_current_year():
    parsed = parse_deadline("8月6日22:00", current_time=REFERENCE)
    assert parsed.value.year == 2026
    assert parsed.requires_confirmation is True
    assert "已经过去" in parsed.explanation


def test_explicit_year_is_never_rewritten():
    parsed = parse_deadline("截止2025年8月6日22:00", current_time=REFERENCE)
    assert parsed.value.isoformat() == "2025-08-06T22:00:00+08:00"
    assert parsed.requires_confirmation is False


def test_invalid_date_returns_no_value():
    parsed = parse_deadline("2月30日", datetime(2026, 2, 1, tzinfo=CHINA_TZ), REFERENCE)
    assert parsed.value is None
    assert parsed.requires_confirmation is True


def test_relative_dates_use_notice_anchor():
    anchor = datetime(2026, 8, 5, tzinfo=CHINA_TZ)
    assert parse_deadline("明天17:00", anchor, REFERENCE).value.isoformat() == "2026-08-06T17:00:00+08:00"
    assert parse_deadline("下周一参加培训", anchor, REFERENCE).value.date().isoformat() == "2026-08-10"


def test_relative_range_and_month_end_require_confirmation():
    anchor = datetime(2026, 8, 3, tzinfo=CHINA_TZ)
    within = parse_deadline("三天内", anchor, REFERENCE)
    month_end = parse_deadline("月底", anchor, REFERENCE)
    assert within.value.date().isoformat() == "2026-08-06"
    assert within.requires_confirmation is True
    assert month_end.value.isoformat() == "2026-08-31T23:59:00+08:00"


def test_compatibility_relative_parser_no_longer_rolls_to_next_year():
    parsed = parse_relative_datetime("1月3日上午9点", REFERENCE)
    assert parsed.value.isoformat() == "2026-01-03T09:00:00+08:00"
    assert parsed.requires_confirmation is True


def test_zhengda_notice_title_date_campuses_and_audience():
    result = zhengda_result()
    assert result.notice.title == "关于正大杯（全国市调赛）加分通知"
    assert result.notice.notice_date.date().isoformat() == "2026-08-05"
    assert result.notice.campuses == ["广州校区", "清远校区"]
    assert "二课负责人" in result.notice.audience


def test_zhengda_notice_has_three_rules_and_one_action():
    result = zhengda_result()
    assert len(result.rules) == 3
    assert len(result.action_items) == 1
    assert result.action_items[0].title == "收集并提交正大杯加分补录材料"


def test_zhengda_notice_conditions_are_merged_into_the_action():
    conditions = zhengda_result().action_items[0].conditions
    assert conditions == ["班级已经提交创新创业修正补录表", "校赛没有补录成功的同学"]


def test_zhengda_notice_deadline_is_expired_not_next_year():
    action = zhengda_result().action_items[0]
    assert action.deadline.isoformat() == "2026-08-06T22:00:00+08:00"
    assert action.is_expired is True
    assert action.needs_confirmation is False


def test_zhengda_notice_keeps_exact_zip_naming():
    assert zhengda_result().action_items[0].file_naming == "正大杯-24/25+学院+专业+班级"


def test_zhengda_notice_keeps_evidence_requirements():
    evidence = zhengda_result().action_items[0].evidence_requirements
    assert evidence == [
        "证明材料需要有表头",
        "证明材料需要有公章",
        "通知所示的正大杯奖状图片可以作为证明材料",
    ]


def test_zhengda_notice_does_not_fabricate_email_address():
    action = zhengda_result().action_items[0]
    assert action.submission_method == "邮件发送 ZIP 文件"
    assert action.submission_target == "邮箱"
    assert "@" not in json.dumps(action.model_dump(mode="json"), ensure_ascii=False)


def test_zhengda_notice_preserves_the_raw_original_text():
    action = zhengda_result().action_items[0]
    assert "🍊" in action.source_text
    assert "⭕" in action.source_text
    assert "8月6日22：00" in action.source_text


def test_expired_notice_has_friendly_warning():
    assert any("截止时间已经过了" in warning for warning in zhengda_result().warnings)


def test_rules_only_notice_has_zero_actions():
    result = NotificationService().fallback("本次比赛加分调整为一等奖0.5，二等奖0.3。", reference_time=REFERENCE)
    assert result.action_items == []
    assert result.rules


def test_multi_action_notice_creates_three_actions_not_one_per_number():
    result = NotificationService().fallback("周五前交报名表；下周一参加培训；培训后提交心得。", reference_time=REFERENCE)
    assert [item.title for item in result.action_items] == ["提交报名表", "参加培训", "提交心得"]


def test_conditional_action_keeps_condition_and_real_action():
    result = NotificationService().fallback("如果已经提交旧版本，需要重新提交新版。", reference_time=REFERENCE)
    assert len(result.action_items) == 1
    assert result.action_items[0].conditions == ["已经提交旧版本"]
    assert result.action_items[0].title == "提交新版"


def test_material_requirement_does_not_create_a_task():
    result = NotificationService().fallback("证明材料需要表头和公章。", reference_time=REFERENCE)
    assert result.action_items == []


def test_email_address_is_kept_only_when_present():
    result = NotificationService().fallback("请将报名表发送到example@gduf.edu.cn。", reference_time=REFERENCE)
    assert result.action_items[0].submission_target == "example@gduf.edu.cn"


def test_no_deadline_keeps_null_and_requires_no_date_guess():
    result = NotificationService().fallback("请提交班级报名表。", reference_time=REFERENCE)
    assert result.action_items[0].deadline is None
    assert result.action_items[0].deadline_text == ""


def test_multiple_deadlines_stay_with_their_actions():
    text = "周五17:00前提交报名表；下周一9:00参加培训。"
    result = NotificationService().fallback(text, reference_time=REFERENCE)
    assert len(result.deadlines) == 2
    assert result.deadlines[0].deadline != result.deadlines[1].deadline


def test_model_schema_failure_is_repaired_exactly_once():
    valid = {
        "notice": {"title": "测试通知"},
        "rules": [],
        "action_items": [{"title": "提交材料", "action": "提交材料", "deadline_text": ""}],
        "warnings": [],
    }

    class RepairingLLM:
        configured = True

        def __init__(self):
            self.calls = 0

        async def chat_completion(self, *_args, **_kwargs):
            self.calls += 1
            return "not-json" if self.calls == 1 else json.dumps(valid, ensure_ascii=False)

    llm = RepairingLLM()
    result = asyncio.run(NotificationService().with_model("请提交材料", llm=llm, reference_time=REFERENCE))
    assert llm.calls == 2
    assert result.extraction_mode == "llm"
    assert result.action_items[0].title == "提交材料"


def test_model_is_not_repaired_more_than_once_and_falls_back_without_secret():
    secret = "sensitive-parser-key"

    class BrokenLLM:
        configured = True

        def __init__(self):
            self.calls = 0

        async def chat_completion(self, *_args, **_kwargs):
            self.calls += 1
            raise ValueError(secret)

    llm = BrokenLLM()
    result = asyncio.run(NotificationService().extract("请提交报名表", llm=llm, reference_time=REFERENCE))
    assert llm.calls == 2
    assert result.extraction_mode == "rules"
    assert secret not in result.model_dump_json()


def test_notification_preview_expired_save_requires_manual_override(client: TestClient, register_user):
    register_user("notice")
    preview = client.post("/api/notifications/parse", data={"text": FIXTURE.read_text(encoding="utf-8")})
    assert preview.status_code == 200
    body = preview.json()
    assert len(body["action_items"]) == 1
    denied = client.post("/api/notifications/confirm", json={"action_items": body["action_items"], "confirmed": True})
    assert denied.status_code == 422
    saved = client.post(
        "/api/notifications/confirm",
        json={"action_items": body["action_items"], "confirmed": True, "allow_expired": True},
    )
    assert saved.status_code == 201
    task = saved.json()[0]
    assert task["title"] == "收集并提交正大杯加分补录材料"
    assert task["is_expired"] is True
    assert task["conditions"]
    assert task["evidence_requirements"]
    assert "🍊" in task["source_text"]


def test_txt_upload_and_image_ocr_rejection(client: TestClient, register_user):
    register_user("upload")
    txt = client.post(
        "/api/notifications/parse",
        files={"file": ("notice.txt", "作业通知\n请提交报告", "text/plain")},
    )
    assert txt.status_code == 200
    image = client.post(
        "/api/notifications/parse",
        files={"file": ("notice.png", b"not-an-image", "image/png")},
    )
    assert image.status_code == 415
    assert "OCR" in image.json()["detail"]


def test_empty_notification_is_rejected(client: TestClient, register_user):
    register_user("empty")
    assert client.post("/api/notifications/parse", data={"text": ""}).status_code == 422
