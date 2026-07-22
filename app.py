import streamlit as st
from dotenv import load_dotenv
import os
import json

from tools.ics_tool import extract_tasks_from_text, generate_ics_file
from tools.csv_tool import parse_expenses_from_text, generate_csv_file, generate_markdown_table
from rag.knowledge_base import CampusKnowledgeBase

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

def initialize_session_state():
    """
    初始化会话状态
    """
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "current_mode" not in st.session_state:
        st.session_state.current_mode = "干活模式"
    
    if "knowledge_base" not in st.session_state:
        st.session_state.knowledge_base = None
    
    if "agent_executor" not in st.session_state:
        st.session_state.agent_executor = None
    
    if "last_tool_result" not in st.session_state:
        st.session_state.last_tool_result = None

def get_deepseek_api_key():
    """
    获取DeepSeek API密钥
    """
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    
    if not api_key:
        api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    
    return api_key

def save_tool_result(result):
    """
    保存工具执行结果到会话状态
    """
    st.session_state.last_tool_result = result

@tool
def generate_ics_calendar(text: str) -> str:
    """
    根据班群通知文本生成ICS日历文件
    输入：包含任务和截止时间的通知文本
    输出：任务列表的描述信息
    """
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
    """
    解析消费记录文本并生成CSV文件
    输入：包含消费记录的文本
    输出：消费统计描述信息
    """
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

def create_agent(api_key):
    """
    创建LangChain Agent，具备工具调用能力（使用DeepSeek API）
    """
    llm = ChatOpenAI(
        temperature=0,
        model="deepseek-chat",
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    )
    
    tools = [generate_ics_calendar, parse_expense_text]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是广金万事屋师兄，一个具备工具调用能力的AI助手。
        
        你有以下工具可用：
        1. generate_ics_calendar: 根据班群通知文本提取任务信息并生成日历文件。当用户输入包含任务名称、截止时间、地点等信息的通知文本时调用此工具。
        2. parse_expense_text: 解析消费记录文本并生成CSV文件和统计表格。当用户输入包含消费日期、金额、描述等信息的文本时调用此工具。
        
        请根据用户的需求，选择合适的工具进行调用。
        如果用户的问题不属于上述两类，直接回答，不需要调用工具。
        
        回答时保持老学长的口吻，靠谱、不废话。"""),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)

def handle_task_mode(user_input, api_key):
    """
    使用LangChain Agent处理干活模式的用户输入
    """
    st.session_state.last_tool_result = None
    
    if not st.session_state.agent_executor:
        st.session_state.agent_executor = create_agent(api_key)
    
    with st.status("🧠 万事屋师兄正在思考...", expanded=True) as status:
        st.write("正在分析你的需求...")
        
        try:
            result = st.session_state.agent_executor.invoke({
                "input": user_input,
                "chat_history": []
            })
            
            output = result.get("output", "")
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
            
            return output
        
        except Exception as e:
            status.update(label="处理失败", state="error")
            return f"处理过程中出现问题：{str(e)}"

def handle_rag_mode(user_input, api_key):
    """
    处理生活向导模式的用户输入
    """
    if not st.session_state.knowledge_base:
        with st.spinner("正在初始化知识库..."):
            st.session_state.knowledge_base = CampusKnowledgeBase(api_key)
            st.session_state.knowledge_base.setup_qa_chain()
    
    with st.spinner("正在检索知识库..."):
        answer = st.session_state.knowledge_base.query(user_input)
    
    return answer

def add_pwa_support():
    """
    添加 PWA 支持，使应用可以被添加到手机主屏幕
    """
    st.markdown("""
    <link rel="manifest" href="https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=manifest%20json%20for%20university%20app&image_size=square">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="广金万事屋">
    <link rel="apple-touch-icon" href="https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Guangdong%20University%20of%20Finance%20school%20emblem%20red%20circle%20golden%20logo%20minimalist&image_size=square_hd">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    """, unsafe_allow_html=True)

def main():
    """
    主应用入口
    """
    st.set_page_config(
        page_title="广金万事屋师兄",
        page_icon="🎓",
        layout="centered"
    )
    
    add_pwa_support()
    initialize_session_state()
    
    st.title("🎓 广金万事屋师兄")
    st.markdown("专为广东金融学院学生打造的智能助手")
    
    with st.sidebar:
        st.header("模式切换")
        mode = st.radio(
            "选择工作模式",
            ["干活模式", "生活向导模式"],
            index=0 if st.session_state.current_mode == "干活模式" else 1
        )
        
        if mode != st.session_state.current_mode:
            st.session_state.current_mode = mode
            st.session_state.messages = []
            st.session_state.agent_executor = None
            st.rerun()
        
        st.divider()
        
        if st.session_state.current_mode == "干活模式":
            st.info("**干活模式**：处理班群通知生成日历，解析消费记录生成账单")
            st.markdown("""
            📅 **DDL收割机**：输入班群通知，自动提取任务和截止时间，生成日历文件
            📊 **账单流水**：输入消费记录，自动分类汇总，生成表格和CSV
            """)
        else:
            st.info("**生活向导模式**：基于广金知识库回答校园问题")
            st.markdown("""
            🗺️ **路线查询**：问我校园路线
            📞 **服务查询**：问我报修电话等生活信息
            💡 **避坑建议**：获取学长的实用建议
            """)
        
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
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"], avatar=message.get("avatar")):
            st.markdown(message["content"])
    
    if prompt := st.chat_input("请输入你的问题..."):
        api_key = api_key_input if api_key_input else get_deepseek_api_key()
        
        if not api_key:
            st.error("请先在侧边栏输入你的DeepSeek API Key！")
            return
        
        os.environ["DEEPSEEK_API_KEY"] = api_key
        os.environ["DEEPSEEK_BASE_URL"] = "https://api.deepseek.com/v1"
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant", avatar="🧑‍🎓"):
            if st.session_state.current_mode == "干活模式":
                response = handle_task_mode(prompt, api_key)
            else:
                response = handle_rag_mode(prompt, api_key)
            
            st.markdown(response)
        
        st.session_state.messages.append({"role": "assistant", "content": response, "avatar": "🧑‍🎓"})

if __name__ == "__main__":
    main()