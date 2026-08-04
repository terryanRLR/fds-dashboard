@echo off
REM ===================================================================
REM  check_watcher.bat - 데드맨 스위치 실행 래퍼 (작업 스케줄러가 호출)
REM  주의: 이 파일은 CP949(ANSI) 인코딩이어야 한다.
REM ===================================================================
setlocal
cd /d "%~dp0"

set "CONDA_ROOT=%USERPROFILE%\miniconda3"
if not exist "%CONDA_ROOT%\Scripts\activate.bat" set "CONDA_ROOT=%USERPROFILE%\anaconda3"
if not exist "%CONDA_ROOT%\Scripts\activate.bat" set "CONDA_ROOT=C:\ProgramData\miniconda3"
if not exist "%CONDA_ROOT%\Scripts\activate.bat" exit /b 4
call "%CONDA_ROOT%\Scripts\activate.bat" qaqc_st

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM 옵션을 바꾸려면 이 줄만 수정하세요.
REM   --restart 를 붙이면 워처가 죽었을 때 자동으로 다시 띄웁니다.
python -m tools.check_watcher --stale-minutes 10 --cooldown-minutes 60 %* >> "%~dp0logs\deadman.log" 2>&1
exit /b %errorlevel%
