"""持久化任务列表、周视图、完成状态和 ICS 导出。"""

from __future__ import annotations

import uuid

import streamlit as st

from core.time_service import format_current_time_prompt
from services.task_service import TaskService
from tools.ics_tool import generate_ics_bytes
from ui.navigation import safe_page_link


st.set_page_config(page_title="任务中心 - 广金大师兄", page_icon="✅", layout="wide")

if "user_id" not in st.session_state:
    st.session_state.user_id = f"session-{uuid.uuid4()}"


@st.cache_resource
def get_task_service() -> TaskService:
    return TaskService()


tasks = get_task_service()
st.title("✅ 任务中心")
st.caption(format_current_time_prompt())
st.caption("任务按当前会话用户 ID 隔离；通知只有经确认后才会进入这里。")

with st.sidebar:
    safe_page_link("app.py", "返回首页")
    st.code(st.session_state.user_id, language=None)

all_tasks = tasks.list_tasks(st.session_state.user_id)
week_tasks = tasks.list_week_tasks(st.session_state.user_id)
overdue = tasks.overdue_tasks(st.session_state.user_id)

col_a, col_b, col_c = st.columns(3)
col_a.metric("全部任务", len(all_tasks))
col_b.metric("本周未完成", len(week_tasks))
col_c.metric("已过期", len(overdue))

if all_tasks:
    st.download_button(
        "导出全部任务为 ICS",
        data=generate_ics_bytes([item.to_dict() for item in all_tasks]),
        file_name=f"gduf-tasks-{uuid.uuid4().hex[:8]}.ics",
        mime="text/calendar",
    )

week_tab, pending_tab, completed_tab = st.tabs(["本周", "待办", "已完成"])


def render_task_list(items, allow_reopen: bool = False) -> None:
    if not items:
        st.info("暂无任务。")
        return
    for task in items:
        with st.container(border=True):
            main, action = st.columns([5, 1])
            with main:
                st.markdown(f"### {task.title}")
                st.write(f"**截止：**{task.deadline or '未设置'}")
                st.write(f"**地点：**{task.location or '未提及'}")
                st.write(f"**材料：**{'、'.join(task.materials) or '未提及'}")
                st.write(f"**提交方式：**{task.submission_method or '未提及'}")
                if task.source_url:
                    st.markdown(f"[查看原通知]({task.source_url})")
                if task.needs_confirmation:
                    st.warning("该任务的日期在提取时曾需要人工确认。")
            with action:
                if allow_reopen:
                    if st.button("重新打开", key=f"reopen-{task.id}"):
                        tasks.reopen_task(task.id, st.session_state.user_id)
                        st.rerun()
                elif st.button("标记完成", key=f"complete-{task.id}"):
                    tasks.complete_task(task.id, st.session_state.user_id)
                    st.rerun()


with week_tab:
    render_task_list(week_tasks)
with pending_tab:
    render_task_list([item for item in all_tasks if item.status == "pending"])
with completed_tab:
    render_task_list([item for item in all_tasks if item.status == "completed"], allow_reopen=True)
