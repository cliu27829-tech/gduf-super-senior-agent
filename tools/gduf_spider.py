import requests
from bs4 import BeautifulSoup
import os
import json

BASE_URL = "https://qyxq.gduf.edu.cn/"

def fetch_page(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = "utf-8"
        return response.text
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return None

def parse_news_list(html):
    news_items = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        all_links = soup.find_all("a", href=True)
        
        for link in all_links:
            href = link.get("href", "")
            text = link.get_text(strip=True)
            
            if "/info/" in href and len(text) > 5 and len(text) < 100:
                if not href.startswith("http"):
                    href = BASE_URL + href
                
                if href not in [n["url"] for n in news_items]:
                    date_str = ""
                    next_span = link.find_next("span")
                    if next_span:
                        date_str = next_span.get_text(strip=True)
                    
                    news_items.append({
                        "title": text,
                        "url": href,
                        "date": date_str
                    })
                    
                    if len(news_items) >= 10:
                        break
    except Exception as e:
        print(f"Failed to parse news: {e}")
    return news_items

def parse_article_content(url):
    html = fetch_page(url)
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        content_div = soup.find("div", class_="article-content") 
        if not content_div:
            content_div = soup.find("div", id="content")
        if not content_div:
            content_div = soup.find("div", class_="view-content")
        if not content_div:
            content_div = soup.find("div", class_="main-content")
        
        if content_div:
            paragraphs = content_div.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            return content[:1000]
    except Exception as e:
        print(f"Failed to parse article content: {e}")
    return ""

def crawl_gduf_campus():
    print("Crawling GDUF Qingyuan Campus website...")
    
    html = fetch_page(BASE_URL)
    if not html:
        return None
    
    news = parse_news_list(html)
    
    for item in news[:5]:
        item["content"] = parse_article_content(item["url"])
    
    campus_info = {
        "source": "广东金融学院清远校区官网",
        "url": BASE_URL,
        "update_time": "",
        "news": news,
        "basic_info": {
            "address": "广东省清远市清城区东城街道环城东路北1号",
            "email": "qygwh@gduf.edu.cn",
            "zipcode": "511515"
        }
    }
    
    return campus_info

def generate_knowledge_text(campus_info):
    if not campus_info:
        return ""
    
    text = f"# 广东金融学院清远校区官网信息\n\n"
    text += f"## 基本信息\n\n"
    text += f"- 地址：{campus_info['basic_info']['address']}\n"
    text += f"- 邮箱：{campus_info['basic_info']['email']}\n"
    text += f"- 邮编：{campus_info['basic_info']['zipcode']}\n\n"
    
    text += "## 最新新闻与公告\n\n"
    for i, news in enumerate(campus_info['news'], 1):
        text += f"### {i}. {news['title']}\n"
        text += f"**日期**：{news['date']}\n"
        if news.get('content'):
            text += f"**内容**：{news['content']}\n"
        text += f"**链接**：{news['url']}\n\n"
    
    return text

def save_knowledge_to_file(campus_info, data_dir="data"):
    os.makedirs(data_dir, exist_ok=True)
    text = generate_knowledge_text(campus_info)
    filepath = os.path.join(data_dir, "gduf_qingyuan_campus.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Saved campus knowledge to {filepath}")
    return filepath

def update_knowledge_base(data_dir="data"):
    campus_info = crawl_gduf_campus()
    if campus_info:
        return save_knowledge_to_file(campus_info, data_dir)
    return None

if __name__ == "__main__":
    update_knowledge_base()