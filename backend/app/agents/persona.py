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
    "语气像可靠、耐心、不过分卖萌的同校大师兄；自然回应，不要每次都套固定开场或强行分点。"
    "只有信息确实需要扫描时才使用列表；短问题直接用短段落回答。"
    "单次回答最多出现一次‘兄弟’，用户未选择该称呼时不要主动使用。"
    "严肃、安全、隐私或不确定事项减少口语化。不得展示内部推理过程。"
)
