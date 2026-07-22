import streamlit as st
import os
import openai

from duckduckgo_search import DDGS

from tools.ics_tool import extract_tasks_from_text, generate_ics_file
from tools.csv_tool import parse_expenses_from_text, generate_csv_file, generate_markdown_table
from tools.wechat_tool import crawl_gduf_wechat, generate_articles_summary
from tools.local_knowledge import load_local_knowledge, search_knowledge, build_knowledge_context
from rag.knowledge_base import CampusKnowledgeBase

AVATAR_URL = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=pixel%20art%20anime%20girl%20with%20black%20ponytail%20hair%20brown%20eyes%20school%20uniform%20beige%20vest%20white%20background%20cute%20style&image_size=square_hd"

SYSTEM_PROMPT = f"""你是广东金融学院校本部的刘晨曦师兄。在回答学弟学妹的问题时，请严格遵循以下知识调取优先级：
1. 【优先】：如果传入了《好人师兄》本地资料，必须优先严格基于本地资料精准回答。请通读所有提供的参考资料后再作答，不要只看第一篇就急于回答，确保信息完整；
2. 【补充】：如果本地资料未提及，请结合【联网搜索结果】进行回答，并说明信息来自网络；
3. 【兜底】：如果本地和联网均未搜到，允许使用你的通用知识进行解答，并在回答末尾使用引用框提示：
   '> 💡 晨曦师兄提示：以上信息基于通用常识推断，具体建议向学校官方确认。'
严禁在未尝试其他途径时轻易回答'不知道'。

用户信息：
- 校区：校本部（广州市天河区）
- 性别：{st.session_state.user_gender if 'user_gender' in st.session_state and st.session_state.user_gender else '未知'}
- 年级：{st.session_state.user_grade if 'user_grade' in st.session_state and st.session_state.user_grade else '未知'}

你有以下工具可用：
1. generate_ics_calendar: 根据班群通知文本提取任务信息并生成日历文件
2. parse_expense_text: 解析消费记录文本并生成CSV文件和统计表格
3. search_wechat_articles: 搜索微信公众号文章获取广金最新资讯

人设约束（必须严格遵守）：
- 你的名字是刘晨曦，你是广东金融学院校本部的师兄，常驻校本部。
- 严禁自称是龙洞校区、肇庆校区、清远校区或其他校区的学生。

回答时保持老学长的口吻，靠谱、不废话。涉及校园问题时优先考虑校本部的情况。"""

SEARCH_KEYWORDS = [
    "最新", "2026年", "2026", "当前", "通知", "公告", "新闻", "动态", "现在", "今天", "近期", "最近", "什么时候", "何时",
    "校本部", "广州校区", "多少个学院", "学院", "专业", "在哪", "怎么走", "官网", "指南", "电话", "地址", "路线", "几栋", "几号楼", "哪里", "位置"
]

def save_tool_result(result):
    st.session_state.last_tool_result = result

def need_web_search(user_input):
    for keyword in SEARCH_KEYWORDS:
        if keyword in user_input:
            return True
    return False

def web_search(query, max_results=3):
    search_results = []
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)
            for i, result in enumerate(results, 1):
                search_results.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", "")[:200]
                })
    except Exception as e:
        st.warning(f"网络搜索失败：{str(e)}")
    return search_results

def build_search_context(search_results):
    if not search_results:
        return ""
    context = "\n\n【网络搜索补充信息】\n"
    for i, result in enumerate(search_results, 1):
        context += f"\n{i}. {result['title']}\n"
        context += f"   链接：{result['url']}\n"
        context += f"   摘要：{result['snippet']}\n"
    return context

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

def build_hybrid_context(user_input):
    context_parts = []
    has_local = False
    has_web = False

    # 步骤一：本地知识库检索（取 top 4 提高覆盖率）
    local_docs = load_local_knowledge()
    kb_context = ""
    if local_docs:
        results = search_knowledge(user_input, local_docs, top_n=4)
        if results:
            kb_context = build_knowledge_context(results)
            context_parts.append(f"[本地知识库参考]\n{kb_context}")
            has_local = True

    # 步骤二：判断是否需要网络搜索
    need_web = need_web_search(user_input) or not has_local

    web_context = ""
    if need_web:
        search_query = f"广东金融学院 校本部 {user_input}"
        search_results = web_search(search_query)
        if search_results:
            web_context = build_search_context(search_results)
            context_parts.append(f"[网络实时搜索结果]\n{web_context}")
            has_web = True

    final_context = "\n\n".join(context_parts)
    return final_context, has_local, has_web

def build_messages_for_api(user_input, context=""):
    messages = []
    system_content = SYSTEM_PROMPT

    messages.append({"role": "system", "content": system_content})
    for msg in st.session_state.messages:
        if msg["role"] in ["user", "assistant"]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    if context:
        final_user_input = f"{context}\n\n用户问题：{user_input}"
    else:
        final_user_input = user_input

    messages.append({"role": "user", "content": final_user_input})
    return messages

def call_deepseek_api(messages, api_key, stream=True):
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.7,
        stream=stream
    )
    
    return response

def handle_task_mode(user_input, api_key):
    st.session_state.last_tool_result = None

    # 三层降级混合检索
    with st.status("🔍 正在检索相关信息...", expanded=True) as status:
        st.write("步骤1/3：正在检索本地知识库（好人师兄）...")
        context, has_local, has_web = build_hybrid_context(user_input)
        if has_local:
            st.write("✅ 本地知识库匹配成功")
        else:
            st.write("⚠️  本地知识库未找到高匹配内容")

        if not has_local or need_web_search(user_input):
            st.write("步骤2/3：正在进行网络实时搜索...")
        if has_web:
            st.write("✅ 网络搜索完成")
        elif not has_local:
            st.write("步骤3/3：本地和网络均未找到，将使用通用知识解答")

        status.update(label="检索完成", state="complete", expanded=False)

    messages = build_messages_for_api(user_input, context)
    
    with st.status("🧠 万事屋师兄正在思考...", expanded=True) as status:
        st.write("正在分析你的需求...")
        try:
            response = call_deepseek_api(messages, api_key, stream=False)
            result = response.choices[0].message.content
            
            tool_result = st.session_state.last_tool_result
            
            if "生成日历" in user_input or "DDL" in user_input or "截止时间" in user_input:
                tool_result_data = generate_ics_calendar(user_input)
                if st.session_state.last_tool_result and st.session_state.last_tool_result.get("success"):
                    filename = st.session_state.last_tool_result.get("filename", "")
                    tasks = st.session_state.last_tool_result["tasks"]
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
            
            elif "消费" in user_input or "账单" in user_input or "流水" in user_input:
                tool_result_data = parse_expense_text(user_input)
                if st.session_state.last_tool_result and st.session_state.last_tool_result.get("success"):
                    filename = st.session_state.last_tool_result.get("filename", "")
                    st.write("正在生成账单表格...")
                    status.update(label="任务完成", state="complete", expanded=False)
                    st.markdown(st.session_state.last_tool_result.get("markdown_table", ""))
                    with open(filename, "rb") as f:
                        file_bytes = f.read()
                    st.download_button(
                        label="📥 导出CSV文件",
                        data=file_bytes,
                        file_name=filename,
                        mime="text/csv"
                    )
                    return "消费记录已整理完成！以上是你的账单汇总，请点击按钮导出CSV文件。"
            
            elif "公众号" in user_input or "资讯" in user_input or "新闻" in user_input:
                tool_result_data = search_wechat_articles(user_input)
                if st.session_state.last_tool_result and st.session_state.last_tool_result.get("success"):
                    st.write("正在整理公众号文章...")
                    status.update(label="任务完成", state="complete", expanded=False)
                    articles = st.session_state.last_tool_result.get("articles", [])
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
    # 生活向导模式也使用三层混合检索（与干活模式相同的检索管道）
    with st.status("🔍 正在检索相关信息...", expanded=True) as status:
        st.write("步骤1/3：正在检索本地知识库（好人师兄）...")
        context, has_local, has_web = build_hybrid_context(user_input)
        if has_local:
            st.write("✅ 本地知识库匹配成功")
        else:
            st.write("⚠️  本地知识库未找到高匹配内容")

        if not has_local or need_web_search(user_input):
            st.write("步骤2/3：正在进行网络实时搜索...")
        if has_web:
            st.write("✅ 网络搜索完成")
        elif not has_local:
            st.write("步骤3/3：本地和网络均未找到，将使用通用知识解答")

        status.update(label="检索完成", state="complete", expanded=False)

    messages = build_messages_for_api(user_input, context)

    with st.spinner("🧠 万事屋师兄正在思考..."):
        try:
            response = call_deepseek_api(messages, api_key, stream=False)
            answer = response.choices[0].message.content
            return answer
        except Exception as e:
            return f"处理过程中出现问题：{str(e)}"

def main():
    st.set_page_config(
        page_title="校本部 - 广金万事屋",
        page_icon="🏫",
        layout="centered"
    )
    
    if "user_campus" not in st.session_state or st.session_state.user_campus != "校本部":
        st.warning("请先在首页选择校本部！")
        if st.button("返回首页选择校区"):
            st.switch_page("app.py")
        return
    
    st.title("🏫 校本部 - 广金万事屋师兄")
    st.markdown("📍 广州市天河区 | 主校区专属服务")
    
    with st.sidebar:
        st.header("当前校区")
        st.info("🏫 **校本部**")
        st.markdown("📍 广州市天河区")
        
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
            🗺️ **路线查询**：问我校园路线（校本部）
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
        
        st.divider()

        st.header("数据更新")
        if st.button("🔄 手动更新知识库"):
            with st.spinner("正在从官网获取最新信息..."):
                if st.session_state.knowledge_base:
                    success, message = st.session_state.knowledge_base.manual_update()
                    if success:
                        st.success(message)
                    else:
                        st.error(message)

        st.divider()

        st.header("本地知识库")
        local_docs = load_local_knowledge()
        st.info(f"📚 已加载 {len(local_docs)} 篇文章")
        if st.button("🔄 刷新本地知识库缓存"):
            st.cache_data.clear()
            st.rerun()
    
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
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant", avatar=AVATAR_URL):
            if st.session_state.current_mode == "干活模式":
                response = handle_task_mode(prompt, api_key)
            else:
                response = handle_rag_mode(prompt, api_key)
            st.markdown(response)
        
        st.session_state.messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()