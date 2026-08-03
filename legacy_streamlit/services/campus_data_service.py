"""Official-source refresh with caching, retries, provenance, and failure isolation."""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.database import Database
from core.models import CanteenInfo, CampusLocation, FreshnessResult
from core.time_service import now_china, parse_datetime_value
from services.location_service import LocationService, normalize_campus


SOURCE_LEVEL_LABELS = {
    1: "学校及校区官网",
    2: "学校职能部门官网",
    3: "学校官方微信公众号",
    4: "学校公开后勤或服务公告",
    5: "管理员实地核验",
    6: "审核通过的学生提交",
    7: "普通公开网页",
    8: "未核验历史资料",
}


def source_rank(source: dict[str, Any]) -> tuple[int, int]:
    """Lower tuple values are preferred."""

    return (
        int(source.get("source_level") or 8),
        0 if source.get("is_official") else 1,
    )


class CampusDataService:
    def __init__(
        self,
        db_path: str | Path | None = None,
        source_config: str | Path = "data/official_sources.json",
        timeout: tuple[int, int] = (4, 12),
        cache_hours: int = 6,
    ):
        self.database = Database(db_path)
        self.location_service = LocationService(db_path, auto_seed=False)
        self.source_config = Path(source_config)
        self.timeout = timeout
        self.cache_hours = cache_hours

    def load_source_config(self) -> list[dict[str, Any]]:
        if not self.source_config.exists():
            return []
        payload = json.loads(self.source_config.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("official_sources.json 必须是数组")
        return payload

    @staticmethod
    def build_session() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(
            {
                "User-Agent": "GDUF-Super-Senior-Agent/2.0 (+data-refresh; no-personal-data)",
                "Accept": "text/html,application/xhtml+xml",
            }
        )
        return session

    @staticmethod
    def _extract_page(response: requests.Response) -> tuple[str, str, str | None]:
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:20_000]
        published = None
        patterns = (
            r"(?<!\d)(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})日?",
            r"发布时间[:：]?\s*(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                published = f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
                break
        return title, text, published

    def _is_cached(self, existing: dict[str, Any] | None, reference_time=None) -> bool:
        if not existing or not existing.get("fetched_at"):
            return False
        fetched = parse_datetime_value(existing["fetched_at"])
        return bool(fetched and now_china(reference_time) - fetched < timedelta(hours=self.cache_hours))

    def refresh_official_sources(
        self,
        campus: str | None = None,
        force: bool = False,
        session: requests.Session | None = None,
        reference_time=None,
    ) -> list[dict[str, Any]]:
        normalized_campus = normalize_campus(campus)
        sources = self.load_source_config()
        if normalized_campus:
            sources = [item for item in sources if item.get("campus") == normalized_campus]
        client = session or self.build_session()
        fetched_at = now_china(reference_time).isoformat()
        results = []
        for source in sources:
            url = source["url"]
            existing = self.database.query_one(
                "SELECT * FROM location_sources WHERE url = ?", (url,)
            )
            if not force and self._is_cached(existing, reference_time):
                results.append(
                    {
                        "url": url,
                        "campus": source["campus"],
                        "status": "cached",
                        "changed": False,
                        "fetched_at": existing["fetched_at"],
                    }
                )
                continue
            try:
                response = client.get(url, timeout=self.timeout)
                response.raise_for_status()
                title, text, published = self._extract_page(response)
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                changed = not existing or existing.get("content_hash") != content_hash
                values = (
                    source["campus"],
                    title or source.get("title", url),
                    url,
                    source.get("publisher", "广东金融学院"),
                    published,
                    fetched_at,
                    int(bool(source.get("is_official", True))),
                    int(source.get("source_level", 1)),
                    "current_source" if source.get("is_official", True) else "unverified",
                    content_hash,
                    text,
                    None,
                    fetched_at,
                )
                self.database.execute(
                    """
                    INSERT INTO location_sources(
                        campus,title,url,publisher,published_at,fetched_at,is_official,
                        source_level,source_status,content_hash,cached_text,last_error,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(url) DO UPDATE SET
                        campus=excluded.campus,title=excluded.title,publisher=excluded.publisher,
                        published_at=excluded.published_at,fetched_at=excluded.fetched_at,
                        is_official=excluded.is_official,source_level=excluded.source_level,
                        source_status=excluded.source_status,content_hash=excluded.content_hash,
                        cached_text=excluded.cached_text,last_error=NULL,updated_at=excluded.updated_at
                    """,
                    values,
                )
                status = "updated" if changed else "unchanged"
                message = "内容发生变化，等待管理员核验。" if changed else "内容未变化。"
                results.append(
                    {
                        "url": url,
                        "campus": source["campus"],
                        "status": status,
                        "changed": changed,
                        "published_at": published,
                        "fetched_at": fetched_at,
                    }
                )
            except Exception as exc:  # each source is isolated by design
                message = str(exc)[:500]
                if existing:
                    self.database.execute(
                        "UPDATE location_sources SET last_error = ?, updated_at = ? WHERE url = ?",
                        (message, fetched_at, url),
                    )
                status = "failed_preserved" if existing else "failed"
                results.append(
                    {
                        "url": url,
                        "campus": source["campus"],
                        "status": status,
                        "changed": False,
                        "error": message,
                        "preserved_previous": bool(existing),
                    }
                )
            self.database.execute(
                "INSERT INTO data_refresh_logs(campus,source_url,status,changed,message,fetched_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    source["campus"],
                    url,
                    results[-1]["status"],
                    int(bool(results[-1].get("changed"))),
                    message,
                    fetched_at,
                ),
            )
        return results

    def list_sources(self, campus: str | None = None) -> list[dict[str, Any]]:
        normalized = normalize_campus(campus)
        if normalized:
            rows = self.database.query(
                "SELECT * FROM location_sources WHERE campus = ?", (normalized,)
            )
        else:
            rows = self.database.query("SELECT * FROM location_sources")
        return sorted(rows, key=source_rank)

    def calculate_freshness(
        self,
        item: CampusLocation | CanteenInfo,
        reference_time=None,
        data_kind: str | None = None,
    ) -> FreshnessResult:
        return self.location_service.calculate_freshness(item, reference_time, data_kind)


def refresh_official_sources(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return CampusDataService().refresh_official_sources(*args, **kwargs)


def calculate_freshness(
    item: CampusLocation | CanteenInfo,
    reference_time=None,
    data_kind: str | None = None,
) -> dict[str, Any]:
    return asdict(CampusDataService().calculate_freshness(item, reference_time, data_kind))
