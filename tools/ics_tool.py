from icalendar import Calendar, Event
from datetime import datetime, timedelta
import uuid
import re
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List
import os

class Task(BaseModel):
    name: str = Field(description="任务名称")
    deadline: str = Field(description="截止时间，格式YYYY-MM-DD HH:MM")
    location: str = Field(description="地点/备注")

class TaskList(BaseModel):
    tasks: List[Task] = Field(description="任务列表")

def extract_tasks_from_text(text, openai_api_key):
    """
    使用LLM从班群通知文本中提取任务信息
    返回包含任务名称、截止时间、地点/备注的列表
    """
    output_parser = JsonOutputParser(pydantic_object=TaskList)
    format_instructions = output_parser.get_format_instructions()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个任务提取助手，请从文本中提取所有任务信息。"),
        ("human", "请从以下文本中提取所有任务信息，包括任务名称、截止时间和地点/备注：\n\n{text}\n\n{format_instructions}")
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
        return [t.dict() for t in result.tasks]
    except Exception as e:
        return extract_tasks_fallback(text)

def extract_tasks_fallback(text):
    """
    当LLM提取失败时的备用规则匹配方法
    """
    tasks = []
    
    date_patterns = [
        r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*(\d{1,2}):(\d{1,2})',
        r'(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{1,2})',
        r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})',
        r'(\d{1,2})月(\d{1,2})日'
    ]
    
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        for pattern in date_patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) == 5:
                        year, month, day, hour, minute = groups
                    elif len(groups) == 4:
                        year = datetime.now().year
                        month, day, hour, minute = groups
                    elif len(groups) == 3:
                        year, month, day = groups
                        hour, minute = "23", "59"
                    else:
                        year = datetime.now().year
                        month, day = groups
                        hour, minute = "23", "59"
                    
                    deadline = f"{year}-{month.zfill(2)}-{day.zfill(2)} {hour.zfill(2)}:{minute.zfill(2)}"
                    task_name = line[:match.start()].strip() or "未命名任务"
                    
                    tasks.append({
                        "name": task_name,
                        "deadline": deadline,
                        "location": ""
                    })
                except:
                    pass
    
    return tasks

def generate_ics_file(tasks, filename="calendar.ics"):
    """
    将任务列表转换为ICS格式文件
    """
    cal = Calendar()
    cal.add('prodid', '-//GDUF Super-Senior Agent//Calendar//CN')
    cal.add('version', '2.0')
    cal.add('name', '广金任务日历')
    
    for task in tasks:
        event = Event()
        event.add('summary', task.get("name", "未命名任务"))
        
        try:
            deadline_str = task.get("deadline", "")
            if deadline_str:
                dt = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
                event.add('dtstart', dt)
                event.add('dtend', dt + timedelta(hours=1))
        except:
            pass
        
        location = task.get("location", "")
        if location:
            event.add('location', location)
        
        event.add('uid', str(uuid.uuid4()) + '@gduf-agent')
        event.add('dtstamp', datetime.now())
        
        cal.add_component(event)
    
    with open(filename, 'wb') as f:
        f.write(cal.to_ical())
    
    return filename

def process_notification(text, openai_api_key, output_filename="gduf_tasks.ics"):
    """
    完整流程：解析通知文本 -> 提取任务 -> 生成ICS文件
    """
    tasks = extract_tasks_from_text(text, openai_api_key)
    if not tasks:
        return None, "未从文本中提取到任务信息"
    
    ics_file = generate_ics_file(tasks, output_filename)
    return ics_file, tasks