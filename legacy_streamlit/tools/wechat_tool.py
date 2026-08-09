import requests
from bs4 import BeautifulSoup
import re
import time
import random

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def fetch_wechat_articles(query, count=5):
    """
    使用搜狗微信搜索API获取公众号文章
    :param query: 搜索关键词
    :param count: 获取文章数量
    :return: 文章列表
    """
    articles = []
    base_url = "https://weixin.sogou.com/weixin"
    
    try:
        params = {
            "type": 2,
            "query": query,
            "page": 1,
            "ie": "utf8"
        }
        
        headers = {
            "User-Agent": get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://weixin.sogou.com/"
        }
        
        session = requests.Session()
        response = session.get(base_url, params=params, headers=headers)
        
        if response.status_code != 200:
            return articles
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        items = soup.find_all('div', class_='txt-box')
        if not items:
            items = soup.find_all('div', class_='article')
        
        for item in items[:count]:
            try:
                title_tag = item.find('h3') or item.find('a')
                title = title_tag.get_text(strip=True) if title_tag else "无标题"
                
                link_tag = item.find('a')
                link = link_tag['href'] if link_tag else ""
                
                summary_tag = item.find('p', class_='txt-info') or item.find('p')
                summary = summary_tag.get_text(strip=True) if summary_tag else ""
                
                date_tag = item.find('span', class_='s2') or item.find('span', class_='time')
                date = date_tag.get_text(strip=True) if date_tag else ""
                
                if link:
                    full_content = fetch_article_content(link, session)
                else:
                    full_content = summary
                
                articles.append({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "date": date,
                    "content": full_content
                })
                
                time.sleep(random.uniform(1, 2))
                
            except Exception as e:
                continue
        
    except Exception as e:
        print(f"搜索公众号文章失败: {str(e)}")
    
    return articles

def fetch_article_content(url, session=None):
    """
    获取微信公众号文章的完整内容
    """
    if not session:
        session = requests.Session()
    
    try:
        headers = {
            "User-Agent": get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }
        
        response = session.get(url, headers=headers, allow_redirects=True)
        
        if response.status_code != 200:
            return ""
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        content_div = soup.find('div', id='js_content') or soup.find('div', class_='rich_media_content')
        if content_div:
            text_content = content_div.get_text(separator='\n', strip=True)
            text_content = re.sub(r'\n+', '\n', text_content)
            return text_content[:3000]
        
        return ""
    
    except Exception as e:
        return ""

def crawl_gduf_wechat():
    """
    爬取广东金融学院相关公众号最新文章
    """
    queries = ["广东金融学院", "广金", "广金教务", "广金招生"]
    
    all_articles = []
    
    for query in queries:
        articles = fetch_wechat_articles(query, count=3)
        all_articles.extend(articles)
        time.sleep(random.uniform(2, 3))
    
    all_articles.sort(key=lambda x: x.get('date', ''), reverse=True)
    
    return all_articles[:10]

def generate_articles_summary(articles):
    """
    生成文章摘要
    """
    if not articles:
        return "暂无公众号文章信息"
    
    summary = "📢 广金最新资讯：\n\n"
    
    for i, article in enumerate(articles[:5], 1):
        summary += f"{i}. **{article['title']}**\n"
        summary += f"   📅 {article['date']}\n"
        summary += f"   🔗 [查看原文]({article['link']})\n"
        summary += f"   💡 {article['summary'][:50]}...\n\n"
    
    return summary