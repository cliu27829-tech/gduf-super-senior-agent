import streamlit as st
from dotenv import load_dotenv
import os
import json
import base64

AVATAR_URL = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=pixel%20art%20anime%20girl%20with%20black%20ponytail%20hair%20brown%20eyes%20school%20uniform%20beige%20vest%20white%20background%20cute%20style&image_size=square_hd"

CAMPUSES = {
    "校本部": {
        "name": "校本部",
        "location": "广州市天河区",
        "description": "主校区，设施齐全，交通便利",
        "icon": "🏫",
        "page": "pages/1_校本部.py"
    },
    "肇庆校区": {
        "name": "肇庆校区",
        "location": "肇庆市端州区",
        "description": "风景优美，学习氛围浓厚",
        "icon": "🌳",
        "page": "pages/2_肇庆校区.py"
    },
    "清远校区": {
        "name": "清远校区",
        "location": "清远市清城区",
        "description": "新校区，现代化设施",
        "icon": "✨",
        "page": "pages/3_清远校区.py"
    }
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
    
    with st.sidebar:
        st.header("个人信息设置")
        
        campus = st.selectbox(
            "选择校区",
            [""] + list(CAMPUSES.keys()),
            index=list(CAMPUSES.keys()).index(st.session_state.user_campus) + 1 if st.session_state.user_campus else 0,
            placeholder="请选择你的校区"
        )
        
        if campus != st.session_state.user_campus and campus:
            st.session_state.user_campus = campus
            st.session_state.messages = []
        
        gender = st.selectbox(
            "选择性别",
            ["", "男", "女"],
            index=[0, 1, 2][["", "男", "女"].index(st.session_state.user_gender)] if st.session_state.user_gender else 0,
            placeholder="请选择你的性别"
        )
        st.session_state.user_gender = gender
        
        grade = st.selectbox(
            "选择年级",
            [""] + GRADES,
            index=GRADES.index(st.session_state.user_grade) + 1 if st.session_state.user_grade else 0,
            placeholder="请选择你的年级"
        )
        st.session_state.user_grade = grade
        
        st.divider()
        
        api_key_input = st.text_input(
            "DeepSeek API Key",
            value=get_deepseek_api_key(),
            type="password",
            placeholder="请输入你的DeepSeek API Key"
        )
        
        if api_key_input:
            os.environ["DEEPSEEK_API_KEY"] = api_key_input
            os.environ["DEEPSEEK_BASE_URL"] = "https://api.deepseek.com/v1"
    
    if st.session_state.user_campus:
        campus_page = CAMPUSES[st.session_state.user_campus]["page"]
        try:
            st.switch_page(campus_page)
        except Exception as e:
            st.error(f"跳转失败：{str(e)}")
            st.write("请点击左侧导航栏进入对应校区页面")
        return
    
    st.title("🎓 广金万事屋师兄")
    st.markdown("专为广东金融学院学生打造的智能助手")
    
    st.markdown("---")
    st.subheader("🏛️ 选择你的校区")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🏫 校本部", use_container_width=True):
            st.session_state.user_campus = "校本部"
            st.session_state.messages = []
            st.switch_page("pages/1_校本部.py")
    
    with col2:
        if st.button("🌳 肇庆校区", use_container_width=True):
            st.session_state.user_campus = "肇庆校区"
            st.session_state.messages = []
            st.switch_page("pages/2_肇庆校区.py")
    
    with col3:
        if st.button("✨ 清远校区", use_container_width=True):
            st.session_state.user_campus = "清远校区"
            st.session_state.messages = []
            st.switch_page("pages/3_清远校区.py")
    
    st.markdown("""
    请先选择你的校区，以便获取个性化的校园服务。
    
    **校区介绍：**
    - 🏫 **校本部**：位于广州市天河区，是学校的主校区，拥有最完善的教学设施和浓厚的学术氛围。
    - 🌳 **肇庆校区**：位于肇庆市端州区，环境优美，适合静心学习。
    - ✨ **清远校区**：位于清远市清城区，是新建校区，设施现代化。
    """)

if __name__ == "__main__":
    main()