import streamlit as st
import os

from tools.ics_tool import extract_tasks_from_text, generate_ics_file
from tools.csv_tool import parse_expenses_from_text, generate_csv_file, generate_markdown_table
from tools.wechat_tool import crawl_gduf_wechat, generate_articles_summary
from rag.knowledge_base import CampusKnowledgeBase

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

AVATAR_URL = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=pixel%20art%20anime%20girl%20with%20black%20ponytail%20hair%20brown%20eyes%20school%20uniform%20beige%20vest%20white%20background%20cute%20style&image_size=square_hd"

def save_tool_result(result):
    st.session_state.last_tool_result = result

@tool
def generate_ics_calendar(text: str) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    tasks = extract_tasks_from_text(text, api_key)
    if not tasks:
        save_tool_result({"success": False, "type": "ics", "message": "未提取到任务信息"})
        return "未从文本中提取到任务信息"
    filename = "gduf_tasks.ics"
    generate_ics_file(tasks, filename)
    save_tool_result({
        "success": True,
        "type": "ics",
        "filename": filename,
        "tasks": tasks
    })
    return f"成功提取 {len(tasks)} 个任务并生成日历文件"

@tool
def parse_expense_text(text: str) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    expenses = parse_expenses_from_text(text, api_key)
    if not expenses:
        save_tool_result({"success": False, "type": "expense", "message": "未提取到消费记录"})
        return "未从文本中提取到消费记录"
    filename = "gduf_expenses.csv"
    generate_csv_file(expenses, filename)
    markdown_table = generate_markdown_table(expenses)
    save_tool_result({
        "success": True,
        "type": "expense",
        "filename": filename,
        "expenses": expenses,
        "markdown_table": markdown_table
    })
    total = sum(e["amount"] for e in expenses)
    return f"成功解析 {len(expenses)} 条消费记录，总计 {total:.2f} 元"

@tool
def search_wechat_articles(query: str) -> str:
    articles = crawl_gduf_wechat()
    if not articles:
        return "暂未搜索到相关公众号文章"
    save_tool_result({
        "success": True,
        "type": "wechat",
        "articles": articles
    })
    return generate_articles_summary(articles)

def handle_task_mode(user_input, api_key):
    st.session_state.last_tool_result = None
    llm = ChatOpenAI(
        temperature=0,
        model="deepseek-chat",
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    )
    tools = [generate_ics_calendar, parse_expense_text, search_wechat_articles]
    llm_with_tools = llm.bind_tools(tools)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""你是广金万事屋师兄（清远校区版），一个具备工具调用能力的AI助手。
        
        用户信息：
        - 校区：清远校区（清远市清城区）
        - 性别：{st.session_state.user_gender if st.session_state.user_gender else '未知'}
        - 年级：{st.session_state.user_grade if st.session_state.user_grade else '未知'}
        
        你有以下工具可用：
        1. generate_ics_calendar: 根据班群通知文本提取任务信息并生成日历文件
        2. parse_expense_text: 解析消费记录文本并生成CSV文件和统计表格
        3. search_wechat_articles: 搜索微信公众号文章获取广金最新资讯
        
        回答时保持老学长的口吻，靠谱、不废话。涉及校园问题时优先考虑清远校区的情况。"""),
        ("human", "{input}"),
    ])
    
    agent_chain = prompt | llm_with_tools | StrOutputParser()
    
    with st.status("🧠 万事屋师兄正在思考...", expanded=True) as status:
        st.write("正在分析你的需求...")
        try:
            result = agent_chain.invoke({"input": user_input})
            tool_result = st.session_state.last_tool_result
            
            if tool_result and tool_result.get("success"):
                filename = tool_result.get("filename", "")
                
                if tool_result["type"] == "ics":
                    tasks = tool_result["tasks"]
                    task_list = "\n".join([f"- {t['name']}（截止：{t['deadline']}）" for t in tasks])
                    with open(filename, "rb") as f:
                        file_bytes = f.read()
                    st.write("正在生成日历文件...")
                    status.update(label="任务完成", state="complete", expanded=False)
                    st.download_button(
                        label="📥 下载日历文件 (.ics)",
                        data=file_bytes,
                        file_name=filename,
                        mime="text/calendar"
                    )
                    return f"已帮你提取 {len(tasks)} 个任务：\n\n{task_list}\n\n点击上方按钮下载日历文件！"
                
                elif tool_result["type"] == "expense":
                    st.write("正在生成账单表格...")
                    status.update(label="任务完成", state="complete", expanded=False)
                    st.markdown(tool_result.get("markdown_table", ""))
                    with open(filename, "rb") as f:
                        file_bytes = f.read()
                    st.download_button(
                        label="📥 导出CSV文件",
                        data=file_bytes,
                        file_name=filename,
                        mime="text/csv"
                    )
                    return "消费记录已整理完成！以上是你的账单汇总，请点击按钮导出CSV文件。"
                
                elif tool_result["type"] == "wechat":
                    st.write("正在整理公众号文章...")
                    status.update(label="任务完成", state="complete", expanded=False)
                    articles = tool_result.get("articles", [])
                    for article in articles[:3]:
                        with st.expander(f"📢 {article['title']}"):
                            st.markdown(f"**日期**：{article['date']}")
                            st.markdown(f"**摘要**：{article['summary']}")
                            if article['link']:
                                st.markdown(f"**原文链接**：[{article['link']}]({article['link']})")
            
            return result
        
        except Exception as e:
            status.update(label="处理失败", state="error")
            return f"处理过程中出现问题：{str(e)}"

def handle_rag_mode(user_input, api_key):
    if not st.session_state.knowledge_base:
        with st.spinner("正在初始化知识库..."):
            st.session_state.knowledge_base = CampusKnowledgeBase(api_key)
            st.session_state.knowledge_base.setup_qa_chain()
    with st.spinner("正在检索知识库..."):
        answer = st.session_state.knowledge_base.query(user_input)
    return answer

def main():
    st.set_page_config(
        page_title="清远校区 - 广金万事屋",
        page_icon="✨",
        layout="centered"
    )
    
    if "user_campus" not in st.session_state or st.session_state.user_campus != "清远校区":
        st.warning("请先在首页选择清远校区！")
        if st.button("返回首页选择校区"):
            st.switch_page("app.py")
        return
    
    st.title("✨ 清远校区 - 广金万事屋师兄")
    st.markdown("📍 清远市清城区 | 新校区，现代化设施")
    
    with st.sidebar:
        st.header("当前校区")
        st.info("✨ **清远校区**")
        st.markdown("📍 清远市清城区")
        
        st.divider()
        
        st.header("个人信息")
        st.markdown(f"- 校区：{st.session_state.user_campus}")
        st.markdown(f"- 性别：{st.session_state.user_gender if st.session_state.user_gender else '未设置'}")
        st.markdown(f"- 年级：{st.session_state.user_grade if st.session_state.user_grade else '未设置'}")
        
        st.divider()
        
        st.header("模式切换")
        mode = st.radio(
            "选择工作模式",
            ["干活模式", "生活向导模式"],
            index=0 if st.session_state.current_mode == "干活模式" else 1
        )
        
        if mode != st.session_state.current_mode:
            st.session_state.current_mode = mode
            st.session_state.messages = []
            st.rerun()
        
        st.divider()
        
        if st.session_state.current_mode == "干活模式":
            st.info("**干活模式**：处理班群通知生成日历，解析消费记录生成账单，获取公众号资讯")
            st.markdown("""
            📅 **DDL收割机**：输入班群通知，自动提取任务和截止时间，生成日历文件
            📊 **账单流水**：输入消费记录，自动分类汇总，生成表格和CSV
            📰 **校园资讯**：获取广金相关公众号最新文章和通知
            """)
        else:
            st.info("**生活向导模式**：基于广金知识库回答校园问题")
            st.markdown("""
            🗺️ **路线查询**：问我校园路线（清远校区）
            📞 **服务查询**：问我报修电话等生活信息
            💡 **避坑建议**：获取学长的实用建议
            """)
        
        st.divider()
        
        api_key_input = st.text_input(
            "DeepSeek API Key",
            value=os.environ.get("DEEPSEEK_API_KEY", ""),
            type="password",
            placeholder="请输入你的DeepSeek API Key"
        )
        
        if api_key_input:
            os.environ["DEEPSEEK_API_KEY"] = api_key_input
            os.environ["DEEPSEEK_BASE_URL"] = "https://api.deepseek.com/v1"
    
    for message in st.session_state.messages:
        avatar = AVATAR_URL if message["role"] == "assistant" else None
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])
    
    if prompt := st.chat_input("请输入你的问题..."):
        api_key = api_key_input if api_key_input else os.environ.get("DEEPSEEK_API_KEY", "")
        
        if not api_key:
            st.error("请先在侧边栏输入你的DeepSeek API Key！")
            return
        
        os.environ["DEEPSEEK_API_KEY"] = api_key
        os.environ["DEEPSEEK_BASE_URL"] = "https://api.deepseek.com/v1"
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant", avatar=AVATAR_URL):
            if st.session_state.current_mode == "干活模式":
                response = handle_task_mode(prompt, api_key)
            else:
                response = handle_rag_mode(prompt, api_key)
            st.markdown(response)
        
        st.session_state.messages.append({"role": "assistant", "content": response, "avatar": AVATAR_URL})

if __name__ == "__main__":
    main()