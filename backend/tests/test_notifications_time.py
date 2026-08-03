from datetime import datetime

from fastapi.testclient import TestClient

from app.services.time_service import CHINA_TZ, parse_relative_datetime
from app.schemas.agent import NotificationDraft
from app.services.notification_service import NotificationService


def test_month_is_not_parsed_as_hour():
    parsed = parse_relative_datetime("9月3日下午5点", datetime(2026, 8, 3, 9, 0, tzinfo=CHINA_TZ))
    assert parsed.value is not None
    assert parsed.value.isoformat() == "2026-09-03T17:00:00+08:00"
    assert not parsed.requires_confirmation


def test_past_missing_year_requires_confirmation():
    parsed = parse_relative_datetime("1月2日上午9点", datetime(2026, 8, 3, 9, 0, tzinfo=CHINA_TZ))
    assert parsed.value and parsed.value.year == 2027
    assert parsed.requires_confirmation


def test_relative_weekday_range_and_month_end_are_explicit():
    reference = datetime(2026, 8, 3, 9, 0, tzinfo=CHINA_TZ)  # Monday
    friday = parse_relative_datetime("下周五下午5点", reference)
    assert friday.value and friday.value.isoformat() == "2026-08-14T17:00:00+08:00"
    assert not friday.requires_confirmation

    within = parse_relative_datetime("三天内", reference)
    assert within.value and within.value.date().isoformat() == "2026-08-06"
    assert within.requires_confirmation

    month_end = parse_relative_datetime("月底", reference)
    assert month_end.value and month_end.value.isoformat() == "2026-08-31T23:59:00+08:00"
    assert month_end.requires_confirmation


def test_rule_extractor_splits_multiple_tasks_and_keeps_submission_fields():
    text = (
        "1. 下周五下午5点前提交课程报告给任课老师，提交方式：教学平台，"
        "文件命名为学号-姓名，材料：报告、附件\n"
        "2. 月底前提交纸质申请到辅导员办公室，备注：务必本人签名"
    )
    drafts = NotificationService().fallback(text, reference_time=datetime(2026, 8, 3, 9, 0, tzinfo=CHINA_TZ))
    assert len(drafts) == 2
    assert drafts[0].submission_target
    assert drafts[0].submission_method == "教学平台"
    assert drafts[0].file_naming == "学号-姓名"
    assert drafts[0].materials == ["报告", "附件"]
    assert drafts[1].needs_confirmation is True


def test_notification_model_path_uses_a_mock_and_never_calls_external_api(monkeypatch):
    expected = NotificationDraft(title="模型提取任务", deadline=None, needs_confirmation=True)
    monkeypatch.setattr("app.services.notification_service.get_settings", lambda: type("S", (), {"deepseek_api_key": "mock-key"})())
    monkeypatch.setattr(NotificationService, "with_model", lambda self, text, source_url="", reference_time=None: [expected])
    drafts, mode, warning = NotificationService().extract("测试通知")
    assert mode == "llm"
    assert warning == ""
    assert drafts[0].title == "模型提取任务"


def test_notification_model_failure_degrades_with_error_id(monkeypatch):
    monkeypatch.setattr("app.services.notification_service.get_settings", lambda: type("S", (), {"deepseek_api_key": "mock-key"})())
    monkeypatch.setattr(NotificationService, "with_model", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("mock timeout")))
    drafts, mode, warning = NotificationService().extract("明天提交报告")
    assert mode == "rules"
    assert drafts
    assert "错误编号" in warning


def test_notification_preview_then_confirm(client: TestClient, register_user):
    register_user("notice")
    text = "课程报告提交通知\n截止时间：2099年9月3日下午5点\n材料：报告、附件\n提交方式：教学平台"
    preview = client.post("/api/notifications/parse", data={"text": text})
    assert preview.status_code == 200
    body = preview.json()
    assert body["extraction_mode"] == "rules"
    assert body["drafts"][0]["title"]
    before = len(client.get("/api/tasks").json())
    confirmed = client.post("/api/notifications/confirm", json={"drafts": body["drafts"], "confirmed": True})
    assert confirmed.status_code == 201
    assert len(client.get("/api/tasks").json()) == before + 1


def test_txt_upload_and_image_ocr_rejection(client: TestClient, register_user):
    register_user("upload")
    txt = client.post(
        "/api/notifications/parse",
        files={"file": ("notice.txt", "作业通知\n截止时间：2099年10月1日", "text/plain")},
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
