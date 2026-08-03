from core.models import CampusLocation
from core.orchestrator import Orchestrator
from services.location_service import LocationService
from services.notification_service import NotificationService
from services.task_service import TaskService


def build_orchestrator(tmp_path):
    locations = LocationService(tmp_path / "agent.db", tmp_path / "none", auto_seed=False)
    for location_id, name, campus in (
        ("gz-canteen", "广州饭堂", "广州校本部"),
        ("zq-canteen", "肇庆饭堂", "肇庆校区"),
    ):
        locations.save_location(
            CampusLocation(
                id=location_id,
                name=name,
                aliases=[],
                campus=campus,
                category="canteen",
                map_x=0.5,
                map_y=0.5,
                verified_at=None,
                data_status="historical_seed",
            )
        )
    tasks = TaskService(locations.database.path)
    return Orchestrator(locations, tasks, NotificationService()), tasks


def test_required_intent_routes(tmp_path):
    agent, _ = build_orchestrator(tmp_path)
    cases = {
        "广州校本部有哪些饭堂": "canteen_search",
        "饭堂有什么吃的": "canteen_search",
        "我想吃面": "food_search",
        "哪里可以买早餐": "food_search",
        "附近有快递站吗": "nearby_location_search",
        "从宿舍到图书馆怎么走": "campus_navigation",
        "数据最后更新和核验时间": "campus_data_freshness",
        "这周有什么没完成": "task_management",
        "我还有什么任务": "task_management",
        "校园卡丢了怎么补办": "campus_process",
    }
    for text, expected in cases.items():
        assert agent.classify_intent(text, "广州校本部").intent == expected
    assert agent.classify_intent("你好", "广州校本部").intent == "general_chat"


def test_canteen_answer_is_campus_scoped_and_warns_about_stale_data(tmp_path):
    agent, _ = build_orchestrator(tmp_path)
    response = agent.handle("有哪些饭堂", "u1", campus_hint="广州校本部")
    assert response.intent == "canteen_search"
    assert "广州饭堂" in response.content
    assert "肇庆饭堂" not in response.content
    assert "历史资料或待核验" in response.content
    assert "list_canteens" in response.tool_plan


def test_food_answer_does_not_invent_unverified_stalls(tmp_path):
    agent, _ = build_orchestrator(tmp_path)
    response = agent.handle("我想吃面", "u1", campus_hint="广州校本部")
    assert response.data == []
    assert "不会根据旧文章编造" in response.content


def test_notification_route_only_previews_and_does_not_create_task(tmp_path):
    agent, tasks = build_orchestrator(tmp_path)
    response = agent.handle(
        "通知：请于9月3日下午5点前提交材料：申请表、学生证",
        "u1",
        campus_hint="广州校本部",
    )
    assert response.intent == "notification_to_tasks"
    assert response.requires_confirmation is True
    assert response.data[0]["deadline"].endswith("17:00:00+08:00")
    assert tasks.list_tasks("u1") == []
