from __future__ import annotations

from app.models.entities import User


def preferred_address(user: User) -> str:
    name = user.preferred_name.strip() or user.nickname.strip() or user.username
    style = user.address_style
    if style == "名字":
        return name
    if style in {"师弟", "师妹", "兄弟", "同学"}:
        return f"{name}{style}" if user.preferred_name.strip() else style
    return "同学"


PERSONA_RULES = (
    "语气像可靠、耐心、不过分卖萌的同校大师兄；先给结论，再给可执行步骤。"
    "严肃、安全、隐私或不确定事项减少口语化。不得展示内部推理过程。"
)
