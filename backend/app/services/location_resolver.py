from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Location, User


def resolve_location(
    db: Session,
    user: User,
    *,
    location_id: str | None = None,
    location_text: str = "",
) -> Location | None:
    if location_id:
        row = db.scalar(
            select(Location).where(
                Location.id == location_id,
                Location.is_active.is_(True),
                Location.data_status != "demo_fixture",
            )
        )
        if not row or (user.campus_id and row.campus_id != user.campus_id):
            raise HTTPException(status_code=404, detail="地点不存在")
        return row
    needle = re.sub(r"[\s，。？?、！!]", "", location_text).lower()
    if not needle or not user.campus_id:
        return None
    rows = list(
        db.scalars(
            select(Location).where(
                Location.campus_id == user.campus_id,
                Location.is_active.is_(True),
                Location.data_status != "demo_fixture",
            )
        )
    )
    matches: list[tuple[int, Location]] = []
    for row in rows:
        names = [row.name, *row.aliases]
        score = max((len(name) for name in names if name and re.sub(r"\s", "", name).lower() in needle), default=0)
        if score:
            matches.append((score, row))
    return max(matches, key=lambda item: item[0])[1] if matches else None
