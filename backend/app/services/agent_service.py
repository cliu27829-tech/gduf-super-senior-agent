from __future__ import annotations

import json
import re

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.entities import CampusProcess, Canteen, Conversation, Location, Message, Source, Task, User
from app.schemas.agent import AgentChatResponse, ToolResult
from app.services.notification_service import NotificationService
from app.services.time_service import now_china


INTENTS = {
    "campus_location_search", "canteen_search", "food_search", "campus_navigation",
    "notification_to_tasks", "campus_process", "task_management", "learning_guidance",
    "campus_life_guidance", "general_chat", "out_of_scope",
}


class IntentPlan(BaseModel):
    intent: str
    confidence: float = Field(ge=0, le=1)
    query: str = ""
    tool_plan: list[str] = Field(default_factory=list)


class AgentService:
    FALLBACK_PATTERNS = {
        "notification_to_tasks": r"截止|提交材料|班群通知|生成任务|通知转",
        "task_management": r"我的任务|待办|已完成|逾期|任务中心",
        "campus_process": r"校园卡|挂失|补办|报修|请假|办事|证明",
        "campus_navigation": r"怎么走|导航|路线|从.+到",
        "canteen_search": r"饭堂|食堂|餐厅",
        "food_search": r"想吃|早餐|午餐|晚餐|面|粉|奶茶|咖啡",
        "campus_location_search": r"在哪|哪里|位置|教学楼|宿舍|快递|医务|超市|图书馆",
        "learning_guidance": r"复习|学习|考试|课程|论文|四六级",
        "campus_life_guidance": r"社团|宿舍生活|适应大学|人际|校园生活",
    }

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _llm_plan(self, message: str) -> IntentPlan:
        client = OpenAI(api_key=self.settings.deepseek_api_key, base_url=self.settings.deepseek_base_url)
        prompt = (
            "你是校园助手意图分类器。只输出 JSON，字段 intent/confidence/query/tool_plan。"
            f"intent 必须属于：{sorted(INTENTS)}。涉及校园事实必须安排数据库工具，不能自由编造。"
        )
        response = client.chat.completions.create(
            model=self.settings.deepseek_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": message}],
        )
        plan = IntentPlan.model_validate(json.loads(response.choices[0].message.content or "{}"))
        if plan.intent not in INTENTS:
            raise ValidationError.from_exception_data("IntentPlan", [])
        return plan

    def classify(self, message: str) -> tuple[IntentPlan, bool]:
        if self.settings.deepseek_api_key:
            try:
                return self._llm_plan(message), False
            except Exception:
                pass
        for intent, pattern in self.FALLBACK_PATTERNS.items():
            if re.search(pattern, message, re.I):
                return IntentPlan(intent=intent, confidence=0.65, query=message, tool_plan=[intent]), True
        return IntentPlan(intent="general_chat", confidence=0.55, query=message, tool_plan=[]), True

    @staticmethod
    def _source(source: Source) -> dict:
        return {
            "id": source.id, "title": source.title, "url": source.url, "publisher": source.publisher,
            "source_type": source.source_type, "published_at": source.published_at.isoformat() if source.published_at else None,
            "verified_at": source.verified_at.isoformat() if source.verified_at else None,
            "confidence": source.confidence, "is_official": source.is_official,
        }

    def _locations(self, message: str, campus_id: str | None) -> tuple[str, list[ToolResult], list[dict]]:
        query = select(Location).options(selectinload(Location.sources)).where(Location.is_active.is_(True))
        if campus_id:
            query = query.where(Location.campus_id == campus_id)
        terms = [term for term in re.split(r"[\s，。？?、]+", message) if len(term) >= 2]
        if terms:
            query = query.where(or_(*[Location.name.contains(term) for term in terms], *[Location.description.contains(term) for term in terms]))
        rows = list(self.db.scalars(query.limit(20)).unique())
        if not rows:
            return "没有找到匹配且已启用的地点；数据可能仍待管理员补充。", [ToolResult(tool="location_search", title="地点搜索", data=[])], []
        data = [{"id": row.id, "name": row.name, "category": row.category, "area": row.area or row.address, "map_x": row.map_x, "map_y": row.map_y, "verification_status": row.verification_status, "updated_at": row.updated_at.isoformat()} for row in rows]
        sources = [self._source(source) for row in rows for source in row.sources]
        return f"找到 {len(rows)} 个匹配地点。请查看地点卡片中的来源、核验状态和更新时间。", [ToolResult(tool="location_search", title="地点结果", data=data)], sources

    def _canteens(self, campus_id: str | None, food: bool = False) -> tuple[str, list[ToolResult], list[dict]]:
        query = select(Canteen).options(selectinload(Canteen.stalls), selectinload(Canteen.source)).where(Canteen.is_active.is_(True))
        if campus_id:
            query = query.where(Canteen.campus_id == campus_id)
        rows = list(self.db.scalars(query).unique())
        data = []
        sources = []
        for row in rows:
            verified_stalls = [stall for stall in row.stalls if stall.verified_at and stall.verification_status == "verified" and stall.is_active]
            data.append({
                "id": row.id, "name": row.name, "floors": row.floors, "opening_hours": row.opening_hours,
                "verification_status": row.verification_status,
                "stalls": [{"name": stall.name, "food_type": stall.food_type, "common_items": stall.common_items} for stall in verified_stalls],
                "today_menu_available": False,
            })
            if row.source:
                sources.append(self._source(row.source))
        if food and not any(item["stalls"] for item in data):
            answer = "目前没有已核验档口可支持该餐食查询，我不会依据占位或历史资料编造今日供应。"
        elif rows:
            answer = "以下为最近记录的饭堂信息；系统没有可靠的实时菜单，常见餐品不代表今日供应。"
        else:
            answer = "该校区暂无已记录饭堂，等待管理员核验。"
        return answer, [ToolResult(tool="food_search" if food else "canteen_search", title="饭堂与档口", data=data)], sources

    def chat(self, user: User, message: str, conversation_id: str | None, campus_id: str | None) -> AgentChatResponse:
        plan, degraded = self.classify(message)
        conversation = self.db.get(Conversation, conversation_id) if conversation_id else None
        if conversation and conversation.user_id != user.id:
            conversation = None
        if not conversation:
            conversation = Conversation(user_id=user.id, campus_id=campus_id or user.campus_id, title=message[:60])
            self.db.add(conversation)
            self.db.flush()
        self.db.add(Message(conversation_id=conversation.id, role="user", content=message, intent=plan.intent))
        tool_results: list[ToolResult] = []
        sources: list[dict] = []
        requires_confirmation = False
        if plan.intent in {"campus_location_search", "campus_navigation"}:
            answer, tool_results, sources = self._locations(message, campus_id or conversation.campus_id)
        elif plan.intent in {"canteen_search", "food_search"}:
            answer, tool_results, sources = self._canteens(campus_id or conversation.campus_id, plan.intent == "food_search")
        elif plan.intent == "notification_to_tasks":
            drafts, mode, warning = NotificationService().extract(message)
            data = [draft.model_dump(mode="json") for draft in drafts]
            tool_results = [ToolResult(tool="notification_parser", title="通知任务预览", data=data)]
            answer = "已生成任务预览，请核对并明确确认后保存。" + (f" {warning}" if warning else "")
            requires_confirmation = True
            degraded = degraded or mode == "rules"
        elif plan.intent == "task_management":
            tasks = list(self.db.scalars(select(Task).where(Task.user_id == user.id).order_by(Task.deadline)))
            data = [{"id": task.id, "title": task.title, "deadline": task.deadline.isoformat() if task.deadline else None, "status": task.status} for task in tasks]
            tool_results = [ToolResult(tool="task_list", title="我的任务", data=data)]
            answer = f"你当前共有 {len(tasks)} 条任务。"
        elif plan.intent == "campus_process":
            processes = list(self.db.scalars(select(CampusProcess).where(CampusProcess.is_active.is_(True), CampusProcess.verification_status == "verified")))
            matched = [item for item in processes if item.title in message or any(word in item.title for word in re.split(r"\s+", message))]
            data = [{"id": item.id, "title": item.title, "steps": item.steps, "materials": item.materials} for item in matched]
            tool_results = [ToolResult(tool="process_search", title="校园办事流程", data=data)]
            answer = "已返回经过核验的办事流程。" if matched else "目前没有匹配且已核验的办事流程；我不会补写地点、费用或时限。"
        elif plan.intent == "learning_guidance":
            answer = "可以先把目标拆成一周可执行计划：明确考试或作业节点、每天安排一个高专注时段、结束后做十分钟复盘。若提供课程和截止日期，我可以进一步整理任务。"
        elif plan.intent == "campus_life_guidance":
            answer = "遇到校园生活问题，可以先说明所在校区和具体场景。我会把建议与未经核验的校园事实分开；地点、电话和制度只使用数据库或官方来源。"
        else:
            answer = "你好，我是广金大师兄。你可以让我查校园、看饭堂、处理通知、管理任务，或咨询学习与校园生活。"
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            intent=plan.intent,
            tool_results=[item.model_dump(mode="json") for item in tool_results],
            sources=sources,
        )
        self.db.add(assistant_message)
        self.db.commit()
        self.db.refresh(assistant_message)
        return AgentChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            intent=plan.intent,
            answer=answer,
            tool_results=tool_results,
            sources=sources,
            requires_confirmation=requires_confirmation,
            degraded=degraded,
            current_time=now_china(),
        )

