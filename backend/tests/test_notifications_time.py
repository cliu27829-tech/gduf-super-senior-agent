from datetime import datetime

from fastapi.testclient import TestClient

from app.services.time_service import CHINA_TZ, parse_relative_datetime


def test_month_is_not_parsed_as_hour():
    parsed = parse_relative_datetime("9月3日下午5点", datetime(2026, 8, 3, 9, 0, tzinfo=CHINA_TZ))
    assert parsed.value is not None
    assert parsed.value.isoformat() == "2026-09-03T17:00:00+08:00"
    assert not parsed.requires_confirmation


def test_past_missing_year_requires_confirmation():
    parsed = parse_relative_datetime("1月2日上午9点", datetime(2026, 8, 3, 9, 0, tzinfo=CHINA_TZ))
    assert parsed.value and parsed.value.year == 2027
    assert parsed.requires_confirmation


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

