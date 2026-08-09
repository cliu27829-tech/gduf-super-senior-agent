from __future__ import annotations

import json
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse


app = FastAPI()


def _intent(message: str) -> str:
    patterns = (
        ("reminder_management", ("提醒我", "设提醒")),
        ("note_management", ("记一下", "记下来", "便签")),
        ("notification_to_tasks", ("通知", "提交课程报告", "生成任务")),
        ("task_management", ("我的任务", "待办", "已完成", "逾期")),
        ("campus_process", ("校园卡", "挂失", "补办", "报修")),
        ("food_search", ("有什么吃", "面", "肠粉", "早餐", "菜品")),
        ("canteen_search", ("饭堂", "食堂", "餐厅")),
        ("campus_location_search", ("在哪里", "在哪", "快递", "医务室", "图书馆")),
        ("learning_guidance", ("高数", "学习", "考试周")),
        ("campus_life_guidance", ("社团", "新生", "入学")),
    )
    for intent, terms in patterns:
        if any(term in message for term in terms):
            return intent
    return "general_chat"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat/completions")
async def chat_completions(request: Request):
    payload = await request.json()
    messages = payload.get("messages", [])
    system = messages[0].get("content", "") if messages else ""
    user_message = next((item.get("content", "") for item in reversed(messages) if item.get("role") == "user"), "")

    if "意图规划器" in system:
        intent = _intent(user_message)
        tool_plan = [intent] if intent in {
            "campus_location_search", "canteen_search", "food_search", "campus_process"
        } else []
        content = json.dumps({"intent": intent, "confidence": 0.99, "query": user_message, "tool_plan": tool_plan})
    elif "我刚才说我叫什么" in user_message and any("我叫小明" in item.get("content", "") for item in messages):
        content = "你刚才说你叫小明，我记得。"
    elif "我叫小明" in user_message:
        content = "好的，小明。我会在这段对话中记住你的名字。"
    elif "高数" in user_message:
        content = "先用几道基础题定位是概念、计算还是题型识别的问题，再每天复盘错题并逐步增加练习难度。"
    elif "当日菜单" in system:
        content = "目前没有可靠的当日菜单数据，以下是最近核验的历史档口资料，不保证今日供应。"
    else:
        content = "你好，我是广金大师兄。我可以陪你多轮讨论学习问题，并在校园事实问题上使用后端工具查询。"

    response = {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.get("model", "deepseek-v4-flash"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    if not payload.get("stream"):
        return response

    async def events():
        stream_id = response["id"]
        # Include a reasoning-only chunk to verify clients do not expose it.
        reasoning = {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": response["created"],
            "model": response["model"],
            "choices": [{"index": 0, "delta": {"reasoning_content": "internal-test-reasoning"}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(reasoning, ensure_ascii=False)}\n\n"
        midpoint = max(1, len(content) // 2)
        for part in (content[:midpoint], content[midpoint:]):
            if not part:
                continue
            chunk = {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "created": response["created"],
                "model": response["model"],
                "choices": [{"index": 0, "delta": {"content": part}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        finished = {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": response["created"],
            "model": response["model"],
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(finished, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
