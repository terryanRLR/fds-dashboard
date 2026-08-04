@echo off
REM ===================================================================
REM  run_watcher.bat - FDS 워처 실행 래퍼
REM
REM  왜 python.exe를 직접 부르지 않고 이 배치를 거치나?
REM    서비스로 등록하면 PATH를 물려받지 못한다. conda 환경의
REM    Library\bin 이 PATH에 없으면 lightgbm 등이 DLL을 못 찾아
REM    "모델 로드 실패 -> 더미 모드"로 빠질 수 있다.
REM    -> activate.bat 을 거쳐 환경을 제대로 구성한 뒤 실행한다.
REM
REM  주의: 이 파일은 CP949(ANSI) 인코딩이어야 한다.
REM        UTF-8로 저장하면 한글 주석이 깨져 명령어로 실행된다.
REM
REM  직접 실행:  run_watcher.bat
REM  옵션 추가:  run_watcher.bat --interval 10
REM  PowerShell: .\run_watcher.bat
REM ===================================================================
setlocal

REM 프로젝트 루트 = 이 배치 파일이 있는 폴더 (한글 경로 대응)
cd /d "%~dp0"

REM -- conda 환경 활성화 --------------------------------------------
set "CONDA_ROOT=%USERPROFILE%\miniconda3"
if not exist "%CONDA_ROOT%\Scripts\activate.bat" set "CONDA_ROOT=%USERPROFILE%\anaconda3"
if not exist "%CONDA_ROOT%\Scripts\activate.bat" set "CONDA_ROOT=C:\ProgramData\miniconda3"
if not exist "%CONDA_ROOT%\Scripts\activate.bat" (
    echo [ERROR] conda 를 찾지 못했습니다. CONDA_ROOT 를 직접 지정하세요.
    exit /b 4
)
call "%CONDA_ROOT%\Scripts\activate.bat" qaqc_st
if errorlevel 1 (
    echo [ERROR] conda 환경 qaqc_st 활성화 실패
    exit /b 4
)

REM -- 실행 환경 -----------------------------------------------------
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "HF_HUB_OFFLINE=1"
set "PYTHONUNBUFFERED=1"

REM -- 기본 옵션 (필요하면 이 줄만 고치세요) -------------------------
set "WATCH_ARGS=--inbox inbox --interval 5 --startup-ping"

python watcher.py %WATCH_ARGS% %*
exit /b %errorlevel%
