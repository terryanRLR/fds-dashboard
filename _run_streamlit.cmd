@echo off
title Streamlit dashboard
call "C:\Users\terry\miniconda3\Scripts\activate.bat" qaqc_st
cd /d "C:\Users\terry\πŸ≈¡ »≠∏È\QAQC_streamlit"
streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false
echo.
echo [Streamlit ended - check messages above for errors]
pause
