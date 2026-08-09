from __future__ import annotations

from datetime import timedelta
import re
from typing import Any
from urllib.parse import quote

import httpx
from icalendar import Calendar
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.agents.contracts import ToolResponse
from app.core.config import get_settings
from app.models.entities import (
    CampusProcess, Canteen, FoodStall, KnowledgeDocument, Location, Source, Task, TaskReminder, User, UserPreference, utcnow,
)
from app.services.ics_service import generate_ics
from app.services.map_service import MapService, MapServiceError
from app.services.knowledge_service import (
    KnowledgeImportError,
    create_import_job,
    fetch_article,
    finish_import_job,
    import_document,
    reindex_documents as rebuild_knowledge_index,
    search_knowledge,
)
from app.services.notification_service import NotificationService
from app.services.time_service import now_china, parse_relative_datetime


def _source(source: Source | None) -> dict[str, Any] | None:
    if not source:
        return None
    return {
        "id": source.id, "title": source.title, "url": source.url, "publisher": source.publisher,
        "source_type": source.source_type, "published_at": source.published_at,
        "verified_at": source.verified_at, "confidence": source.confidence, "is_official": source.is_official,
    }


def _task_data(task: Task) -> dict[str, Any]:
    return {
        "id": task.id, "user_id": task.user_id, "title": task.title, "description": task.description,
        "deadline": task.deadline, "location": task.location, "course": task.course, "task_type": task.task_type,
        "materials": task.materials, "submission_target": task.submission_target,
        "submission_method": task.submission_method, "file_naming": task.file_naming,
        "source_text": task.source_text, "source_url": task.source_url, "status": task.status,
    }


class AgentToolbox:
    """Authenticated, campus-scoped implementations for every registered Agent tool."""

    def __init__(self, db: Session, user: User, campus_id: str | None):
        self.db = db
        self.user = user
        self.campus_id = campus_id or user.campus_id

    @staticmethod
    def _ok(name: str, data: Any, summary: str, *, sources: list[dict] | None = None, verification: dict | None = None, action: bool = False) -> ToolResponse:
        return ToolResponse(
            tool_name=name, success=True, data=data, summary=summary, sources=sources or [],
            verification=verification or {}, requires_user_action=action,
        )

    @staticmethod
    def _confirmation(name: str, summary: str, data: Any = None) -> ToolResponse:
        return ToolResponse(tool_name=name, success=True, data=data, summary=summary, requires_user_action=True, verification={"confirmed": False})

    def _owned_task(self, task_id: str) -> Task | None:
        return self.db.scalar(select(Task).where(Task.id == task_id, Task.user_id == self.user.id))

    def search_campus_locations(self, query: str = "", category: str | None = None, limit: int = 20, **_: Any) -> ToolResponse:
        statement = select(Location).options(selectinload(Location.sources)).where(
            Location.is_active.is_(True), Location.data_status != "demo_fixture"
        )
        if self.campus_id:
            statement = statement.where(Location.campus_id == self.campus_id)
        if category:
            statement = statement.where(Location.category == category)
        rows = list(self.db.scalars(statement).unique())
        needle = re.sub(r"\s+", "", query.lower())
        if needle:
            rows = [row for row in rows if needle in re.sub(r"\s+", "", " ".join([row.name, *row.aliases, row.description, row.address, row.area, *row.services]).lower())]
        rows = rows[:max(1, min(limit, 50))]
        data = [{
            "id": row.id, "campus_id": row.campus_id, "name": row.name, "aliases": row.aliases,
            "category": row.category, "description": row.description, "address": row.address, "area": row.area,
            "floor": row.floor, "latitude": row.latitude, "longitude": row.longitude,
            "opening_hours": row.opening_hours, "services": row.services, "phone": row.phone,
            "verification_status": row.verification_status, "data_status": row.data_status,
            "verified_at": row.verified_at, "updated_at": row.updated_at,
        } for row in rows]
        sources = [item for row in rows for source in row.sources if (item := _source(source))]
        return self._ok("search_campus_locations", data, f"找到 {len(rows)} 个地点", sources=sources, verification={"campus_id": self.campus_id})

    def get_location_details(self, location_id: str = "", **_: Any) -> ToolResponse:
        row = self.db.scalar(select(Location).options(selectinload(Location.sources)).where(
            Location.id == location_id, Location.is_active.is_(True), Location.data_status != "demo_fixture"
        ))
        if not row or (self.campus_id and row.campus_id != self.campus_id):
            return ToolResponse(tool_name="get_location_details", success=False, error="not_found", summary="地点不存在或不属于当前校区")
        result = self.search_campus_locations(query=row.name)
        result.tool_name = "get_location_details"
        result.data = result.data[0] if result.data else None
        result.summary = f"已读取 {row.name} 详情"
        return result

    def find_nearby_locations(self, latitude: float | None = None, longitude: float | None = None, limit: int = 8, **_: Any) -> ToolResponse:
        if latitude is None or longitude is None:
            return ToolResponse(tool_name="find_nearby_locations", success=False, error="missing_coordinates", summary="附近搜索需要用户授权的真实坐标", requires_user_action=True)
        rows = list(self.db.scalars(select(Location).where(
            Location.campus_id == self.campus_id, Location.is_active.is_(True),
            Location.data_status != "demo_fixture", Location.latitude.is_not(None), Location.longitude.is_not(None),
        )))
        from app.api.campus import _distance
        data = sorted(({
            "id": row.id, "campus_id": row.campus_id, "name": row.name,
            "distance_meters": round(_distance(latitude, longitude, float(row.latitude), float(row.longitude))),
            "latitude": row.latitude, "longitude": row.longitude, "data_status": row.data_status,
        } for row in rows), key=lambda item: item["distance_meters"])[:limit]
        return self._ok("find_nearby_locations", data, f"找到 {len(data)} 个有真实坐标的附近地点", verification={"precision": "gps"})

    def list_location_categories(self, **_: Any) -> ToolResponse:
        rows = self.db.execute(select(Location.category, Location.sub_category).where(
            Location.campus_id == self.campus_id, Location.is_active.is_(True), Location.data_status != "demo_fixture"
        ).distinct()).all()
        data = [{"category": category, "sub_category": sub_category} for category, sub_category in rows]
        return self._ok("list_location_categories", data, f"当前校区有 {len(data)} 组地点分类")

    async def calculate_walking_route(self, origin_location_id: str = "", destination_location_id: str = "", **_: Any) -> ToolResponse:
        origin = self.db.get(Location, origin_location_id)
        destination = self.db.get(Location, destination_location_id)
        if not origin or not destination or origin.campus_id != self.campus_id or destination.campus_id != self.campus_id:
            return ToolResponse(tool_name="calculate_walking_route", success=False, error="not_found", summary="起点或终点不属于当前校区")
        if None in (origin.longitude, origin.latitude, destination.longitude, destination.latitude):
            return ToolResponse(tool_name="calculate_walking_route", success=False, error="unverified_coordinates", summary="起点或终点没有经过核验的真实坐标")
        try:
            data = await MapService.configured().walking_route(
                float(origin.longitude), float(origin.latitude), float(destination.longitude), float(destination.latitude)
            )
        except MapServiceError as exc:
            return ToolResponse(tool_name="calculate_walking_route", success=False, error="map_service", summary=exc.public_message)
        data.update({"origin_location_id": origin.id, "destination_location_id": destination.id})
        return self._ok("calculate_walking_route", data, f"已获取从{origin.name}到{destination.name}的真实步行路线", verification={"provider": "amap"})

    def build_navigation_link(self, location_id: str = "", **_: Any) -> ToolResponse:
        row = self.db.get(Location, location_id)
        if not row or row.campus_id != self.campus_id or None in (row.longitude, row.latitude):
            return ToolResponse(tool_name="build_navigation_link", success=False, error="unverified_coordinates", summary="地点缺少可用于导航的真实坐标")
        url = MapService.navigation_link(row.name, float(row.longitude), float(row.latitude))
        return self._ok("build_navigation_link", {"url": url, "location_id": row.id}, "已生成高德外部导航链接", verification={"provider": "amap_uri"})

    async def geocode_campus_address(self, address: str = "", city: str = "广州", **_: Any) -> ToolResponse:
        try:
            data = await MapService.configured().geocode(address, city)
        except MapServiceError as exc:
            return ToolResponse(tool_name="geocode_campus_address", success=False, error="map_service", summary=exc.public_message)
        return self._ok("geocode_campus_address", data, "高德已返回地址坐标", verification={"provider": "amap"})

    async def geocode_address(self, address: str = "", city: str = "广州", **kwargs: Any) -> ToolResponse:
        result = await self.geocode_campus_address(address=address, city=city, **kwargs)
        result.tool_name = "geocode_address"
        return result

    def list_canteens(self, query: str = "", **_: Any) -> ToolResponse:
        statement = select(Canteen).options(selectinload(Canteen.stalls), selectinload(Canteen.source), selectinload(Canteen.location)).where(
            Canteen.is_active.is_(True), Canteen.data_status != "demo_fixture"
        )
        if self.campus_id:
            statement = statement.where(Canteen.campus_id == self.campus_id)
        rows = list(self.db.scalars(statement).unique())
        if query:
            rows = [row for row in rows if row.name in query or query in row.name]
        data = [{
            "id": row.id, "campus_id": row.campus_id, "name": row.name, "floors": row.floors,
            "opening_hours": row.opening_hours, "payment_methods": row.payment_methods,
            "verification_status": row.verification_status, "data_status": row.data_status,
            "verified_at": row.verified_at, "today_menu_available": False,
            "stalls": [{"id": stall.id, "name": stall.name, "floor": stall.floor, "food_type": stall.food_type, "common_items": stall.common_items, "data_status": stall.data_status} for stall in row.stalls if stall.is_active and stall.data_status != "demo_fixture"],
        } for row in rows]
        sources = [source for row in rows if (source := _source(row.source))]
        return self._ok("list_canteens", data, "饭堂资料不是实时营业或今日菜单", sources=sources, verification={"today_menu_available": False})

    def get_canteen_details(self, canteen_id: str = "", **_: Any) -> ToolResponse:
        result = self.list_canteens()
        result.tool_name = "get_canteen_details"
        result.data = next((row for row in result.data if row["id"] == canteen_id), None)
        result.success = result.data is not None
        result.summary = "已读取饭堂详情" if result.success else "饭堂不存在或不属于当前校区"
        return result

    def list_food_stalls(self, canteen_id: str = "", **_: Any) -> ToolResponse:
        canteen = self.db.get(Canteen, canteen_id)
        if not canteen or canteen.campus_id != self.campus_id:
            return ToolResponse(tool_name="list_food_stalls", success=False, error="not_found", summary="饭堂不存在或不属于当前校区")
        rows = list(self.db.scalars(select(FoodStall).where(
            FoodStall.canteen_id == canteen_id, FoodStall.is_active.is_(True), FoodStall.data_status != "demo_fixture"
        )))
        data = [{"id": row.id, "name": row.name, "floor": row.floor, "food_type": row.food_type, "common_items": row.common_items, "data_status": row.data_status, "verified_at": row.verified_at} for row in rows]
        return self._ok("list_food_stalls", data, f"找到 {len(data)} 条档口历史或核验资料", verification={"today_menu_available": False})

    def search_food(self, query: str = "", **_: Any) -> ToolResponse:
        result = self.list_canteens()
        needle = query.lower()
        matches = []
        for canteen in result.data:
            stalls = [stall for stall in canteen["stalls"] if any(term in " ".join([stall["name"], stall["food_type"], *stall["common_items"]]).lower() for term in [needle] if term)]
            if not stalls and any(generic in needle for generic in ("吃什么", "有什么吃", "菜品", "档口")):
                stalls = canteen["stalls"]
            if stalls:
                matches.append({**canteen, "stalls": stalls})
        return self._ok("search_food", matches, "没有可靠的当日菜单；结果仅是最近核验档口或常见餐品", sources=result.sources, verification={"today_menu_available": False})

    def filter_canteens_by_opening_hours(self, **_: Any) -> ToolResponse:
        result = self.list_canteens()
        result.tool_name = "filter_canteens_by_opening_hours"
        result.data = [row for row in result.data if row["opening_hours"]]
        result.summary = "仅返回有营业时间资料的饭堂；文本资料不能证明当前正在营业"
        result.verification["realtime"] = False
        return result

    def calculate_canteen_freshness(self, canteen_id: str = "", **_: Any) -> ToolResponse:
        row = self.db.get(Canteen, canteen_id)
        if not row or row.campus_id != self.campus_id:
            return ToolResponse(tool_name="calculate_canteen_freshness", success=False, error="not_found", summary="饭堂不存在")
        age = (now_china() - row.verified_at).days if row.verified_at else None
        status = "current" if age is not None and age <= 180 else "stale" if age is not None else "needs_verification"
        return self._ok("calculate_canteen_freshness", {"canteen_id": row.id, "verified_at": row.verified_at, "age_days": age, "freshness_status": status}, f"饭堂资料状态：{status}")

    def create_task(self, confirmed: bool = False, **fields: Any) -> ToolResponse:
        if not confirmed:
            return self._confirmation("create_task", "创建任务前需要用户确认", fields)
        allowed = {key: value for key, value in fields.items() if key in {"title", "description", "deadline", "location", "course", "task_type", "materials", "submission_target", "submission_method", "file_naming", "source_text", "source_url"}}
        if not str(allowed.get("title") or "").strip():
            return ToolResponse(tool_name="create_task", success=False, error="invalid_title", summary="任务标题不能为空")
        task = Task(user_id=self.user.id, **allowed)
        self.db.add(task); self.db.flush()
        self.db.add_all([TaskReminder(task_id=task.id, minutes_before=1440), TaskReminder(task_id=task.id, minutes_before=180)])
        self.db.commit(); self.db.refresh(task)
        return self._ok("create_task", _task_data(task), "任务已真实保存", verification={"persisted": True, "confirmed": True})

    def create_tasks(self, tasks: list[dict] | None = None, confirmed: bool = False, **_: Any) -> ToolResponse:
        if not confirmed:
            return self._confirmation("create_tasks", "批量创建任务前需要用户确认", tasks or [])
        created = []
        for fields in tasks or []:
            result = self.create_task(confirmed=True, **fields)
            if not result.success:
                return ToolResponse(tool_name="create_tasks", success=False, error=result.error, summary=result.summary)
            created.append(result.data)
        return self._ok("create_tasks", created, f"已真实保存 {len(created)} 条任务", verification={"persisted": True, "confirmed": True})

    def list_tasks(self, status: str | None = None, **_: Any) -> ToolResponse:
        statement = select(Task).where(Task.user_id == self.user.id)
        if status:
            statement = statement.where(Task.status == status)
        rows = list(self.db.scalars(statement.order_by(Task.deadline.is_(None), Task.deadline)))
        return self._ok("list_tasks", [_task_data(row) for row in rows], f"共有 {len(rows)} 条任务", verification={"user_id": self.user.id})

    def get_task(self, task_id: str = "", **_: Any) -> ToolResponse:
        row = self._owned_task(task_id)
        return self._ok("get_task", _task_data(row), "已读取任务") if row else ToolResponse(tool_name="get_task", success=False, error="not_found", summary="任务不存在")

    def update_task(self, task_id: str = "", confirmed: bool = False, **changes: Any) -> ToolResponse:
        if not confirmed:
            return self._confirmation("update_task", "修改任务前需要用户确认", changes)
        row = self._owned_task(task_id)
        if not row:
            return ToolResponse(tool_name="update_task", success=False, error="not_found", summary="任务不存在")
        for key, value in changes.items():
            if key in {"title", "description", "deadline", "location", "course", "task_type", "materials", "submission_target", "submission_method", "file_naming", "source_text", "source_url"}:
                setattr(row, key, value)
        self.db.commit(); self.db.refresh(row)
        return self._ok("update_task", _task_data(row), "任务已更新", verification={"persisted": True, "confirmed": True})

    def delete_task(self, task_id: str = "", confirmed: bool = False, **_: Any) -> ToolResponse:
        if not confirmed:
            return self._confirmation("delete_task", "删除任务前需要用户确认", {"task_id": task_id})
        row = self._owned_task(task_id)
        if not row:
            return ToolResponse(tool_name="delete_task", success=False, error="not_found", summary="任务不存在")
        self.db.delete(row); self.db.commit()
        return self._ok("delete_task", {"task_id": task_id}, "任务已删除", verification={"persisted": True, "confirmed": True})

    def complete_task(self, task_id: str = "", confirmed: bool = False, **_: Any) -> ToolResponse:
        return self._set_task_status("complete_task", task_id, "completed", confirmed)

    def reopen_task(self, task_id: str = "", confirmed: bool = False, **_: Any) -> ToolResponse:
        return self._set_task_status("reopen_task", task_id, "pending", confirmed)

    def _set_task_status(self, tool: str, task_id: str, status: str, confirmed: bool) -> ToolResponse:
        if not confirmed:
            return self._confirmation(tool, "修改任务状态前需要用户确认", {"task_id": task_id, "status": status})
        row = self._owned_task(task_id)
        if not row:
            return ToolResponse(tool_name=tool, success=False, error="not_found", summary="任务不存在")
        row.status = status; row.completed_at = utcnow() if status == "completed" else None
        self.db.commit(); self.db.refresh(row)
        return self._ok(tool, _task_data(row), "任务状态已更新", verification={"persisted": True, "confirmed": True})

    def list_overdue_tasks(self, **_: Any) -> ToolResponse:
        rows = list(self.db.scalars(select(Task).where(Task.user_id == self.user.id, Task.status == "pending", Task.deadline < now_china())))
        return self._ok("list_overdue_tasks", [_task_data(row) for row in rows], f"有 {len(rows)} 条逾期任务")

    def list_upcoming_tasks(self, days: int = 7, **_: Any) -> ToolResponse:
        current = now_china(); end = current + timedelta(days=max(1, min(days, 90)))
        rows = list(self.db.scalars(select(Task).where(Task.user_id == self.user.id, Task.status == "pending", Task.deadline >= current, Task.deadline <= end)))
        return self._ok("list_upcoming_tasks", [_task_data(row) for row in rows], f"未来 {days} 天有 {len(rows)} 条任务")

    def extract_tasks_from_notification(self, text: str = "", source_url: str = "", **_: Any) -> ToolResponse:
        drafts, mode, warning = NotificationService().extract(text, source_url)
        data = [draft.model_dump(mode="json") for draft in drafts]
        return self._ok("extract_tasks_from_notification", data, "已生成任务预览，尚未写入数据库" + (f"；{warning}" if warning else ""), verification={"mode": mode, "persisted": False}, action=True)

    def parse_deadline(self, text: str = "", **_: Any) -> ToolResponse:
        parsed = parse_relative_datetime(text, now_china())
        return self._ok("parse_deadline", {"deadline": parsed.value, "requires_confirmation": parsed.requires_confirmation, "explanation": parsed.explanation}, parsed.explanation, action=parsed.requires_confirmation)

    def validate_extracted_tasks(self, tasks: list[dict] | None = None, **_: Any) -> ToolResponse:
        errors = []
        for index, task in enumerate(tasks or []):
            if not str(task.get("title") or "").strip(): errors.append(f"第 {index + 1} 条缺少标题")
            if task.get("needs_confirmation"): errors.append(f"第 {index + 1} 条日期需要确认")
        return self._ok("validate_extracted_tasks", {"valid": not errors, "errors": errors}, "预览校验完成", verification={"valid": not errors}, action=bool(errors))

    def save_confirmed_tasks(self, tasks: list[dict] | None = None, confirmed: bool = False, **_: Any) -> ToolResponse:
        result = self.create_tasks(tasks=tasks, confirmed=confirmed)
        result.tool_name = "save_confirmed_tasks"
        return result

    def generate_task_ics(self, task_id: str = "", **_: Any) -> ToolResponse:
        row = self._owned_task(task_id)
        if not row:
            return ToolResponse(tool_name="generate_task_ics", success=False, error="not_found", summary="任务不存在")
        payload = generate_ics([row], [1440, 180])
        return self._ok("generate_task_ics", {"ics": payload, "task_ids": [row.id]}, "已生成包含两次提醒的 ICS", verification={"generated": True})

    def generate_tasks_ics(self, task_ids: list[str] | None = None, confirmed: bool = False, **_: Any) -> ToolResponse:
        if not confirmed:
            return self._confirmation("generate_tasks_ics", "批量导出日历前需要用户确认", task_ids or [])
        statement = select(Task).where(Task.user_id == self.user.id)
        if task_ids:
            statement = statement.where(Task.id.in_(task_ids))
        rows = list(self.db.scalars(statement))
        payload = generate_ics(rows, [1440, 180])
        return self._ok("generate_tasks_ics", {"ics": payload, "task_ids": [row.id for row in rows]}, f"已生成 {len(rows)} 个日历事件", verification={"generated": True, "confirmed": True})

    def verify_ics(self, ics: str = "", **_: Any) -> ToolResponse:
        try:
            calendar = Calendar.from_ical(ics)
            events = [component for component in calendar.walk() if component.name == "VEVENT"]
            alarms = [component for component in calendar.walk() if component.name == "VALARM"]
        except Exception as exc:
            return ToolResponse(tool_name="verify_ics", success=False, error=type(exc).__name__, summary="ICS 校验失败")
        return self._ok("verify_ics", {"events": len(events), "alarms": len(alarms)}, "ICS 结构有效", verification={"valid": True, "two_alarms_per_event": len(alarms) == len(events) * 2})

    def build_calendar_download(self, task_ids: list[str] | None = None, **_: Any) -> ToolResponse:
        query = "&".join(f"task_ids={quote(task_id)}" for task_id in task_ids or [])
        return self._ok("build_calendar_download", {"url": f"/api/tasks/export/ics{f'?{query}' if query else ''}"}, "已生成本站日历下载地址")

    def search_campus_processes(self, query: str = "", **_: Any) -> ToolResponse:
        statement = select(CampusProcess).options(selectinload(CampusProcess.source)).where(CampusProcess.is_active.is_(True))
        if self.campus_id:
            statement = statement.where(or_(CampusProcess.campus_id == self.campus_id, CampusProcess.campus_id.is_(None)))
        rows = list(self.db.scalars(statement))
        if query:
            tokens = [token for token in re.findall(r"[\u4e00-\u9fff]{2,6}|[a-z0-9]{2,}", query.lower()) if token not in {"怎么", "办理", "流程", "需要"}]
            rows = [row for row in rows if any(token in f"{row.title}{row.category}{row.notes}".lower() for token in tokens)]
        data = [{
            "id": row.id, "campus_id": row.campus_id, "title": row.title, "category": row.category,
            "audience": row.audience, "steps": row.steps, "materials": row.materials, "location": row.location,
            "contact": row.contact, "opening_hours": row.opening_hours, "online_url": row.online_url,
            "notes": row.notes, "verification_status": row.verification_status,
            "verified_at": row.verified_at, "confidence": row.confidence, "data_status": row.data_status,
        } for row in rows]
        sources = [source for row in rows if (source := _source(row.source))]
        return self._ok("search_campus_processes", data, f"找到 {len(rows)} 条办事流程", sources=sources, verification={"campus_id": self.campus_id})

    def get_process_details(self, process_id: str = "", **_: Any) -> ToolResponse:
        result = self.search_campus_processes()
        result.tool_name = "get_process_details"
        result.data = next((row for row in result.data if row["id"] == process_id), None)
        result.success = result.data is not None
        result.summary = "已读取办事流程" if result.success else "办事流程不存在或不属于当前校区"
        return result

    def save_process_as_tasks(self, process_id: str = "", confirmed: bool = False, **_: Any) -> ToolResponse:
        if not confirmed:
            return self._confirmation("save_process_as_tasks", "把办事步骤保存为任务前需要用户确认", {"process_id": process_id})
        details = self.get_process_details(process_id)
        if not details.success:
            return ToolResponse(tool_name="save_process_as_tasks", success=False, error="not_found", summary=details.summary)
        process = details.data
        tasks = [{"title": f"{process['title']} · 第 {index} 步", "description": step.get("text") or step.get("title") or "", "location": process["location"], "task_type": "campus_process_step", "source_url": process["online_url"]} for index, step in enumerate(process["steps"], 1)]
        result = self.create_tasks(tasks=tasks, confirmed=True)
        result.tool_name = "save_process_as_tasks"
        return result

    def search_campus_knowledge(self, query: str = "", **_: Any) -> ToolResponse:
        results = search_knowledge(
            self.db,
            user_id=self.user.id,
            query=query,
            campus_id=self.campus_id,
            limit=8,
        )
        data = [{**item, "id": item["document_id"], "campus_id": self.campus_id, "data_status": "private_or_reviewed"} for item in results]
        sources = [{
            "id": item["document_id"],
            "title": item["title"],
            "url": item["url"],
            "publisher": item["publisher"],
            "source_type": item["source_type"],
            "visibility": item["visibility"],
        } for item in results]
        return self._ok(
            "search_campus_knowledge",
            data,
            f"检索到 {len(data)} 条有来源的知识资料",
            sources=sources,
            verification={"retrieval": "bm25_zh", "user_isolated": True, "low_match_suppressed": True},
        )

    def search_learning_materials(self, query: str = "", **_: Any) -> ToolResponse:
        result = self.search_campus_knowledge(query=query)
        result.tool_name = "search_learning_materials"
        result.data = [row for row in result.data if any(term in f"{row['title']} {row['snippet']}" for term in ("学习", "课程", "考试", "图书"))]
        result.summary = f"检索到 {len(result.data)} 条学习资料"
        return result

    def get_source_details(self, source_id: str = "", **_: Any) -> ToolResponse:
        document = self.db.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.id == source_id,
            KnowledgeDocument.is_active.is_(True),
            or_(KnowledgeDocument.visibility == "public", KnowledgeDocument.owner_user_id == self.user.id),
        ))
        if document:
            data = {
                "id": document.id,
                "title": document.title,
                "content": document.content[:5000],
                "url": document.url,
                "publisher": document.publisher,
                "source_type": document.source_type,
                "visibility": document.visibility,
                "data_status": document.data_status,
                "created_at": document.created_at,
            }
            return self._ok("get_source_details", data, "已读取有权限的知识来源", verification={"user_isolated": True})
        row = self.db.get(Source, source_id)
        data = _source(row)
        return self._ok("get_source_details", data, "已读取来源详情") if data else ToolResponse(tool_name="get_source_details", success=False, error="not_found", summary="来源不存在")

    def import_local_documents(self, confirmed: bool = False, **_: Any) -> ToolResponse:
        del confirmed
        return self._confirmation(
            "import_local_documents",
            "本地文件导入必须由你在知识库导入页明确选择文件；Agent 不会自行扫描电脑或微信数据库。",
            {"action_url": "/knowledge/import", "accepted": ["md", "txt", "html", "mhtml", "pdf", "docx", "json", "csv"]},
        )

    def import_text_content(
        self,
        title: str = "",
        content: str = "",
        publisher: str = "",
        confirmed: bool = False,
        **_: Any,
    ) -> ToolResponse:
        preview = {"title": title[:255], "characters": len(content), "visibility": "private"}
        if not confirmed:
            return self._confirmation("import_text_content", "保存正文到私有知识库前需要用户确认", preview)
        try:
            job = create_import_job(self.db, user_id=self.user.id, source_label="agent-text", total_files=1)
            outcome = import_document(
                self.db,
                user_id=self.user.id,
                title=title,
                content=content,
                source_type="agent_text",
                campus_id=self.campus_id,
                publisher=publisher,
            )
        except KnowledgeImportError as exc:
            return ToolResponse(tool_name="import_text_content", success=False, error="invalid_content", summary=str(exc))
        job.imported_files = int(not outcome.duplicate)
        job.duplicate_files = int(outcome.duplicate)
        finish_import_job(job, errors=[])
        self.db.commit()
        return self._ok(
            "import_text_content",
            {"document_id": outcome.document.id if outcome.document else None, "duplicate": outcome.duplicate},
            "正文已保存到当前用户的私有知识库",
            verification={"persisted": True, "confirmed": True, "visibility": "private"},
        )

    def import_article_url(
        self,
        url: str = "",
        publisher: str = "",
        confirmed: bool = False,
        **_: Any,
    ) -> ToolResponse:
        if not confirmed:
            return self._confirmation("import_article_url", "抓取并保存文章 URL 前需要用户确认", {"url": url, "visibility": "private"})
        try:
            title, content = fetch_article(url, max_bytes=get_settings().max_upload_bytes)
            job = create_import_job(self.db, user_id=self.user.id, source_label="agent-url", total_files=1)
            outcome = import_document(
                self.db,
                user_id=self.user.id,
                title=title,
                content=content,
                source_type="agent_url",
                campus_id=self.campus_id,
                publisher=publisher,
                url=url,
            )
        except (KnowledgeImportError, httpx.HTTPError) as exc:
            return ToolResponse(tool_name="import_article_url", success=False, error=type(exc).__name__, summary="文章导入失败；未保存不完整内容")
        job.imported_files = int(not outcome.duplicate)
        job.duplicate_files = int(outcome.duplicate)
        finish_import_job(job, errors=[])
        self.db.commit()
        return self._ok(
            "import_article_url",
            {"document_id": outcome.document.id if outcome.document else None, "duplicate": outcome.duplicate},
            "文章已保存到当前用户的私有知识库",
            verification={"persisted": True, "confirmed": True, "visibility": "private"},
        )

    def reindex_documents(self, confirmed: bool = False, **_: Any) -> ToolResponse:
        if not confirmed:
            return self._confirmation("reindex_documents", "重建私有知识检索索引前需要用户确认")
        count = rebuild_knowledge_index(self.db, user_id=self.user.id)
        self.db.commit()
        return self._ok(
            "reindex_documents",
            {"indexed_documents": count},
            f"已重建 {count} 篇私有资料的检索索引",
            verification={"persisted": True, "confirmed": True, "user_isolated": True},
        )

    def get_user_profile(self, **_: Any) -> ToolResponse:
        data = {"id": self.user.id, "nickname": self.user.nickname, "campus_id": self.user.campus_id, "grade": self.user.grade, "major": self.user.major, "preferred_name": self.user.preferred_name, "address_style": self.user.address_style, "preferred_location_id": self.user.preferred_location_id}
        return self._ok("get_user_profile", data, "已读取当前用户公开给 Agent 的个人偏好", verification={"user_id": self.user.id})

    def update_user_preference(self, confirmed: bool = False, **changes: Any) -> ToolResponse:
        if not confirmed:
            return self._confirmation("update_user_preference", "修改用户偏好前需要用户确认", changes)
        preference = self.user.preference or UserPreference(user_id=self.user.id)
        for key in ("preferred_name", "address_style", "preferred_location_id", "accessibility_notes"):
            if key in changes:
                setattr(preference, key, changes[key])
        if not self.user.preference: self.db.add(preference)
        self.db.commit()
        return self._ok("update_user_preference", {"preferred_name": preference.preferred_name, "address_style": preference.address_style, "preferred_location_id": preference.preferred_location_id}, "用户偏好已保存", verification={"persisted": True, "confirmed": True})

    def get_preferred_address(self, **_: Any) -> ToolResponse:
        from app.agents.persona import preferred_address
        return self._ok("get_preferred_address", {"address": preferred_address(self.user), "preferred_location_id": self.user.preferred_location_id}, "已读取称呼和常用地点偏好")
