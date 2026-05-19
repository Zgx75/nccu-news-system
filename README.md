📰 政大新聞自動化彙整與 AI 問答系統

這是一套專為收集與分析「政治大學」相關新聞所設計的自動化系統。具備：

24 小時新聞滾動式爬蟲

多關鍵字精準過濾（intitle:）

數據圖表儀表板

結合 OpenAI API 的 RAG（檢索增強生成）智能問答功能

🚀 系統運行模式

系統支援兩種模式：

互動式網頁版

即時數據視覺化

AI 問答介面

自動化背景版

每日定時抓取新聞

自動匯出 Excel 報表

🛠️ 環境建置與安裝（首次執行必看）

請先確認已安裝 Python 3.9（含）以上版本

🔹 建立虛擬環境
python -m venv .venv
.\.venv\Scripts\activate
🔹 安裝依賴套件
pip install --no-cache-dir -r requirements.txt
🔹 建立 .gitignore
# 忽略 Python 虛擬環境與系統快取
.venv/
venv/
env/
__pycache__/
*.pyc

# 忽略自動生成的報表與編輯器暫存檔
每日新聞匯出/
*.xlsx
.ipynb_checkpoints/
🖥️ 啟動 Web UI
streamlit run app.py

預設網址：http://localhost:8501

系統會自動開啟瀏覽器

💡 使用 RAG 功能需輸入 OpenAI API Key

⏰ Windows 自動排程
🔹 建立 run_auto.bat
@echo off
cd /d C:\Users\您的使用者名稱\Desktop\nccu-news-system
call .venv\Scripts\activate.bat
python auto_export.py
🔹 工作排程器設定

名稱：政大新聞自動抓取任務

觸發：每天 09:00

動作：執行 run_auto.bat

⚠️ 開始位置請填：

C:\Users\...\nccu-news-system\
🔹 進階設定

勾選：喚醒電腦以執行此工作

勾選：錯過時間後盡快執行

✅ 完成！

照此 README 操作即可完整執行專案 🚀