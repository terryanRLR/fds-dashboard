@echo off
REM ===================================================================
REM  service_uninstall.bat - FDS 워처 서비스 제거 (관리자 권한 필요)
REM  DB/로그/커서는 지우지 않는다. 서비스 등록만 해제한다.
REM  주의: 이 파일은 CP949(ANSI) 인코딩이어야 한다.
REM ===================================================================
setlocal
set "SVC=FDSWatcher"
set "NSSM=%~dp0nssm.exe"

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 관리자 권한으로 실행하세요.
    pause
    exit /b 1
)
if not exist "%NSSM%" (
    echo [ERROR] nssm.exe 가 없습니다: %NSSM%
    pause
    exit /b 1
)

echo 서비스 중지 중...
"%NSSM%" stop %SVC%
timeout /t 3 /nobreak >nul
echo 서비스 제거 중...
"%NSSM%" remove %SVC% confirm

REM 비정상 종료로 남았을 수 있는 중복 실행 방지 락 정리
if exist "%~dp0.watcher.lock" del /q "%~dp0.watcher.lock" >nul 2>&1

echo.
echo 제거 완료. (fds_results.db / watcher.log / 커서는 그대로 보존됩니다)
echo 수동 실행은 여전히 가능합니다:  run_watcher.bat
echo.
pause
