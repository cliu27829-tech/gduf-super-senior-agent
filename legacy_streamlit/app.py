"""广金大师兄 Streamlit entry page."""

from __future__ import annotations

import uuid

import streamlit as st

from config import get_deepseek_api_key
from core.models import CAMPUSES
from core.time_service import current_year_china, format_current_time_prompt


AVATAR_PATH = "static/avatar.png"
CAMPUS_PAGES = {
    "广州校本部": "pages/1_校本部.py",
    "肇庆校区": "pages/2_肇庆校区.py",
    "清远校区": "pages/3_清远校区.py",
}


def initialize_session_state() -> None:
    defaults = {
        "user_id": f"session-{uuid.uuid4()}",
        "user_campus": "",
        "user_grade": "",
        "deepseek_api_key": get_deepseek_api_key(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def main() -> None:
    st.set_page_config(page_title="广金大师兄", page_icon="🎓", layout="centered")
    initialize_session_state()

    st.title("🎓 广金大师兄")
    st.caption("广东金融学院校园信息执行与位置服务 Agent")
    st.info(format_current_time_prompt())

    st.markdown(
        """
        - 把班群通知转成可确认、可追踪的待办与中国时区日历
        - 按校区查询饭堂、教学楼、宿舍与生活服务地点
        - 每条地点信息显示来源、核验时间、可信度和过期警告
        """
    )

    campus = st.selectbox(
        "选择校区",
        [""] + list(CAMPUSES),
        index=([""] + list(CAMPUSES)).index(st.session_state.user_campus),
        placeholder="请选择校区",
    )
    grade = st.text_input(
        "年级（选填）",
        value=st.session_state.user_grade,
        placeholder=f"例如：{current_year_china()}级；不填也可以使用",
    )
    api_key = st.text_input(
        "DeepSeek API Key（选填，仅保存在当前会话）",
        value=st.session_state.deepseek_api_key,
        type="password",
        help="没有 Key 也可使用地图、任务和规则提取功能。",
    )
    st.session_state.user_campus = campus
    st.session_state.user_grade = grade
    st.session_state.deepseek_api_key = api_key

    if st.button("进入校区 Agent", type="primary", width="stretch", disabled=not campus):
        st.switch_page(CAMPUS_PAGES[campus])

    col1, col2, col3 = st.columns(3)
    with col1:
        st.page_link("pages/4_校园地图.py", label="🗺️ 校园地图", width="stretch")
    with col2:
        st.page_link("pages/6_任务中心.py", label="✅ 任务中心", width="stretch")
    with col3:
        st.page_link("pages/5_数据管理.py", label="🛠️ 数据管理", width="stretch")

    st.divider()
    st.warning(
        "当前内置地点包含历史资料与演示占位数据。带‘待核验/历史’标记的内容不代表当前营业、今日菜单或精确 GPS。"
    )


if __name__ == "__main__":
    main()
