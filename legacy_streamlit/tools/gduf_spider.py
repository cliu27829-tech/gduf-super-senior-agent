"""兼容入口：使用三校官方源刷新服务，不再写入固定清远文件。"""

from __future__ import annotations

from typing import Any

from services.campus_data_service import CampusDataService


def crawl_gduf_campus(campus: str | None = None, force: bool = False) -> list[dict[str, Any]]:
    return CampusDataService().refresh_official_sources(campus=campus, force=force)


def update_knowledge_base(data_dir: str = "data", campus: str | None = None):
    del data_dir  # Kept in the signature for old callers; refreshes now live in SQLite.
    return crawl_gduf_campus(campus=campus, force=True)


if __name__ == "__main__":
    for result in update_knowledge_base():
        print(result)
