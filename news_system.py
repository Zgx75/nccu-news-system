import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import plotly.express as px
import io
import re
from datetime import datetime

# --- 1. 自動探勘分類 (Dynamic Category Discovery) ---
@st.cache_data(ttl=3600) # 加上快取，避免每次按按鈕都重新抓分類
def get_dynamic_categories():
    url = "https://www.nccu.edu.tw/p/412-1000-87.php?Lang=zh-tw"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    categories = {}
    
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 尋找網頁中所有的 a 標籤
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            
            # 利用正規表達式尋找「分類專屬連結」 (特徵: 403-1000-數字.php)
            match = re.search(r'403-1000-(\d+)\.php', href)
            
            if match and text:
                # 過濾掉可能不小心抓到的長句子，確保它是單純的分類名稱
                if len(text) < 15 and "更多" not in text:
                    cat_id = match.group(1)
                    categories[text] = cat_id
                    
        return categories
    except Exception as e:
        st.error(f"無法自動取得分類清單: {e}")
        return {}

# --- 2. 光速爬蟲引擎 ---
def fast_crawl_by_category(target_month, category_dict):
    now = datetime.now()
    target_year = now.year - 1 if target_month > now.month else now.year
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    all_results = []
    
    # 這裡的 category_dict 就是剛剛程式自己抓到的分類
    for category_name, cat_id in category_dict.items():
        for page in range(1, 31):
            url = f"https://www.nccu.edu.tw/p/403-1000-{cat_id}-{page}.php?Lang=zh-tw"
            
            try:
                resp = requests.get(url, headers=headers, timeout=5)
                resp.encoding = 'utf-8'
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                news_blocks = soup.select('.d-txt')
                if not news_blocks:
                    break 
                
                found_in_this_page = False
                passed_target_month = False 
                
                for block in news_blocks:
                    # 抓標題與網址
                    mtitle = block.find(class_='mtitle')
                    if not mtitle: continue
                    a_tag = mtitle.find('a')
                    if not a_tag: continue
                    
                    title = a_tag.get_text(strip=True)
                    href = a_tag.get('href')
                    full_link = href if href.startswith('http') else f"https://www.nccu.edu.tw{href}"
                    
                    # 抓日期
                    mdate = block.find(class_='mdate')
                    date_str = mdate.get_text(strip=True) if mdate else ""
                    
                    # 抓單位
                    meditor = block.find(class_='meditor')
                    unit_str = "秘書處" 
                    if meditor:
                        meditor_text = meditor.get_text(strip=True)
                        match = re.search(r'【(.*?)】', meditor_text)
                        if match:
                            unit_str = match.group(1)
                            if unit_str.endswith('訊'):
                                unit_str = unit_str[:-1]

                    # 判斷月份與智慧煞車
                    if date_str:
                        try:
                            clean_date = date_str.replace('/', '-').split(' ')[0]
                            article_date = datetime.strptime(clean_date, "%Y-%m-%d")
                            
                            if article_date.year < target_year or (article_date.year == target_year and article_date.month < target_month):
                                passed_target_month = True
                                
                            if article_date.year == target_year and article_date.month == target_month:
                                found_in_this_page = True
                                all_results.append({
                                    "分類": category_name,
                                    "日期": article_date.strftime("%Y-%m-%d"),
                                    "內容": title, 
                                    "單位": unit_str,
                                    "網址": full_link
                                })
                        except:
                            pass
                
                if passed_target_month or (len(all_results) > 0 and not found_in_this_page):
                    break
                    
            except Exception as e:
                continue
                
    return all_results, target_year

# --- 3. 系統介面 ---
st.set_page_config(page_title="政大新聞自動彙整系統", layout="wide")
st.title("⚡ 政大新聞光速彙整系統 (AI 自動探勘版)")
st.markdown("本系統已實現 **全自動化**：自動從總表探勘最新分類 ID，並使用光速模組擷取資料，無需手動維護分類代碼。")

# 啟動時自動抓取分類
dynamic_categories = get_dynamic_categories()

with st.sidebar:
    st.header("⚙️ 抓取設定")
    if dynamic_categories:
        st.success(f"✅ 自動探勘成功！已發現 {len(dynamic_categories)} 個分類")
        # 讓使用者可以看見系統自動抓到了哪些分類
        with st.expander("查看已發現的分類"):
            st.json(dynamic_categories)
    else:
        st.error("❌ 分類探勘失敗，請檢查網路連線。")
        
    selected_month = st.slider("選擇要抓取的月份", 1, 12, datetime.now().month)
    run_btn = st.button("🚀 開始光速抓取", disabled=not bool(dynamic_categories))

if run_btn:
    with st.spinner(f"系統正以光速掃描 {selected_month} 月份新聞... (預計 5-10 秒完成)"):
        # 將自動抓到的分類丟進爬蟲裡
        data, current_year = fast_crawl_by_category(selected_month, dynamic_categories)
        
        if data:
            df = pd.DataFrame(data)
            df = df.sort_values(by='日期', ascending=False)
            
            st.success(f"✅ 抓取完成！共精準抓出 {len(df)} 則 {selected_month} 月份的新聞。")
            
            c1, c2 = st.columns(2)
            fig_unit = px.pie(df['單位'].value_counts().reset_index(name='數量'), names='單位', values='數量', title="發布單位分佈", hole=0.3)
            c1.plotly_chart(fig_unit, use_container_width=True)
            
            fig_cat = px.bar(df['分類'].value_counts().reset_index(name='數量'), x='分類', y='數量', color='分類', title="新聞分類統計", text_auto=True)
            c2.plotly_chart(fig_cat, use_container_width=True)
            
            st.dataframe(df, use_container_width=True)

            # --- 產生 Excel ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                sheet_name = f"{selected_month}月"
                
                title_df = pd.DataFrame([[f"政大{current_year}年新聞", "", "", "", ""]])
                title_df.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=1)
                
                df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=2)
                
                start_row_stats = len(df) + 6
                unit_counts = df['單位'].value_counts().reset_index()
                unit_counts.columns = ['單位', '數量']
                cat_counts = df['分類'].value_counts().reset_index()
                cat_counts.columns = ['分類', '數量']
                
                unit_counts.to_excel(writer, sheet_name=sheet_name, index=False, startrow=start_row_stats, startcol=0)
                cat_counts.to_excel(writer, sheet_name=sheet_name, index=False, startrow=start_row_stats, startcol=4)
                
            st.download_button(
                label="📥 下載完整 Excel 報表", 
                data=output.getvalue(), 
                file_name=f"政大新聞_{current_year}年{selected_month}月.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning(f"目前找不到 {current_year}年{selected_month}月 的新聞資料，請嘗試其他月份。")