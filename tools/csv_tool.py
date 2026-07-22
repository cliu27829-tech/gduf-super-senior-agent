import csv
import pandas as pd
import os
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import StructuredOutputParser, ResponseSchema

def parse_expenses_from_text(text, openai_api_key):
    """
    使用LLM从消费记录文本中解析并分类汇总
    """
    response_schemas = [
        ResponseSchema(name="expenses", description="消费记录列表，每个记录包含date（日期，格式YYYY-MM-DD）、category（分类：餐饮/交通/购物/娱乐/学习/其他）、description（消费描述）、amount（金额，数字）")
    ]
    
    output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
    format_instructions = output_parser.get_format_instructions()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个消费记录解析助手，请从文本中提取所有消费信息并进行分类。"),
        ("human", "请从以下文本中提取所有消费记录，包括日期、分类、描述和金额：\n\n{text}\n\n{format_instructions}")
    ])
    
    llm = ChatOpenAI(
        temperature=0,
        model="deepseek-chat",
        api_key=openai_api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    )
    chain = prompt | llm | output_parser
    
    try:
        result = chain.invoke({"text": text, "format_instructions": format_instructions})
        return result.get("expenses", [])
    except Exception as e:
        return parse_expenses_fallback(text)

def parse_expenses_fallback(text):
    """
    备用规则匹配方法
    """
    import re
    
    expenses = []
    patterns = [
        r'(\d{4}[-/年]?\d{1,2}[-/月]?\d{1,2}[日号]?)\s*[：:]\s*(.+?)\s*(\d+(?:\.\d+)?)\s*[元块]',
        r'(\d{1,2}[-/月]?\d{1,2}[日号]?)\s*[：:]\s*(.+?)\s*(\d+(?:\.\d+)?)\s*[元块]',
        r'(\d{4}[-/年]?\d{1,2}[-/月]?\d{1,2}[日号]?)\s+(吃饭|外卖|打车|购物|买|消费)\s*(.+?)\s*(\d+(?:\.\d+)?)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) == 3:
                date_str, desc, amount = match
            elif len(match) == 4:
                date_str, category_keyword, desc, amount = match
                desc = f"{category_keyword}{desc}"
            else:
                continue
            
            try:
                amount = float(amount)
            except:
                continue
            
            category = categorize_expense(desc)
            
            expenses.append({
                "date": normalize_date(date_str),
                "category": category,
                "description": desc,
                "amount": amount
            })
    
    return expenses

def categorize_expense(desc):
    """
    根据消费描述进行分类
    """
    desc = desc.lower()
    if any(keyword in desc for keyword in ["饭", "餐", "外卖", "吃", "食堂", "奶茶", "咖啡"]):
        return "餐饮"
    elif any(keyword in desc for keyword in ["车", "地铁", "公交", "打车", "滴滴", "出租"]):
        return "交通"
    elif any(keyword in desc for keyword in ["买", "购物", "超市", "淘宝", "京东"]):
        return "购物"
    elif any(keyword in desc for keyword in ["电影", "游戏", "娱乐", "玩", "KTV"]):
        return "娱乐"
    elif any(keyword in desc for keyword in ["书", "教材", "文具", "学习", "打印", "课程"]):
        return "学习"
    else:
        return "其他"

def normalize_date(date_str):
    """
    标准化日期格式为YYYY-MM-DD
    """
    import re
    from datetime import datetime
    
    date_str = date_str.strip().replace('年', '-').replace('月', '-').replace('日', '').replace('号', '')
    
    match = re.match(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', date_str)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
    
    match = re.match(r'(\d{1,2})[-/](\d{1,2})', date_str)
    if match:
        year = datetime.now().year
        return f"{year}-{match.group(1).zfill(2)}-{match.group(2).zfill(2)}"
    
    return datetime.now().strftime("%Y-%m-%d")

def generate_csv_file(expenses, filename="expenses.csv"):
    """
    将消费记录转换为CSV文件
    """
    df = pd.DataFrame(expenses)
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    return filename

def generate_markdown_table(expenses):
    """
    生成Markdown格式的消费表格
    """
    if not expenses:
        return "暂无消费记录"
    
    total = sum(e["amount"] for e in expenses)
    
    table = "| 日期 | 分类 | 描述 | 金额（元） |\n"
    table += "|------|------|------|------------|\n"
    
    for expense in expenses:
        table += f"| {expense['date']} | {expense['category']} | {expense['description']} | {expense['amount']} |\n"
    
    table += f"\n**总计：{total:.2f} 元**\n"
    
    return table

def get_category_summary(expenses):
    """
    按分类汇总消费金额
    """
    summary = {}
    for expense in expenses:
        category = expense["category"]
        summary[category] = summary.get(category, 0) + expense["amount"]
    return summary

def process_expenses(text, openai_api_key, output_filename="gduf_expenses.csv"):
    """
    完整流程：解析消费文本 -> 生成表格和CSV文件
    """
    expenses = parse_expenses_from_text(text, openai_api_key)
    if not expenses:
        return None, None, "未从文本中提取到消费记录"
    
    csv_file = generate_csv_file(expenses, output_filename)
    markdown_table = generate_markdown_table(expenses)
    
    return csv_file, markdown_table, expenses
