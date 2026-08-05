@echo off
title FDS watcher
call "C:\Users\terry\miniconda3\Scripts\activate.bat" qaqc_st
cd /d "C:\Users\terry\πŸ≈¡ »≠∏È\QAQC_streamlit"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set HF_HUB_OFFLINE=1
python watcher.py --inbox inbox --interval 5 --startup-ping
echo.
echo [watcher ended - exit code %errorlevel%]
echo   2 = model load failed / 3 = already running / 4 = conda env error
pause
