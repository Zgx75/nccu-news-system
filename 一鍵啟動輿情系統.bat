@echo off
chcp 65001 > nul
echo ========================================
echo   🚀 正在啟動「政大新聞輿情系統」...
echo   請勿關閉此黑畫面視窗，瀏覽器將於幾秒後自動彈出
echo ========================================
cd /d "%~dp0"

:: 將原本的 streamlit run app.py 改成下面這行
python -m streamlit run app.py

pause