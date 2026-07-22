import streamlit as st
from dotenv import load_dotenv
import os
import json
import base64

AVATAR_URL = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=pixel%20art%20anime%20girl%20with%20black%20ponytail%20hair%20brown%20eyes%20school%20uniform%20beige%20vest%20white%20background%20cute%20style&image_size=square_hd"

CAMPUSES = {
    "校本部": {"icon": "🏫", "location": "广州市天河区", "page": "pages/1_校本部.py"},
    "肇庆校区": {"icon": "🌳", "location": "肇庆市端州区", "page": "pages/2_肇庆校区.py"},
    "清远校区": {"icon": "✨", "location": "清远市清城区", "page": "pages/3_清远校区.py"}
}

GRADES = ["2026级", "2025级", "2024级", "2023级", "其他"]

def initialize_session_state():
    if "user_campus" not in st.session_state:
        st.session_state.user_campus = ""
    if "user_gender" not in st.session_state:
        st.session_state.user_gender = ""
    if "user_grade" not in st.session_state:
        st.session_state.user_grade = ""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_mode" not in st.session_state:
        st.session_state.current_mode = "干活模式"
    if "knowledge_base" not in st.session_state:
        st.session_state.knowledge_base = None
    if "last_tool_result" not in st.session_state:
        st.session_state.last_tool_result = None

def get_deepseek_api_key():
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    return api_key

def add_pwa_support():
    manifest = {
        "name": "广金万事屋",
        "short_name": "广金万事屋",
        "description": "专为广东金融学院学生打造的智能助手",
        "start_url": ".",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#e74c3c",
        "orientation": "portrait",
        "icons": [
            {"src": AVATAR_URL, "sizes": "192x192", "type": "image/png"},
            {"src": AVATAR_URL, "sizes": "512x512", "type": "image/png"}
        ]
    }
    manifest_str = json.dumps(manifest)
    manifest_b64 = base64.b64encode(manifest_str.encode()).decode('utf-8')
    st.markdown(f"""
    <link rel="manifest" href="data:application/json;base64,{manifest_b64}">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="广金万事屋">
    <link rel="apple-touch-icon" href="{AVATAR_URL}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <link rel="shortcut icon" href="{AVATAR_URL}" type="image/png">
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(
        page_title="广金万事屋师兄",
        page_icon=AVATAR_URL,
        layout="centered"
    )
    
    add_pwa_support()
    initialize_session_state()
    
    st.title("🎓 广金万事屋师兄")
    st.markdown("专为广东金融学院学生打造的智能助手")
    
    st.markdown("---")
    
    st.subheader("📝 填写个人信息")
    
    col1, col2 = st.columns(2)
    
    with col1:
        campus = st.selectbox(
            "🏛️ 选择校区",
            [""] + list(CAMPUSES.keys()),
            index=list(CAMPUSES.keys()).index(st.session_state.user_campus) + 1 if st.session_state.user_campus else 0,
            placeholder="请选择你的校区"
        )
    
    with col2:
        gender = st.selectbox(
            "👤 选择性别",
            ["", "男", "女"],
            index=[0, 1, 2][["", "男", "女"].index(st.session_state.user_gender)] if st.session_state.user_gender else 0,
            placeholder="请选择你的性别"
        )
    
    grade = st.selectbox(
        "🎓 选择年级",
        [""] + GRADES,
        index=GRADES.index(st.session_state.user_grade) + 1 if st.session_state.user_grade else 0,
        placeholder="请选择你的年级"
    )
    
    api_key_input = st.text_input(
        "🔑 DeepSeek API Key（选填）",
        value=get_deepseek_api_key(),
        type="password",
        placeholder="输入API Key以获得更好的AI体验"
    )
    
    if api_key_input:
        os.environ["DEEPSEEK_API_KEY"] = api_key_input
        os.environ["DEEPSEEK_BASE_URL"] = "https://api.deepseek.com/v1"
    
    st.markdown("---")
    
    can_proceed = campus and gender and grade
    
    if can_proceed:
        if st.button("🚀 进入万事屋", use_container_width=True, type="primary"):
            st.session_state.user_campus = campus
            st.session_state.user_gender = gender
            st.session_state.user_grade = grade
            st.session_state.messages = []
            st.switch_page(CAMPUSES[campus]["page"])
    else:
        st.button("🚀 进入万事屋", use_container_width=True, disabled=True)
        missing_fields = []
        if not campus:
            missing_fields.append("校区")
        if not gender:
            missing_fields.append("性别")
        if not grade:
            missing_fields.append("年级")
        st.warning(f"请先填写：{', '.join(missing_fields)}")
    
    st.markdown("---")
    
    if campus:
        st.info(f"🏫 **{CAMPUSES[campus]['icon']} {campus}** - {CAMPUSES[campus]['location']}")
    
    st.markdown("""
    **关于广金万事屋：**
    
    🎯 **干活模式**：处理班群通知生成日历，解析消费记录生成账单
    🗺️ **生活向导**：查询校园路线、服务电话、实用建议
    📰 **校园资讯**：获取广金最新通知和动态
    
    选择你的校区后，万事屋师兄会为你提供个性化的校园服务！
    """)

if __name__ == "__main__":
    main()