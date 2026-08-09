import json

from services.campus_data_service import CampusDataService, source_rank


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        return None


class SuccessSession:
    def get(self, url, timeout):
        assert timeout == (4, 12)
        return FakeResponse("<html><title>校区官网</title><body>发布时间：2026-08-01 测试内容</body></html>")


class FailingSession:
    def get(self, url, timeout):
        raise TimeoutError("模拟超时")


def test_official_source_priority():
    official = {"source_level": 1, "is_official": True}
    historical = {"source_level": 8, "is_official": False}
    assert source_rank(official) < source_rank(historical)


def test_refresh_tracks_source_time_hash_and_preserves_cache_on_failure(tmp_path):
    config = tmp_path / "official_sources.json"
    config.write_text(
        json.dumps(
            [
                {
                    "campus": "广州校本部",
                    "title": "官网",
                    "url": "https://example.invalid/gduf",
                    "publisher": "广东金融学院",
                    "is_official": True,
                    "source_level": 1,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = CampusDataService(tmp_path / "data.db", config)
    success = service.refresh_official_sources(
        campus="广州校本部", force=True, session=SuccessSession()
    )
    assert success[0]["status"] == "updated"
    row = service.list_sources("广州校本部")[0]
    original_hash = row["content_hash"]
    assert row["published_at"] == "2026-08-01"
    assert row["fetched_at"]

    failed = service.refresh_official_sources(
        campus="广州校本部", force=True, session=FailingSession()
    )
    assert failed[0]["status"] == "failed_preserved"
    assert failed[0]["preserved_previous"] is True
    preserved = service.list_sources("广州校本部")[0]
    assert preserved["content_hash"] == original_hash
    assert "模拟超时" in preserved["last_error"]
