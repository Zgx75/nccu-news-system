import os
import re
import json
import time
import urllib.parse
from datetime import datetime, timezone

import pandas as pd
import feedparser
import requests
from bs4 import BeautifulSoup
from newspaper import Article, Config
from google import genai
from dotenv import load_dotenv

load_dotenv()
# ================= 配置區域 =================
# 請至 https://aistudio.google.com/ 申請免費 API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# ===========================================

def extract_article_date(article_obj):
    """
    終極版日期擷取：包含 JSON-LD 解析與 Regex 暴力破解，專治 MSN 與 Yahoo 等 JS 渲染平台。
    """
    try:
        html_content = article_obj.html
        soup = BeautifulSoup(html_content, "html.parser")

        # 🚀 第零防線：暴力 Regex 破解 (專剋 MSN 等隱藏在 JS 變數中的時間)
        date_match = re.search(r'"(?:publishedDateTime|datePublished|pubDate)":"(\d{4}-\d{2}-\d{2}T[^"]+)"', html_content, re.IGNORECASE)
        if date_match:
            return pd.to_datetime(date_match.group(1), errors="coerce")

        # 第一防線：解析 JSON-LD 結構化資料
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                
                if isinstance(data, list):
                    for item in data:
                        if "datePublished" in item:
                            return pd.to_datetime(item["datePublished"], errors="coerce")
                elif isinstance(data, dict):
                    if '@graph' in data:
                        for item in data['@graph']:
                            if "datePublished" in item:
                                return pd.to_datetime(item["datePublished"], errors="coerce")
                    if "datePublished" in data:
                        return pd.to_datetime(data["datePublished"], errors="coerce")
            except json.JSONDecodeError:
                continue

        # 第二防線：常規 Meta 標籤
        for tag in [
            {"property": "article:published_time"},
            {"name": "pubdate"},
            {"name": "publishdate"},
            {"name": "date"},
            {"itemprop": "datePublished"},
        ]:
            meta = soup.find("meta", attrs=tag)
            if meta and meta.get("content"):
                return pd.to_datetime(meta["content"], errors="coerce")

        # 第三防線：HTML5 Time 標籤
        time_tag = soup.find("time")
        if time_tag:
            raw = time_tag.get("datetime") or time_tag.get_text(strip=True)
            return pd.to_datetime(raw, errors="coerce")
            
        # 第四防線：newspaper3k 內建解析器
        if article_obj.publish_date:
            return pd.to_datetime(article_obj.publish_date, errors="coerce")

    except Exception as e:
        pass

    return None

def is_relevant_article(title, content, main_keywords=["政大", "政治大學", "NCCU"]):
    """
    新聞相關性過濾機制（只要標題或內文任一處出現關鍵字即視為相關）
    """
    if any(kw.lower() in title.lower() for kw in main_keywords):
        return True
        
    if not content:
        return False

    content_lower = content.lower()
    return any(kw.lower() in content_lower for kw in main_keywords)

def get_real_url(google_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://news.google.com/'
    }
    try:
        with requests.Session() as s:
            res = s.get(google_url, timeout=12, headers=headers, allow_redirects=True)
            final_url = res.url
            
            if "msn.com" in final_url:
                soup = BeautifulSoup(res.text, "html.parser")
                meta = soup.find("meta", property="og:url")
                if meta:
                    href = meta.get("content", "")
                    if href and "msn.com" not in href:
                        return href
                
            return final_url
    except:
        return google_url

def extract_best_content(article_obj, entry_summary):
    """三層擷取機制：優先抓本文，次抓 Meta，末抓 RSS"""
    main_text = article_obj.text.strip()
    if len(main_text) > 120:
        return main_text
    
    try:
        soup = BeautifulSoup(article_obj.html, 'html.parser')
        meta_desc = (
            soup.find("meta", property="og:description") or 
            soup.find("meta", attrs={"name": "description"})
        )
        if meta_desc and len(meta_desc.get("content", "")) > 40:
            return meta_desc["content"]
    except:
        pass
        
    return BeautifulSoup(entry_summary, "html.parser").text

def get_ai_summary(title, content_text):
    if not content_text or len(content_text) < 80:
        return "（內容不足，建議點擊連結閱讀全文）"

    if not GEMINI_API_KEY:
        return "（未配置 Gemini API Key，跳過摘要）"

    client = genai.Client(api_key=GEMINI_API_KEY)

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=f"""
請將以下新聞整理成「100字以內摘要」。

要求：
1. 不要出現「你」、「我」、「分析官」
2. 不要解釋、不要前言
3. 只輸出摘要內容
4. 使用第三人稱
5. 控制在80~120字
6. 如果資訊不足，直接回覆：內容不足

標題：{title}
內文：{content_text[:1200]}
"""
            )

            text = response.text.strip()

            if any(x in text for x in ["我是", "分析官", "您提供", "無法摘要"]):
                return "（內容不足，建議點擊連結閱讀全文）"

            if len(text) < 30:
                return "（內容不足，建議點擊連結閱讀全文）"

            return text

        except Exception as e:
            if "503" in str(e):
                time.sleep(3 * (attempt + 1))
            else:
                return "摘要失敗"

    return "（AI服務繁忙）"

def fetch_nccu_news(keywords_str, max_results=50):
    keyword_list = [k.strip() for k in keywords_str.split(",") if k.strip()]
    news_list = []
    
    config = Config()
    config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    config.request_timeout = 15

    current_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    is_monday = datetime.now().weekday() == 0
    max_seconds = 86400 * (3 if is_monday else 1)
    time_param = "3d" if is_monday else "1d"

    for kw in keyword_list:
        print(f"📡 正在搜尋：{kw} ...")
        query_string = f"{kw} -MSN" 
        safe_kw = urllib.parse.quote(query_string)
        url = f"https://news.google.com/rss/search?q={safe_kw}%20when:{time_param}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)

        for entry in feed.entries[:max_results]:
            try:
                # 🚫 終極攔截點：從最源頭檢查媒體名稱與網址
                media_name = entry.source.title if hasattr(entry, "source") else ""
                if "nccu.edu.tw" in media_name.lower() or "nccu.edu.tw" in entry.link.lower():
                    continue  # 直接拋棄，連日期都不算、網頁也不抓
                
                pub_dt = datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S GMT")
                if (current_utc - pub_dt).total_seconds() <= max_seconds:
                    
                    real_link = get_real_url(entry.link)
                    
                    article = Article(real_link, language='zh', config=config)
                    article.download()
                    article.parse()
                    real_pub_dt = extract_article_date(article)

                    if real_pub_dt is not None:
                        real_pub_dt = real_pub_dt.tz_localize(None) if hasattr(real_pub_dt, 'tzinfo') and real_pub_dt.tzinfo else real_pub_dt
                        if (current_utc - real_pub_dt).total_seconds() > max_seconds:
                            continue
                        final_dt = real_pub_dt
                    else:
                        final_dt = pub_dt

                    best_text = extract_best_content(article, entry.summary)
                    
                    nccu_core_targets = ["政治大學", "政大"]
                    clean_kw = kw.replace('"', '').strip().lower()
                    needs_strict_filter = any(target in clean_kw for target in nccu_core_targets)

                    if needs_strict_filter:
                        if not is_relevant_article(entry.title, best_text):
                            continue

                    summary = get_ai_summary(entry.title, best_text)

                    news_list.append({
                        "來源關鍵字": kw,
                        "發布時間": final_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "媒體": entry.source.title,
                        "標題": entry.title,
                        "連結": real_link,
                        "摘要": summary
                    })

                    time.sleep(1.5)
            except:
                continue
                
    return pd.DataFrame(news_list).drop_duplicates(subset=['連結']).reset_index(drop=True)

def ai_generate_bullets(title, df, fallback_items):
    if not GEMINI_API_KEY or df.empty:
        return fallback_items
        
    news_text = "\n".join([
        f"- 標題：{r.get('標題','')}｜媒體：{r.get('媒體','')}｜摘要：{r.get('摘要','')}"
        for _, r in df.iterrows()
    ])

    prompt = f"""
你是國立政治大學輿情分析人員。
請根據以下新聞資料，產出「{title}」。

要求：
1. 使用正式、簡潔、穩健語氣
2. 產出 3 點條列
3. 每點不超過 35 字
4. 不要使用 Markdown
5. 不要加標題
6. 只輸出三行，每行一點

新聞資料：
{news_text[:5000]}
"""

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    contents=prompt
                )
                text = response.text.strip()
                lines = [line.strip("・-• 1234567890.、 ") for line in text.splitlines() if line.strip()]
                if lines:
                    return lines[:3]
                break
            except Exception as e:
                if "503" in str(e):
                    time.sleep(2 * (attempt + 1))
                else:
                    return fallback_items
    except Exception:
        pass
    return fallback_items

def classify_news(title, media, keyword=""):
    text = f"{title} {media} {keyword}"

    # 清除官網判定邏輯
    if "政大" in text or "政治大學" in text or "UBA" in text:
        if "UBA" in text or "籃" in text or "體育" in text:
            return "政大", "體育"
        return "政大", "校務"

    if any(k in text for k in ["大學", "高教", "校區", "教授", "學生", "選系", "AI", "教育"]):
        if "AI" in text or "選系" in text:
            return "高教", "選系／AI"
        if "校區" in text or "建設" in text:
            return "高教", "校區建設"
        if "爭議" in text or "霸凌" in text or "提告" in text:
            return "高教", "教學爭議"
        return "高教", "高教議題"

    return "高教", "其他"

def export_email_html(df, folder):
    now = datetime.now()

    today_full = f"{now.year} 年 {now.month} 月 {now.day} 日"
    today_short = f"{now.month}/{now.day}"
    file_time = datetime.now().strftime("%Y%m%d_%H%M")

    df = df.copy()

    categories = df.apply(
        lambda r: classify_news(
            r.get("標題", ""),
            r.get("媒體", ""),
            r.get("來源關鍵字", "")
        ),
        axis=1
    )

    df["類別"] = [c[0] for c in categories]
    df["主題"] = [c[1] for c in categories]

    observation_items = ai_generate_bullets(
        "輿情觀察",
        df,
        [
            "政大相關新聞以校務與活動曝光為主。",
            "高教議題聚焦 AI、校園建設與教學爭議。",
            "整體新聞風向偏中性穩定。"
        ]
    )

    def section_bar(title, bg="#dbe7f3"):
        return f"""
        <div style="background:{bg}; padding:10px 12px; margin-top:24px; font-weight:bold;">
            {title}
        </div>
        """

    def news_list_html(rows):
        if rows.empty:
            return '<p style="margin-left:4px;">今日暫無相關新聞。</p>'

        html = '<ul style="padding-left:22px; margin-top:14px;">'
        for _, r in rows.iterrows():
            html += f"""
            <li style="margin-bottom:8px;">
                <a href="{r['連結']}" style="color:#0057c2; text-decoration:underline;">
                    {r['標題']}
                </a>
                <span>（{r['媒體']}）</span>
            </li>
            """
        html += "</ul>"
        return html

    nccu_news = df[df["類別"] == "政大"]
    higher_edu = df[df["類別"] == "高教"]

    html = f"""
    <html>
    <body style="
        font-family:'Microsoft JhengHei', Arial, sans-serif;
        color:#111;
        font-size:16px;
        line-height:1.7;
        margin:0;
        padding:32px 44px;
        background:#ffffff;
    ">

    <div style="background:#dbe7f3; padding:24px 30px; margin-bottom:42px;">
        <h1 style="font-size:30px; margin:0; font-weight:bold;">
            {today_short} 政大輿情彙整
        </h1>
    </div>

    <p>各位師長、同仁好：</p>

    <p>
        以下為 <strong>{today_full}</strong> 新聞輿情，敬請參閱。<br>
        如對相關議題有興趣，請直接點選標題連結。
    </p>

    <div style="
        border:1px solid #d6e0ea;
        background:#f8fbff;
        padding:18px 22px;
        margin:26px 0;
    ">
        <p style="font-weight:bold; margin-top:0;">輿情觀察</p>
        <ul style="margin-bottom:0; padding-left:22px;">
            {''.join([f'<li>{item}</li>' for item in observation_items])}
        </ul>
    </div>

    {section_bar("政大相關（新聞）", "#dbe7f3")}
    {news_list_html(nccu_news)}

    {section_bar("高教", "#f1f1f1")}
    {news_list_html(higher_edu)}

    <h2 style="font-size:22px; margin-top:28px;">完整新聞列表</h2>

    <table border="1" cellpadding="8" cellspacing="0" style="
        border-collapse:collapse;
        width:60%;
        min-width:900px;
        font-size:15px;
    ">
        <tr style="background:#dbe7f3; text-align:center;">
            <th style="width:90px;">類別</th>
            <th style="width:120px;">主題</th>
            <th>標題</th>
            <th style="width:130px;">來源</th>
        </tr>
    """

    for _, r in df.iterrows():
        html += f"""
        <tr>
            <td>{r['類別']}</td>
            <td>{r['主題']}</td>
            <td>
                <a href="{r['連結']}" style="color:#0057c2; text-decoration:underline;">
                    {r['標題']}
                </a>
            </td>
            <td>{r['媒體']}</td>
        </tr>
        """

    html += f"""
    </table>

    <hr style="margin-top:10px;">

    <p>
        <strong>【校園簡介影片】</strong><br>
        政大校園簡介影片上線，歡迎點閱分享。<br>
        中文｜<a href="https://youtu.be/l9hS0Xu3ZOY">https://youtu.be/l9hS0Xu3ZOY</a><br>
        English｜<a href="https://youtu.be/1ViR0M-UB3o">https://youtu.be/1ViR0M-UB3o</a>
    </p>

    <p><strong>國立政治大學 National Chengchi University</strong></p>

    <p>
        📘 Facebook｜<a href="#">Facebook</a><br>
        📸 Instagram｜<a href="#">Instagram</a><br>
        ▶️ YouTube｜<a href="#">YouTube</a><br>
        👤 MyNCCU｜<a href="#">MyNCCU</a><br>
        💜 校友平台｜<a href="#">We are NCCU</a>
    </p>

    </body>
    </html>
    """

    path = f"{folder}/政大輿情草稿_{file_time}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return path

def job():
    print(f"🚀 系統啟動：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    keywords = '"政治大學","政大","NCCU","李蔡彥","高教","頂大"'
    df = fetch_nccu_news(keywords)

    if not df.empty:
        folder = "每日新聞匯出"
        os.makedirs(folder, exist_ok=True)
        excel_file = f"{folder}/政大新聞_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        df.to_excel(excel_file, index=False, engine='openpyxl')
        export_email_html(df, folder)
        print(f"✅ 任務成功！檔案存放於：{folder}")
    else:
        print("📭 今日無相關新聞動態。")

if __name__ == "__main__":
    job()