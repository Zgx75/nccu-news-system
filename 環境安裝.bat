@echo off
chcp 65001 > nul
echo ========================================
echo   🚀 正在透過 requirements.txt 統一安裝套件...
echo ========================================
cd /d "%~dp0"

:: 讓 pip 直接讀取清單進行安裝
python -m pip install -r requirements.txt

echo ========================================
echo   ✅ 安裝完畢！請按任意鍵關閉此視窗。
echo ========================================
pause