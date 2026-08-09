"""Hybrid intent routing and deterministic local-tool orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Callable

from core.time_service import format_current_time_prompt, now_china
from services.location_service import LocationService, normalize_campus
from services.notification_service import NotificationDraft, NotificationService
from services.task_service import TaskService


INTENTS = (
    "campus_location_search",
    "canteen_search",
    "food_search",
    "nearby_location_search",
    "campus_navigation",
    "campus_data_freshness",
    "notification_to_tasks",
    "campus_process",
    "task_management",
    "general_chat",
)


@dataclass
class IntentDecision:
    intent: str
    campus: str | None
    confidence: float
    reason: str
    tool_plan: list[str] = field(default_factory=list)


@dataclass
class AgentResponse:
    intent: str
    campus: str | None
    content: str
    data: Any = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str | None = None
    requires_confirmation: bool = False
    tool_plan: list[str] = field(default_factory=list)


class Orchestrator:
    """Route by scored language patterns, entities, context, and optional classifier."""

    PATTERNS = {
        "notification_to_tasks": (
            (r"截止|DDL|提交材料|提交方式|班群通知|通知转|生成日历", 3),
            (r"\d{1,2}月\d{1,2}日|20\d{2}[-年/]", 2),
        ),
        "task_management": (
            (r"我.*任务|待办|没完成|已完成|这周.*什么|任务中心", 4),
            (r"完成.*任务|标记.*完成", 3),
        ),
        "food_search": (
            (r"吃什么|有什么吃|想吃|早餐|午餐|晚餐|面|粉|饭|咖啡|奶茶", 3),
            (r"档口|餐品|菜单", 3),
        ),
        "canteen_search": (
            (r"饭堂|食堂|餐厅", 3),
            (r"几个|哪些|哪家|楼层|营业|关门", 2),
        ),
        "nearby_location_search": (
            (r"附近|最近|离我|离.*近|周边", 4),
            (r"哪里|地点|饭堂|快递|超市|ATM", 1),
        ),
        "campus_navigation": (
            (r"怎么走|路线|导航|从.+到|去.+怎么", 4),
        ),
        "campus_data_freshness": (
            (r"多久更新|最后更新|核验时间|是否过期|最新更新|数据新鲜", 4),
        ),
        "campus_process": (
            (r"校园卡.*(丢|挂失|补办)|报修|请假|办事|证明|缴费", 4),
        ),
        "campus_location_search": (
            (r"在哪|哪里|位置|地点|教学楼|宿舍|医务|快递|超市|体育|校门|ATM|打印", 3),
        ),
    }

    TOOL_PLANS = {
        "campus_location_search": ["search_locations", "calculate_freshness"],
        "canteen_search": ["list_canteens", "get_canteen_details", "calculate_freshness"],
        "food_search": ["list_food_stalls", "get_canteen_details"],
        "nearby_location_search": ["find_nearby_locations"],
        "campus_navigation": ["search_locations", "build_navigation_link"],
        "campus_data_freshness": ["search_locations", "calculate_freshness"],
        "notification_to_tasks": ["extract_notification", "preview_tasks"],
        "campus_process": ["lookup_campus_process"],
        "task_management": ["list_tasks"],
        "general_chat": [],
    }

    def __init__(
        self,
        location_service: LocationService | None = None,
        task_service: TaskService | None = None,
        notification_service: NotificationService | None = None,
        classifier: Callable[[str, str | None], str | None] | None = None,
    ):
        self.location_service = location_service or LocationService()
        self.task_service = task_service or TaskService(self.location_service.database.path)
        self.notification_service = notification_service or NotificationService()
        self.classifier = classifier

    @staticmethod
    def extract_campus(text: str, campus_hint: str | None = None) -> str | None:
        for alias in sorted(
            ("广州校本部", "广州校区", "校本部", "本部", "肇庆校区", "肇庆", "清远校区", "清远"),
            key=len,
            reverse=True,
        ):
            if alias in text:
                return normalize_campus(alias)
        return normalize_campus(campus_hint) if campus_hint else None

    def classify_intent(self, text: str, campus_hint: str | None = None) -> IntentDecision:
        campus = self.extract_campus(text, campus_hint)
        normalized = (text or "").strip()
        if not normalized or re.fullmatch(r"(你好|您好|嗨|hi|hello|在吗)[！!。,.，\s]*", normalized, re.I):
            return IntentDecision("general_chat", campus, 0.99, "一般问候", [])
        if self.classifier:
            candidate = self.classifier(normalized, campus)
            if candidate in INTENTS:
                return IntentDecision(candidate, campus, 0.9, "外部分类器", self.TOOL_PLANS[candidate])
        scores: dict[str, int] = {}
        reasons: dict[str, list[str]] = {}
        for intent, patterns in self.PATTERNS.items():
            for pattern, weight in patterns:
                if re.search(pattern, normalized, flags=re.I):
                    scores[intent] = scores.get(intent, 0) + weight
                    reasons.setdefault(intent, []).append(pattern)
        # Context-sensitive tie breakers: location semantics outrank generic food characters.
        if "饭堂" in normalized or "食堂" in normalized:
            scores["canteen_search"] = scores.get("canteen_search", 0) + 2
        if re.search(
            r"(面|粉|早餐|奶茶|咖啡).*(哪|哪里|哪儿|饭堂)"
            r"|(哪|哪里|哪儿).*(面|粉|早餐|奶茶|咖啡|吃)"
            r"|想吃|买早餐",
            normalized,
        ):
            scores["food_search"] = scores.get("food_search", 0) + 4
        if re.search(r"从.+到|怎么走|导航", normalized):
            scores["campus_navigation"] = scores.get("campus_navigation", 0) + 5
        if re.search(r"附近|最近|离.+近", normalized):
            scores["nearby_location_search"] = scores.get("nearby_location_search", 0) + 5
        if not scores:
            intent = "general_chat"
            score = 0
        else:
            priority = {intent: index for index, intent in enumerate(INTENTS)}
            intent, score = max(scores.items(), key=lambda item: (item[1], -priority[item[0]]))
        confidence = min(0.98, 0.5 + score * 0.08) if score else 0.55
        return IntentDecision(
            intent,
            campus,
            confidence,
            "；".join(reasons.get(intent, [])) or "未命中校园工具意图",
            list(self.TOOL_PLANS[intent]),
        )

    @staticmethod
    def _source_dicts(location: dict[str, Any]) -> list[dict[str, Any]]:
        return list(location.get("source_references") or [])

    @staticmethod
    def _location_line(location: dict[str, Any], navigation: str = "") -> str:
        verified = location.get("verified_at") or "未核验"
        warning = "⚠️ " if location.get("freshness_status") != "current" else ""
        source = (location.get("source_references") or [{}])[0]
        return (
            f"- {warning}**{location['name']}**｜{location.get('area') or location.get('address') or '位置待核验'}"
            f"｜最后核验：{verified}｜来源：{source.get('publisher') or source.get('title') or '待补充'}"
            + (f"｜[导航]({navigation})" if navigation else "")
        )

    def _handle_canteens(self, text: str, campus: str | None) -> AgentResponse:
        if not campus:
            return AgentResponse("canteen_search", None, "请先指定广州校本部、肇庆校区或清远校区。")
        canteens = self.location_service.list_canteens(campus)
        named_canteens = [
            item
            for item in canteens
            if item.name in text or any(alias in text for alias in item.aliases)
        ]
        if named_canteens:
            canteens = named_canteens
        if not canteens:
            return AgentResponse("canteen_search", campus, f"{campus}暂无已记录饭堂数据，等待管理员核验。", data=[])
        lines = [f"{campus}当前匹配 {len(canteens)} 个饭堂条目："]
        sources = []
        for canteen in canteens:
            navigation = self.location_service.build_navigation_link(canteen)
            payload = canteen.to_dict()
            details = self.location_service.get_canteen_details(canteen.id) or {}
            verified_stalls = [
                item
                for item in details.get("food_stalls", [])
                if item.get("verified_at")
                and item.get("data_status") not in {"demo_fixture", "unverified_seed"}
            ]
            source = (payload.get("source_references") or [{}])[0]
            lines.extend(
                [
                    f"\n### {canteen.name}",
                    f"- 所属校区：{canteen.campus}",
                    f"- 所在位置：{canteen.area or canteen.address or '待核验'}",
                    f"- 楼层：{canteen.floor or '待核验'}",
                    "- 最近核验档口："
                    + ("、".join(item["name"] for item in verified_stalls) if verified_stalls else "暂无已核验档口"),
                    "- 常见餐品："
                    + (
                        "、".join(
                            dict.fromkeys(
                                food
                                for item in verified_stalls
                                for food in item.get("common_items", [])
                            )
                        )
                        or "暂无已核验信息"
                    ),
                    f"- 开放时间：{canteen.opening_hours or '待核验'}",
                    f"- 支付方式：{'、'.join(canteen.payment_methods) or '待核验'}",
                    f"- 数据状态：{canteen.data_status} / {canteen.freshness_status}",
                    f"- 最后核验：{canteen.verified_at or '未核验'}｜置信度：{canteen.confidence:.0%}",
                    f"- 来源：{source.get('publisher') or source.get('title') or '待补充'}",
                    f"- 导航：[ 打开地图 ]({navigation})",
                ]
            )
            sources.extend(self._source_dicts(payload))
        lines.append("\n历史资料或待核验条目不代表当前营业；上述常见餐品也不代表今日一定供应。")
        return AgentResponse(
            "canteen_search",
            campus,
            "\n".join(lines),
            data=[item.to_dict() for item in canteens],
            sources=sources,
            updated_at=max((item.updated_at or "" for item in canteens), default=None),
        )

    def _handle_food(self, text: str, campus: str | None) -> AgentResponse:
        if not campus:
            return AgentResponse("food_search", None, "请先指定要查询的校区。")
        food_terms = re.findall(r"早餐|午餐|晚餐|面|粉|饭|咖啡|奶茶|轻食", text)
        query = food_terms[0] if food_terms else ""
        stalls = self.location_service.list_food_stalls(
            campus=campus, query=query, verified_only=True
        )
        if not stalls:
            return AgentResponse(
                "food_search",
                campus,
                (
                    f"{campus}目前没有可用于回答“{query or '该餐饮类型'}”的已核验档口数据。"
                    "我不会根据旧文章编造今日供应；可在数据管理页补充管理员核验记录。"
                ),
                data=[],
            )
        lines = ["以下是最近核验信息，不保证今日所有档口均营业："]
        for stall in stalls:
            canteen = self.location_service.get_location(stall.canteen_id)
            lines.append(
                f"- **{canteen.name if canteen else stall.canteen_id} / {stall.name}**｜"
                f"楼层：{stall.floor or '待核验'}｜常见餐品：{'、'.join(stall.common_items) or '未记录'}｜"
                f"最后核验：{stall.verified_at or '未核验'}"
            )
        return AgentResponse("food_search", campus, "\n".join(lines), data=[item.to_dict() for item in stalls])

    def _handle_locations(self, text: str, campus: str | None) -> AgentResponse:
        if not campus:
            return AgentResponse("campus_location_search", None, "请先指定校区，避免混入其他校区地点。")
        query = re.sub(r"广州校本部|广州校区|校本部|肇庆校区|清远校区|在哪|哪里|位置|怎么走|[？?]", "", text).strip()
        locations = self.location_service.search_locations(query=query, campus=campus)
        lines = [self._location_line(item.to_dict(), self.location_service.build_navigation_link(item)) for item in locations[:10]]
        content = "\n".join(lines) if lines else f"{campus}暂无匹配地点，等待管理员补充。"
        return AgentResponse(
            "campus_location_search",
            campus,
            content,
            data=[item.to_dict() for item in locations],
            sources=[source for item in locations for source in self._source_dicts(item.to_dict())],
        )

    def _handle_navigation(self, text: str, campus: str | None) -> AgentResponse:
        if not campus:
            return AgentResponse("campus_navigation", None, "请先指定校区和目的地。")
        locations = self.location_service.search_locations(campus=campus)
        destination = next((item for item in locations if item.name in text or any(alias in text for alias in item.aliases)), None)
        if not destination:
            return AgentResponse("campus_navigation", campus, "没有找到已记录的目的地，请提供更准确的地点名称。")
        link = self.location_service.build_navigation_link(destination)
        precision = "GPS/地址导航" if destination.latitude is not None else "地址搜索；校内点位仅为示意"
        return AgentResponse(
            "campus_navigation",
            campus,
            f"目的地：**{destination.name}**\n\n[打开导航]({link})\n\n定位类型：{precision}。",
            data={"location": destination.to_dict(), "navigation": link},
            sources=self._source_dicts(destination.to_dict()),
        )

    def _handle_nearby(self, text: str, campus: str | None) -> AgentResponse:
        if not campus:
            return AgentResponse("nearby_location_search", None, "请先指定校区和起点。")
        all_locations = self.location_service.search_locations(campus=campus)
        origin = next(
            (
                item
                for item in all_locations
                if item.name in text or any(alias in text for alias in item.aliases)
            ),
            None,
        )
        if not origin:
            return AgentResponse(
                "nearby_location_search",
                campus,
                "请在地图页选择已知起点，或在问题中写出已记录的起点名称。",
                data=[],
            )
        category = None
        category_terms = {
            "canteen": ("饭堂", "食堂", "吃饭"),
            "express_station": ("快递",),
            "supermarket": ("超市",),
            "medical": ("医务", "医院"),
            "atm": ("ATM", "取款"),
            "printing": ("打印",),
        }
        for candidate, terms in category_terms.items():
            if any(term.casefold() in text.casefold() for term in terms):
                category = candidate
                break
        results = self.location_service.find_nearby_locations(
            campus=campus,
            latitude=origin.latitude,
            longitude=origin.longitude,
            map_x=origin.map_x,
            map_y=origin.map_y,
            category=category,
            limit=8,
        )
        results = [item for item in results if item["location"]["id"] != origin.id][:5]
        if not results:
            return AgentResponse(
                "nearby_location_search",
                campus,
                f"没有找到可从“{origin.name}”计算距离的匹配地点。",
                data=[],
            )
        lines = [f"以 **{origin.name}** 为起点："]
        for item in results:
            location = item["location"]
            distance = (
                f"{item['distance']:.0f} 米"
                if item["unit"] == "m"
                else f"{item['distance']:.3f} 示意单位"
            )
            lines.append(
                f"- **{location['name']}**｜{distance}｜{location.get('freshness_status')}｜"
                f"[ 导航 ]({self.location_service.build_navigation_link(location['id'])})"
            )
        if any(item["precision"] == "schematic" for item in results):
            lines.append("\n示意单位只表示校内相对远近，不代表实际步行米数。")
        return AgentResponse("nearby_location_search", campus, "\n".join(lines), data=results)

    def _handle_freshness(self, campus: str | None) -> AgentResponse:
        if not campus:
            return AgentResponse("campus_data_freshness", None, "请先指定校区。")
        locations = self.location_service.search_locations(campus=campus)
        locations.sort(key=lambda item: item.verified_at or "", reverse=True)
        lines = [
            f"- {item.name}：{item.verified_at or '未核验'}（{item.freshness_status}）"
            for item in locations
        ]
        return AgentResponse(
            "campus_data_freshness",
            campus,
            "\n".join(lines) if lines else "暂无数据。",
            data=[item.to_dict() for item in locations],
        )

    def _handle_tasks(self, user_id: str, reference_time=None) -> AgentResponse:
        tasks = self.task_service.list_week_tasks(user_id, reference_time, incomplete_only=True)
        if not tasks:
            content = "本周没有未完成任务。"
        else:
            content = "本周未完成任务：\n" + "\n".join(
                f"- {task.title}｜截止：{task.deadline or '未设置'}｜状态：{task.status}"
                for task in tasks
            )
        return AgentResponse("task_management", None, content, data=[task.to_dict() for task in tasks])

    def _handle_process(self, text: str, campus: str | None) -> AgentResponse:
        if "校园卡" in text:
            content = (
                "已识别为校园卡办事问题。当前结构化数据中没有经过核验的具体挂失/补办流程，"
                "请先联系所在校区校园卡服务点或查看学校官方通知；我不会补写办理地点、费用和时限。"
            )
        else:
            content = "已识别为校园办事问题，但当前没有可验证的结构化流程，请由管理员补充官方来源。"
        return AgentResponse("campus_process", campus, content, data={"status": "needs_verification"})

    def handle(
        self,
        user_input: str,
        user_id: str,
        campus_hint: str | None = None,
        api_key: str = "",
        reference_time=None,
    ) -> AgentResponse:
        decision = self.classify_intent(user_input, campus_hint)
        if decision.intent == "canteen_search":
            response = self._handle_canteens(user_input, decision.campus)
        elif decision.intent == "food_search":
            response = self._handle_food(user_input, decision.campus)
        elif decision.intent == "campus_location_search":
            response = self._handle_locations(user_input, decision.campus)
        elif decision.intent == "campus_navigation":
            response = self._handle_navigation(user_input, decision.campus)
        elif decision.intent == "campus_data_freshness":
            response = self._handle_freshness(decision.campus)
        elif decision.intent == "task_management":
            response = self._handle_tasks(user_id, reference_time)
        elif decision.intent == "notification_to_tasks":
            drafts: list[NotificationDraft] = self.notification_service.extract(
                user_input, api_key=api_key, reference_time=reference_time
            )
            response = AgentResponse(
                decision.intent,
                decision.campus,
                "已提取通知草稿，请确认后再保存任务。",
                data=[draft.to_dict() for draft in drafts],
                requires_confirmation=True,
            )
        elif decision.intent == "campus_process":
            response = self._handle_process(user_input, decision.campus)
        elif decision.intent == "nearby_location_search":
            response = self._handle_nearby(user_input, decision.campus)
        else:
            response = AgentResponse(
                "general_chat",
                decision.campus,
                "你好，我是广金大师兄。可以查校园地点、饭堂、通知待办和本周任务。\n\n"
                + format_current_time_prompt(reference_time),
            )
        response.tool_plan = decision.tool_plan
        response.updated_at = response.updated_at or now_china(reference_time).isoformat()
        return response
