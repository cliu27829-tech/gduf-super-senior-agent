"""Shared UI for all three campus pages."""

from __future__ import annotations

from dataclasses import asdict
import uuid

import streamlit as st

from config import get_deepseek_api_key
from core.orchestrator import Orchestrator
from core.time_service import format_current_time_prompt
from services.location_service import LocationService
from services.notification_service import NotificationDraft, NotificationService
from services.task_service import TaskService
from tools.ics_tool import generate_ics_bytes
from ui.navigation import safe_page_link


def _ensure_session(campus: str) -> None:
    defaults = {
        "user_id": f"session-{uuid.uuid4()}",
        "user_campus": campus,
        "user_grade": "",
        "deepseek_api_key": get_deepseek_api_key(),
        f"messages_{campus}": [],
        f"drafts_{campus}": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_resource
def _services():
    location = LocationService()
    tasks = TaskService(location.database.path)
    notifications = NotificationService()
    return location, tasks, notifications, Orchestrator(location, tasks, notifications)


def _render_chat(campus: str, orchestrator: Orchestrator) -> None:
    message_key = f"messages_{campus}"
    for message in st.session_state[message_key]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("tool_plan"):
                st.caption("工具计划：" + " → ".join(message["tool_plan"]))
    prompt = st.chat_input("例如：广州校本部有哪些饭堂？")
    if not prompt:
        return
    st.session_state[message_key].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    response = orchestrator.handle(
        prompt,
        user_id=st.session_state.user_id,
        campus_hint=campus,
        api_key=st.session_state.deepseek_api_key,
    )
    with st.chat_message("assistant"):
        st.markdown(response.content)
        if response.tool_plan:
            st.caption("工具计划：" + " → ".join(response.tool_plan))
        st.caption(f"数据处理时间：{response.updated_at}")
    st.session_state[message_key].append(
        {
            "role": "assistant",
            "content": response.content,
            "tool_plan": response.tool_plan,
        }
    )


def _render_notification(campus: str, notifications: NotificationService, tasks: TaskService) -> None:
    st.subheader("通知 → 待办草稿")
    st.caption("先提取和预览；只有点击确认保存才会写入任务数据库。")
    source_url = st.text_input("通知来源链接（选填）", key=f"source_url_{campus}")
    text = st.text_area(
        "粘贴班群通知",
        height=180,
        key=f"notification_text_{campus}",
        placeholder="例：请于9月3日下午5点前提交申请表，材料：申请表、学生证；提交方式：发送给班长。",
    )
    draft_key = f"drafts_{campus}"
    if st.button("提取通知", key=f"extract_{campus}", disabled=not text.strip()):
        extracted = notifications.extract(
            text,
            api_key=st.session_state.deepseek_api_key,
            source_url=source_url,
        )
        st.session_state[draft_key] = [item.to_dict() for item in extracted]

    drafts = [NotificationDraft(**item) for item in st.session_state[draft_key]]
    for index, draft in enumerate(drafts, 1):
        with st.expander(f"草稿 {index}：{draft.title}", expanded=True):
            st.write(f"截止：{draft.deadline or '未识别'}")
            st.write(f"地点：{draft.location or '未提及'}")
            st.write(f"材料：{'、'.join(draft.materials) or '未提及'}")
            st.write(f"提交方式：{draft.submission_method or '未提及'}")
            st.write(f"日期说明：{draft.date_explanation}")
            if draft.needs_confirmation:
                st.warning("日期推断存在风险，必须人工确认。")

    if drafts:
        confirmed = st.checkbox("我已核对任务名称、年份、截止时间和提交方式", key=f"confirm_{campus}")
        if st.button("确认并保存任务", type="primary", disabled=not confirmed, key=f"save_{campus}"):
            created = tasks.create_from_drafts(st.session_state.user_id, drafts, confirmed=True)
            st.success(f"已保存 {len(created)} 个任务。")
            payload = [item.to_dict() for item in created]
            st.download_button(
                "下载 ICS 日历",
                data=generate_ics_bytes(payload),
                file_name=f"gduf-tasks-{uuid.uuid4().hex[:8]}.ics",
                mime="text/calendar",
                key=f"download_{campus}",
            )


def _render_tasks(tasks: TaskService) -> None:
    st.subheader("当前会话任务")
    items = tasks.list_tasks(st.session_state.user_id)
    if not items:
        st.info("还没有任务。")
        return
    for task in items:
        col1, col2 = st.columns([4, 1])
        with col1:
            marker = "✅" if task.status == "completed" else "⏳"
            st.markdown(f"{marker} **{task.title}**")
            st.caption(f"截止：{task.deadline or '未设置'}｜地点：{task.location or '未提及'}")
        with col2:
            if task.status == "pending" and st.button("完成", key=f"complete_{task.id}"):
                tasks.complete_task(task.id, st.session_state.user_id)
                st.rerun()


def render_campus_page(campus: str, icon: str) -> None:
    st.set_page_config(page_title=f"{campus} - 广金大师兄", page_icon=icon, layout="wide")
    _ensure_session(campus)
    if st.session_state.user_campus and st.session_state.user_campus != campus:
        st.warning(f"当前会话选择的是 {st.session_state.user_campus}；本页只查询 {campus} 数据。")
    st.session_state.user_campus = campus
    location, tasks, notifications, orchestrator = _services()

    st.title(f"{icon} {campus} · 广金大师兄")
    st.caption(format_current_time_prompt())
    with st.sidebar:
        st.write(f"当前校区：**{campus}**")
        st.session_state.deepseek_api_key = st.text_input(
            "DeepSeek API Key（选填）",
            value=st.session_state.deepseek_api_key,
            type="password",
            help="仅放在当前 Streamlit 会话，不写入 os.environ。",
        )
        safe_page_link("app.py", "返回首页")
        safe_page_link("pages/4_校园地图.py", "校园地图")
        safe_page_link("pages/6_任务中心.py", "任务中心")
        safe_page_link("pages/5_数据管理.py", "数据管理")

    chat_tab, notification_tab, task_tab, data_tab = st.tabs(
        ["Agent 对话", "通知执行", "任务中心", "数据状态"]
    )
    with chat_tab:
        _render_chat(campus, orchestrator)
    with notification_tab:
        _render_notification(campus, notifications, tasks)
    with task_tab:
        _render_tasks(tasks)
    with data_tab:
        entries = location.search_locations(campus=campus)
        st.metric("地点条目", len(entries))
        stale = [item for item in entries if item.freshness_status != "current"]
        st.metric("待核验/过期", len(stale))
        st.warning("内置数据以历史资料和演示占位为主，请在数据管理页完成实地核验。")
