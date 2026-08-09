from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Location


NAVIGATION_TERMS = ("怎么走", "怎么去", "带我去", "导航", "路线", "从我这里", "当前位置")


def resolve_navigation_destination(db: Session, campus_id: str | None, message: str) -> Location | None:
    if not campus_id or not any(term in message for term in NAVIGATION_TERMS):
        return None
    explicit_origin = re.search(r"从(.{1,30}?)(?:到|去)", message)
    if explicit_origin and not any(term in explicit_origin.group(1) for term in ("我", "这里", "当前位置")):
        return None
    normalized = re.sub(r"[\s，。？?、！!]", "", message).lower()
    rows = list(
        db.scalars(
            select(Location).where(
                Location.campus_id == campus_id,
                Location.is_active.is_(True),
                Location.data_status != "demo_fixture",
            )
        )
    )
    ranked: list[tuple[int, Location]] = []
    for row in rows:
        score = max(
            (
                len(alias)
                for alias in [row.name, *row.aliases]
                if alias and re.sub(r"\s", "", alias).lower() in normalized
            ),
            default=0,
        )
        if score:
            ranked.append((score, row))
    return max(ranked, key=lambda item: item[0])[1] if ranked else None
