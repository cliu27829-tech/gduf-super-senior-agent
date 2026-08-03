from __future__ import annotations

import json
import logging
import re
from uuid import uuid4

from fastapi import HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.entities import CampusProcess, Canteen, Conversation, Location, Message, Source, Task, User
from app.schemas.agent import AgentChatResponse, ToolResult
from app.services.notification_service import NotificationService
from app.services.time_service import now_china


logger = logging.getLogger("gduf-api.agent")

INTENTS = {
    "campus_location_search", "canteen_search", "food_search", "notification_to_tasks",
    "task_management", "campus_process", "learning_guidance", "campus_life_guidance",
    "general_chat", "out_of_scope",
}

FACT_INTENTS = {"campus_location_search", "canteen_search", "food_search", "campus_process"}
TRUSTED_STATUSES = {"official", "admin_verified", "user_verified"}


class IntentPlan(BaseModel):
    intent: str
    confidence: float = Field(ge=0, le=1)
    query: str = ""
    tool_plan: list[str] = Field(default_factory=list)


class GuidanceAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=3000)


class AgentService:
    FALLBACK_PATTERNS = (
        ("notification_to_tasks", r"截止|提交材料|班群通知|生成任务|通知转|文件命名"),
        ("task_management", r"我的任务|待办|已完成|逾期|任务中心"),
        ("campus_process", r"校园卡|挂失|补办|报修|请假|办事|证明"),
        ("food_search", r"有什么吃|吃什么|想吃|早餐|午餐|晚餐|面|粉|奶茶|咖啡|档口|菜品"),
        ("canteen_search", r"饭堂|食堂|餐厅"),
        ("campus_location_search", r"在哪|哪里|位置|教学楼|宿舍|快递|医务|卫生所|超市|图书馆|导航|怎么走"),
        ("learning_guidance", r"高数|跟不上|复习|学习|考试|考试周|课程|论文|四六级|作业"),
        ("campus_life_guidance", r"社团|新生|入学|宿舍生活|适应大学|人际|校园生活"),
    )

    CATEGORY_TERMS = {
        "canteen": ("饭堂", "食堂", "餐厅"),
        "teaching_building": ("教学楼", "北教", "教室"),
        "express_station": ("快递", "驿站", "取件", "拿快递"),
        "medical": ("医务室", "医务所", "卫生所", "看病"),
        "library": ("图书馆", "自习"),
        "supermarket": ("超市", "商店"),
        "campus_service": ("校园卡", "补卡", "卡部", "服务前线"),
    }

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.model_error_id: str | None = None

    def _model_error(self, event: str, exc: Exception) -> None:
        self.model_error_id = uuid4().hex[:12]
        logger.warning("%s error_id=%s error_type=%s", event, self.model_error_id, type(exc).__name__)

    def _model_json(self, system_prompt: str, user_message: str) -> dict:
        client = OpenAI(api_key=self.settings.deepseek_api_key, base_url=self.settings.deepseek_base_url, timeout=20.0)
        response = client.chat.completions.create(
            model=self.settings.deepseek_model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
        )
        return json.loads(response.choices[0].message.content or "{}")

    def _llm_plan(self, message: str) -> IntentPlan:
        prompt = (
            "你是校园 Agent 的意图规划器，只输出 JSON：intent/confidence/query/tool_plan。"
            f"intent 必须属于：{sorted(INTENTS)}。"
            "地点、饭堂、餐品、校内制度和办事流程属于校园事实，必须选择对应数据库工具；"
            "学习建议、校园生活建议和寒暄可以不调用校园事实工具。"
        )
        plan = IntentPlan.model_validate(self._model_json(prompt, message))
        if plan.intent not in INTENTS:
            raise ValueError("unsupported intent")
        if plan.intent in FACT_INTENTS and not plan.tool_plan:
            raise ValueError("campus facts require a tool plan")
        return plan

    def classify(self, message: str) -> tuple[IntentPlan, bool]:
        if self.settings.deepseek_api_key:
            try:
                return self._llm_plan(message), False
            except Exception as exc:
                self._model_error("intent_model_fallback", exc)
        for intent, pattern in self.FALLBACK_PATTERNS:
            if re.search(pattern, message, re.I):
                return IntentPlan(intent=intent, confidence=0.68, query=message, tool_plan=[intent]), True
        return IntentPlan(intent="general_chat", confidence=0.58, query=message), True

    @staticmethod
    def _source(source: Source) -> dict:
        return {
            "id": source.id,
            "title": source.title,
            "url": source.url,
            "publisher": source.publisher,
            "source_type": source.source_type,
            "published_at": source.published_at.isoformat() if source.published_at else None,
            "verified_at": source.verified_at.isoformat() if source.verified_at else None,
            "confidence": source.confidence,
            "is_official": source.is_official,
        }

    @staticmethod
    def _dedupe_sources(sources: list[dict]) -> list[dict]:
        unique: dict[str, dict] = {}
        for source in sources:
            unique[str(source.get("id") or source.get("url") or source.get("title"))] = source
        return list(unique.values())

    @staticmethod
    def _data_status(values: list[str]) -> str:
        return "verified" if values and all(value in TRUSTED_STATUSES for value in values) else "needs_verification"

    def _locations(self, message: str, campus_id: str | None) -> tuple[str, list[ToolResult], list[dict], str]:
        query = (
            select(Location)
            .options(selectinload(Location.sources))
            .where(Location.is_active.is_(True), Location.data_status != "demo_fixture")
        )
        if campus_id:
            query = query.where(Location.campus_id == campus_id)
        rows = list(self.db.scalars(query).unique())
        normalized = re.sub(r"[\s，。？?、！!]", "", message).lower()
        requested_categories = {
            category for category, keywords in self.CATEGORY_TERMS.items() if any(keyword in normalized for keyword in keywords)
        }
        ranked: list[tuple[int, Location]] = []
        for row in rows:
            score = 0
            names = [row.name, *row.aliases]
            if any(name and name.lower() in normalized for name in names):
                score += 100
            if row.category in requested_categories:
                score += 40
            searchable = " ".join([row.name, *row.aliases, row.description, row.address, row.area, row.floor, *row.services]).lower()
            for token in re.findall(r"[\u4e00-\u9fff]{2,8}|[a-z0-9]{2,}", message.lower()):
                if token in searchable:
                    score += min(len(token), 6)
            if score:
                ranked.append((score, row))
        matched = [row for _, row in sorted(ranked, key=lambda item: (-item[0], item[1].name))[:8]]
        if not matched:
            return (
                "没有找到匹配的可公开地点记录。系统已排除演示数据，不会用假点位填充结果。",
                [ToolResult(tool="location_search", title="地点搜索", data=[])],
                [],
                "needs_verification",
            )
        data = [
            {
                "id": row.id,
                "name": row.name,
                "aliases": row.aliases,
                "category": row.category,
                "address": row.address,
                "area": row.area,
                "floor": row.floor,
                "opening_hours": row.opening_hours,
                "services": row.services,
                "phone": row.phone,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "map_x": row.map_x,
                "map_y": row.map_y,
                "verification_status": row.verification_status,
                "data_status": row.data_status,
                "verified_at": row.verified_at.isoformat() if row.verified_at else None,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in matched
        ]
        sources = self._dedupe_sources([self._source(source) for row in matched for source in row.sources])
        answer = f"找到 {len(matched)} 条匹配地点。精确楼栋或开放时间没有来源时会留空，并标记为待核验。"
        return answer, [ToolResult(tool="location_search", title="校园地点", data=data)], sources, self._data_status([row.data_status for row in matched])

    @staticmethod
    def _food_matches(message: str, stall) -> bool:
        haystack = " ".join([stall.name, stall.food_type, *stall.common_items, *stall.meal_periods]).lower()
        normalized = message.lower()
        direct_terms = [item for item in stall.common_items if item and item.lower() in normalized]
        if direct_terms or (stall.food_type and stall.food_type.lower() in normalized):
            return True
        generic = {"有什么吃", "吃什么", "档口", "菜品"}
        if any(term in normalized for term in generic):
            return True
        return any(term in haystack and term in normalized for term in ("早餐", "面", "粉", "饭", "烧腊", "肠粉", "麻辣烫", "快餐"))

    def _canteens(self, message: str, campus_id: str | None, food: bool = False) -> tuple[str, list[ToolResult], list[dict], str]:
        query = (
            select(Canteen)
            .options(selectinload(Canteen.stalls), selectinload(Canteen.source), selectinload(Canteen.location))
            .where(Canteen.is_active.is_(True), Canteen.data_status != "demo_fixture")
        )
        if campus_id:
            query = query.where(Canteen.campus_id == campus_id)
        rows = list(self.db.scalars(query).unique())
        named = [
            row for row in rows
            if row.name in message or (row.location and any(alias in message for alias in row.location.aliases))
        ]
        if named:
            rows = named
        data: list[dict] = []
        sources: list[dict] = []
        statuses: list[str] = []
        for row in rows:
            stalls = [stall for stall in row.stalls if stall.is_active and stall.data_status != "demo_fixture"]
            if food:
                stalls = [stall for stall in stalls if self._food_matches(message, stall)]
            data.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "area": row.location.area if row.location else "",
                    "address": row.location.address if row.location else "",
                    "floors": row.floors,
                    "opening_hours": row.opening_hours,
                    "verification_status": row.verification_status,
                    "data_status": row.data_status,
                    "verified_at": row.verified_at.isoformat() if row.verified_at else None,
                    "stalls": [
                        {
                            "id": stall.id,
                            "name": stall.name,
                            "floor": stall.floor,
                            "food_type": stall.food_type,
                            "common_items": stall.common_items,
                            "meal_periods": stall.meal_periods,
                            "data_status": stall.data_status,
                            "verified_at": stall.verified_at.isoformat() if stall.verified_at else None,
                        }
                        for stall in stalls
                    ],
                    "today_menu_available": False,
                }
            )
            statuses.append(row.data_status)
            statuses.extend(stall.data_status for stall in stalls)
            if row.source:
                sources.append(self._source(row.source))
        has_stalls = any(item["stalls"] for item in data)
        if food and has_stalls:
            answer = "目前没有可靠的当日菜单数据，以下是最近一次核验的档口或常见餐品信息，不保证今日全部供应。"
        elif food:
            answer = "目前没有可靠的当日菜单数据，也没有匹配的可公开档口或常见餐品记录；系统不会编造今日供应。"
        elif rows:
            answer = "以下是数据库中的饭堂位置与历史资料。当前营业时间和当日菜单没有可靠数据时不会展示为实时信息。"
        else:
            answer = "该校区暂无可公开饭堂记录；演示条目不会出现在生产查询中。"
        return answer, [ToolResult(tool="food_search" if food else "canteen_search", title="饭堂与档口", data=data)], self._dedupe_sources(sources), self._data_status(statuses)

    def _processes(self, message: str, campus_id: str | None) -> tuple[str, list[ToolResult], list[dict], str]:
        query = select(CampusProcess).options(selectinload(CampusProcess.source)).where(CampusProcess.is_active.is_(True))
        if campus_id:
            query = query.where(or_(CampusProcess.campus_id == campus_id, CampusProcess.campus_id.is_(None)))
        rows = list(self.db.scalars(query))
        normalized = re.sub(r"[\s，。？?、！!]", "", message)
        process_terms = {
            "校园卡": ("校园卡", "补卡", "挂失", "丢卡", "卡丢了"),
            "报修": ("报修", "维修", "坏了"),
            "请假": ("请假", "销假"),
            "证明": ("证明", "盖章", "在读证明"),
        }
        requested = {
            concept for concept, aliases in process_terms.items()
            if any(alias in normalized for alias in aliases)
        }
        matched = []
        for row in rows:
            searchable = f"{row.title}{row.category}"
            if any(concept in searchable for concept in requested):
                matched.append(row)
                continue
            meaningful = [
                token for token in re.findall(r"[\u4e00-\u9fff]{2,4}", normalized)
                if token not in {"哪里", "怎么", "办理", "流程", "需要", "我要"}
            ]
            if any(token in searchable for token in meaningful):
                matched.append(row)
        data = [
            {
                "id": item.id,
                "title": item.title,
                "steps": item.steps,
                "materials": item.materials,
                "contact": item.contact,
                "verification_status": item.verification_status,
                "verified_at": item.verified_at.isoformat() if item.verified_at else None,
            }
            for item in matched[:8]
        ]
        sources = self._dedupe_sources([self._source(item.source) for item in matched if item.source])
        answer = "已返回有公开来源的办事资料；未公开的现场地址和时限不会补写。" if matched else "目前没有匹配且有来源的办事流程；我不会补写地点、费用或时限。"
        status = "verified" if matched and all(item.verification_status == "verified" for item in matched) else "needs_verification"
        return answer, [ToolResult(tool="process_search", title="校园办事流程", data=data)], sources, status

    def _fallback_guidance(self, message: str, intent: str) -> str:
        if intent == "learning_guidance" and "高数" in message:
            return "先定位卡点：用一套基础题区分是概念、计算还是题型识别问题；每天安排 30 分钟补概念、30 分钟做 3—5 道同类题，并把错因写成一句话。连续一周仍无改善时，带着具体错题去问老师或助教，比笼统地说‘听不懂’更容易获得帮助。"
        if intent == "learning_guidance" and "考试周" in message:
            return "先列出每门考试的日期、范围和当前掌握度，再按“临近程度 × 薄弱程度”排序。每天只设 2—3 个可完成目标，晚间留 20 分钟回顾错题和调整第二天计划；不要把通宵当作固定安排。"
        if intent == "learning_guidance":
            return "把目标拆成未来七天可执行的小任务：先列考试或作业节点，再为每天安排一个高专注时段和一个复盘时段。你可以告诉我课程、当前困难和截止日期，我会进一步帮你拆解。"
        if intent == "campus_life_guidance" and "社团" in message:
            return "先按兴趣、时间成本和想获得的成长各选一个候选社团，再去参加一次公开活动或招新交流。建议第一学期不要同时承担太多核心岗位，先观察活动频率和团队氛围再决定长期投入。具体报名时间和校内规定需要以当期官方通知为准。"
        if intent == "campus_life_guidance" and ("新生" in message or "入学" in message):
            return "新生阶段优先确认报到材料、课程平台、校园卡和宿舍安全；把班级正式通知与个人待办分开保存。具体报到地点、时间和材料必须以当年学校通知为准，我不会把通用建议说成学校规定。"
        if intent == "campus_life_guidance":
            return "可以先说明你的具体场景、所在校区和希望解决的问题。我会把通用建议与校园事实分开；地点、电话和制度只使用数据库及公开来源。"
        if re.search(r"你好|能做什么|你是谁", message):
            return "你好，我是广金大师兄。我能查询有来源的校园地点和饭堂资料、把通知拆成可编辑任务、管理你的待办，也能提供学习与校园生活建议。没有可靠数据时我会明确说不知道或进入基础模式。"
        return "我可以继续帮你把问题拆清楚。若问题涉及校园地点、饭堂、流程或通知，请尽量提供校区和原文；若是学习或生活问题，请补充你的目标与当前困难。"

    def _guidance(self, message: str, intent: str) -> tuple[str, bool]:
        if self.settings.deepseek_api_key:
            prompt = (
                "你是面向大学生的校园助手。只输出 JSON 对象 {\"answer\":\"...\"}。"
                "回答要针对用户问题给出可执行建议，不要声称知道任何未提供的校内地点、制度、电话、价格或实时状态；"
                "如果问题需要校园事实，明确建议使用校园查询工具。"
            )
            try:
                answer = GuidanceAnswer.model_validate(self._model_json(prompt, message)).answer
                return answer, False
            except Exception as exc:
                self._model_error("guidance_model_fallback", exc)
        return self._fallback_guidance(message, intent), True

    def chat(self, user: User, message: str, conversation_id: str | None, campus_id: str | None) -> AgentChatResponse:
        plan, degraded = self.classify(message)
        conversation = None
        if conversation_id:
            conversation = self.db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id))
            if not conversation:
                raise HTTPException(status_code=404, detail="对话不存在")
        if not conversation:
            conversation = Conversation(user_id=user.id, campus_id=campus_id or user.campus_id, title=message[:60])
            self.db.add(conversation)
            self.db.flush()
        elif campus_id:
            conversation.campus_id = campus_id

        self.db.add(Message(conversation_id=conversation.id, role="user", content=message, intent=plan.intent))
        tool_results: list[ToolResult] = []
        sources: list[dict] = []
        requires_confirmation = False
        data_status = "not_applicable"
        effective_campus = campus_id or conversation.campus_id or user.campus_id

        if plan.intent == "campus_location_search":
            answer, tool_results, sources, data_status = self._locations(message, effective_campus)
        elif plan.intent in {"canteen_search", "food_search"}:
            answer, tool_results, sources, data_status = self._canteens(message, effective_campus, plan.intent == "food_search")
        elif plan.intent == "notification_to_tasks":
            drafts, mode, warning = NotificationService().extract(message)
            tool_results = [ToolResult(tool="notification_parser", title="通知任务预览", data=[draft.model_dump(mode="json") for draft in drafts])]
            answer = "已生成任务预览。请到通知处理页逐项编辑，并明确确认后写入数据库。" + (f" {warning}" if warning else "")
            requires_confirmation = True
            degraded = degraded or mode == "rules"
        elif plan.intent == "task_management":
            tasks = list(self.db.scalars(select(Task).where(Task.user_id == user.id).order_by(Task.deadline.is_(None), Task.deadline)))
            data = [{"id": task.id, "title": task.title, "deadline": task.deadline.isoformat() if task.deadline else None, "status": task.status} for task in tasks]
            tool_results = [ToolResult(tool="task_list", title="我的任务", data=data)]
            answer = f"你当前共有 {len(tasks)} 条任务，其中 {sum(task.status == 'pending' for task in tasks)} 条待完成。"
        elif plan.intent == "campus_process":
            answer, tool_results, sources, data_status = self._processes(message, effective_campus)
        elif plan.intent in {"learning_guidance", "campus_life_guidance", "general_chat"}:
            answer, guidance_degraded = self._guidance(message, plan.intent)
            degraded = degraded or guidance_degraded
        else:
            answer = "这个请求超出了当前校园助手的安全范围。我可以继续处理校园查询、通知任务、学习与校园生活问题。"

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
            error_id=self.model_error_id,
            data_status=data_status,
            current_time=now_china(),
        )
