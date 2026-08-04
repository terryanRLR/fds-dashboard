@echo off
REM ===================================================================
REM  install_deadman.bat - 데드맨 스위치를 작업 스케줄러에 등록
REM
REM  왜 별도 데몬을 안 만드나?
REM    감시자도 죽을 수 있다. 작업 스케줄러는 OS가 관리하므로
REM    우리가 만든 어떤 프로세스보다 안 죽는다.
REM
REM  이 파일을 우클릭 - "관리자 권한으로 실행"
REM  주의: 이 파일은 CP949(ANSI) 인코딩이어야 한다.
REM ===================================================================
setlocal

set "TASKNAME=FDS Watcher Deadman"
set "ROOT=%~dp0"
set "INTERVAL=10"

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 관리자 권한으로 실행하세요.
    pause
    exit /b 1
)
if not exist "%ROOT%tools\check_watcher.py" (
    echo [ERROR] tools\check_watcher.py 가 없습니다.
    pause
    exit /b 1
)
if not exist "%ROOT%check_watcher.bat" (
    echo [ERROR] check_watcher.bat 이 없습니다.
    pause
    exit /b 1
)
if not exist "%ROOT%logs" mkdir "%ROOT%logs"

echo 기존 작업이 있으면 제거합니다...
schtasks /Delete /TN "%TASKNAME%" /F >nul 2>&1

echo 작업 등록 중 (%INTERVAL%분 간격)...
schtasks /Create /TN "%TASKNAME%" ^
    /TR "wscript.exe \"%ROOT%check_watcher_hidden.vbs\"" ^
    /SC MINUTE /MO %INTERVAL% /F

if errorlevel 1 (
    echo.
    echo [ERROR] 등록 실패.
    pause
    exit /b 1
)

echo.
echo ==============================================================
echo  등록 완료: %TASKNAME%  (%INTERVAL%분마다 점검)
echo ==============================================================
echo.
echo  동작 확인 (지금 바로 1회 실행):
echo     schtasks /Run /TN "%TASKNAME%"
echo     type logs\deadman.log
echo.
echo  발송 테스트 (실제로 Slack 이 오는지):
echo     python -m tools.check_watcher --stale-minutes 0 --dry-run -v
echo.
echo  상태 확인 : schtasks /Query /TN "%TASKNAME%" /V /FO LIST
echo  제거      : schtasks /Delete /TN "%TASKNAME%" /F
echo.
echo  [참고] 이 작업은 로그인한 사용자 세션에서 실행됩니다.
echo         로그오프 상태에서도 돌리려면 아래처럼 계정을 지정하세요:
echo            schtasks /Create /TN "%TASKNAME%" /RU ".\terry" /RP "비밀번호" ^
echo               /TR "wscript.exe \"%ROOT%check_watcher_hidden.vbs\"" /SC MINUTE /MO %INTERVAL% /F
echo.
pause
