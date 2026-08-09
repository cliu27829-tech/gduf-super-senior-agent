from __future__ import annotations

import json

from app.agents.contracts import IntentDecision
from app.core.llm_client import LLMClient


INTENTS = {
    "general_chat", "learning_guidance", "campus_life_guidance", "campus_location_search",
    "nearby_location_search", "campus_navigation", "canteen_search", "food_search",
    "notification_to_tasks", "task_management", "campus_process", "document_analysis",
    "knowledge_search", "knowledge_import", "calendar_export", "data_feedback", "out_of_scope",
    "campus_fact_search", "reminder_management", "note_management", "daily_summary",
}
FACT_INTENTS = {
    "campus_location_search", "nearby_location_search", "campus_navigation", "canteen_search",
    "food_search", "campus_process", "document_analysis", "knowledge_search", "knowledge_import", "data_feedback",
    "campus_fact_search",
}
DEFAULT_TOOL_PLANS = {
    "campus_location_search": ["search_campus_locations"],
    "nearby_location_search": ["find_nearby_locations"],
    "campus_navigation": ["search_campus_locations", "calculate_walking_route"],
    "canteen_search": ["list_canteens"],
    "food_search": ["search_food"],
    "campus_process": ["search_campus_processes"],
    "knowledge_search": ["search_campus_knowledge"],
    "campus_fact_search": ["search_campus_facts", "list_campus_colleges"],
    "notification_to_tasks": ["extract_tasks_from_notification", "validate_extracted_tasks"],
    "reminder_management": ["preview_reminder"],
    "note_management": ["preview_note"],
    "daily_summary": ["get_daily_summary"],
}


class IntentClassifier:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    @staticmethod
    def _heuristic(message: str) -> IntentDecision:
        patterns = (
            ("daily_summary", ("我今天还有什么", "我明天还有什么", "近期安排")),
            ("reminder_management", ("提醒我", "设提醒")),
            ("note_management", ("记一下", "记下来", "便签")),
            (
                "campus_fact_search",
                ("多少个学院", "几个学院", "学院数量", "哪些学院", "学院名单", "2+2", "产业学院", "多少专业", "多少学生"),
            ),
            ("notification_to_tasks", ("通知", "生成任务", "提取任务")),
            ("campus_navigation", ("怎么走", "路线", "导航")),
            ("food_search", ("有什么吃", "吃什么", "菜品", "档口")),
            ("canteen_search", ("饭堂", "食堂", "北饭", "南饭", "西饭")),
            ("campus_location_search", ("在哪里", "在哪", "教学楼", "图书馆", "快递", "体育馆", "宿舍")),
            ("campus_process", ("补办", "挂失", "报修", "借用", "办理")),
            ("task_management", ("我的任务", "待办", "逾期")),
            ("learning_guidance", ("高数", "学习", "复习", "考试")),
        )
        for intent, terms in patterns:
            if any(term in message for term in terms):
                return IntentDecision(intent=intent, confidence=0.75, query=message, tool_plan=DEFAULT_TOOL_PLANS.get(intent, []))
        return IntentDecision(intent="general_chat", confidence=0.6, query=message, tool_plan=[])

    async def classify(self, message: str) -> IntentDecision:
        prompt = (
            "你是校园 Agent 的意图规划器，只输出 json 对象：intent/confidence/query/tool_plan。"
            f"intent 必须属于：{sorted(INTENTS)}。"
            "地点、路线、附近、饭堂、餐品、校内制度、办事流程和资料纠错属于校园事实，必须选择对应数据库或地图工具；"
            "查询用户资料或校园知识使用 knowledge_search；上传文件、粘贴正文或导入文章链接使用 knowledge_import。"
            "学院数量、校区基本情况和别名使用 campus_fact_search；提醒使用 reminder_management；便签使用 note_management；"
            "‘我今天/明天/近期还有什么’使用 daily_summary。学习建议、校园生活建议和寒暄可以不调用校园事实工具。"
            "创建、修改、删除、批量保存等副作用不得直接执行。"
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
                decision.tool_plan = DEFAULT_TOOL_PLANS.get(decision.intent, [])
            heuristic = self._heuristic(message)
            if decision.intent in {"general_chat", "campus_life_guidance", "out_of_scope"} and heuristic.intent != "general_chat":
                return heuristic
            return decision
        except (json.JSONDecodeError, ValueError) as exc:
            del exc
            return self._heuristic(message)
