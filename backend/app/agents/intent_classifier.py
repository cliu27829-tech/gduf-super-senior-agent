from __future__ import annotations

import json

from app.agents.contracts import IntentDecision
from app.core.llm_client import LLMClient, LLMProviderError


INTENTS = {
    "general_chat", "learning_guidance", "campus_life_guidance", "campus_location_search",
    "nearby_location_search", "campus_navigation", "canteen_search", "food_search",
    "notification_to_tasks", "task_management", "campus_process", "document_analysis",
    "knowledge_search", "knowledge_import", "calendar_export", "data_feedback", "out_of_scope",
}
FACT_INTENTS = {
    "campus_location_search", "nearby_location_search", "campus_navigation", "canteen_search",
    "food_search", "campus_process", "document_analysis", "knowledge_search", "knowledge_import", "data_feedback",
}


class IntentClassifier:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def classify(self, message: str) -> IntentDecision:
        prompt = (
            "你是校园 Agent 的意图规划器，只输出 json 对象：intent/confidence/query/tool_plan。"
            f"intent 必须属于：{sorted(INTENTS)}。"
            "地点、路线、附近、饭堂、餐品、校内制度、办事流程和资料纠错属于校园事实，必须选择对应数据库或地图工具；"
            "查询用户资料或校园知识使用 knowledge_search；上传文件、粘贴正文或导入文章链接使用 knowledge_import。"
            "学习建议、校园生活建议和寒暄可以不调用校园事实工具。创建、修改、删除、批量保存等副作用不得直接执行。"
        )
        content = await self.llm.chat_completion(
            [{"role": "system", "content": prompt}, {"role": "user", "content": message}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        try:
            decision = IntentDecision.model_validate(json.loads(content))
            if decision.intent not in INTENTS:
                raise ValueError("unsupported intent")
            if decision.intent in FACT_INTENTS and not decision.tool_plan:
                raise ValueError("campus facts require a tool plan")
            return decision
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMProviderError() from exc
