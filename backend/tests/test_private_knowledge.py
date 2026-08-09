from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.knowledge_service import KnowledgeImportError, chunk_text, extract_document, tokenize, validate_public_url


def _login(client, user: dict) -> None:
    client.cookies.clear()
    response = client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})
    assert response.status_code == 200, response.text


def test_private_import_dedup_search_isolation_and_admin_review(client, register_user, login_admin, campus_id):
    owner = register_user("knowledge-owner")
    payload = {
        "title": "奖学金申请说明",
        "content": "奖学金申请需要先准备成绩单和个人申请材料。评审时间以学校正式通知为准。",
        "campus_id": campus_id,
        "publisher": "个人整理",
    }
    imported = client.post("/api/knowledge/import/text", json=payload)
    assert imported.status_code == 201, imported.text
    assert imported.json()["imported"] == 1
    source_id = imported.json()["document_ids"][0]
    detail = client.get(f"/api/knowledge/sources/{source_id}")
    assert detail.status_code == 200
    assert detail.json()["extracted_metadata"]["publisher"] == "个人整理"

    duplicate = client.post("/api/knowledge/import/text", json=payload)
    assert duplicate.status_code == 201
    assert duplicate.json()["duplicates"] == 1

    search = client.get("/api/knowledge/search", params={"q": "奖学金申请", "campus_id": campus_id})
    assert search.status_code == 200
    assert search.json()[0]["document_id"] == source_id
    assert search.json()[0]["visibility"] == "private"

    agent_search = client.post("/api/agent/chat", json={
        "message": "请在知识库里查奖学金申请",
        "conversation_id": None,
        "campus": "guangzhou",
    })
    assert agent_search.status_code == 200, agent_search.text
    assert agent_search.json()["intent"] == "knowledge_search"
    assert agent_search.json()["tool_results"][0]["tool"] == "knowledge_search"

    agent_import = client.post("/api/agent/chat", json={
        "message": "帮我导入资料",
        "conversation_id": None,
        "campus": "guangzhou",
    })
    assert agent_import.status_code == 200, agent_import.text
    assert agent_import.json()["intent"] == "knowledge_import"
    assert agent_import.json()["requires_confirmation"] is True

    outsider = register_user("knowledge-outsider")
    assert client.get(f"/api/knowledge/sources/{source_id}").status_code == 404
    assert all(item["document_id"] != source_id for item in client.get(
        "/api/knowledge/search", params={"q": "奖学金申请", "campus_id": campus_id}
    ).json())

    _login(client, owner)
    submitted = client.post(f"/api/knowledge/sources/{source_id}/submit-review?confirmed=true")
    assert submitted.status_code == 200
    assert submitted.json()["review_status"] == "pending"

    login_admin()
    reviewed = client.patch(f"/api/knowledge/admin/sources/{source_id}/review", json={
        "status": "approved",
        "verification_method": "source_comparison",
        "verified_fields": ["title", "content"],
        "evidence": "Matched the approved test source fixture",
        "note": "Test review",
        "confirmed": True,
    })
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["visibility"] == "public"

    _login(client, outsider)
    shared = client.get("/api/knowledge/search", params={"q": "奖学金申请", "campus_id": campus_id})
    assert any(item["document_id"] == source_id for item in shared.json())

    _login(client, owner)
    assert client.delete(f"/api/knowledge/sources/{source_id}").status_code == 422
    assert client.delete(f"/api/knowledge/sources/{source_id}?confirmed=true").status_code == 204


def test_file_import_parser_reindex_and_failed_file(client, register_user, campus_id):
    register_user("knowledge-file")
    response = client.post(
        "/api/knowledge/import/files",
        data={"campus_id": campus_id},
        files=[("files", ("guide.md", "# 新生指南\n\n校园卡补办请先核对官方流程。".encode(), "text/markdown"))],
    )
    assert response.status_code == 201, response.text
    assert response.json()["imported"] == 1

    failed = client.post(
        "/api/knowledge/import/files",
        files=[("files", ("archive.exe", b"not-a-document", "application/octet-stream"))],
    )
    assert failed.status_code == 201
    assert failed.json()["failed"] == 1

    reindexed = client.post("/api/knowledge/reindex")
    assert reindexed.status_code == 200
    assert reindexed.json()["indexed_documents"] >= 1


def test_extractors_tokenization_and_ssrf_guard():
    assert "校园卡" in extract_document("note.txt", "校园卡办理".encode())
    assert "去阅读" not in extract_document("note.md", "# 指南\n去阅读\n有效内容\n有效内容".encode())
    assert len(chunk_text("第一段。\n\n" + "第二段。" * 300, max_characters=100)) > 1
    assert "奖学" in tokenize("奖学金申请")
    with pytest.raises(KnowledgeImportError):
        validate_public_url("http://127.0.0.1/internal")


def test_pdf_text_layer_is_extracted_without_ocr():
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    resources = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 30 200 Td (Campus PDF guide) Tj ET")
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = writer._add_object(stream)
    payload = BytesIO()
    writer.write(payload)
    assert "Campus PDF guide" in extract_document("guide.pdf", payload.getvalue())
