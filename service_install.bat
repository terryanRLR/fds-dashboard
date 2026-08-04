@echo off
REM ===================================================================
REM  service_install.bat - FDS 워처를 Windows 서비스로 등록
REM
REM  사전 준비
REM    1) https://nssm.cc/download 에서 nssm 최신본 다운로드
REM    2) win64\nssm.exe 를 이 배치 파일과 같은 폴더에 복사
REM    3) 이 파일을 우클릭 - "관리자 권한으로 실행"
REM
REM  주의: 이 파일은 CP949(ANSI) 인코딩이어야 한다.
REM ===================================================================
setlocal

set "SVC=FDSWatcher"
set "ROOT=%~dp0"
set "NSSM=%ROOT%nssm.exe"

REM -- 사전 점검 -----------------------------------------------------
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] 관리자 권한이 필요합니다.
    echo         이 파일을 우클릭 - "관리자 권한으로 실행" 하세요.
    echo.
    pause
    exit /b 1
)
if not exist "%NSSM%" (
    echo.
    echo [ERROR] nssm.exe 가 없습니다: %NSSM%
    echo         https://nssm.cc/download 에서 받아 win64\nssm.exe 를
    echo         이 폴더에 복사한 뒤 다시 실행하세요.
    echo.
    pause
    exit /b 1
)
if not exist "%ROOT%run_watcher.bat" (
    echo [ERROR] run_watcher.bat 이 없습니다: %ROOT%
    pause
    exit /b 1
)
if not exist "%ROOT%watcher.py" (
    echo [ERROR] watcher.py 가 없습니다. 프로젝트 루트에서 실행하세요.
    pause
    exit /b 1
)

if not exist "%ROOT%logs" mkdir "%ROOT%logs"

REM -- 기존 서비스가 있으면 제거 -------------------------------------
"%NSSM%" status %SVC% >nul 2>&1
if not errorlevel 1 (
    echo [INFO] 기존 서비스 발견 - 중지 후 재등록합니다.
    "%NSSM%" stop %SVC% >nul 2>&1
    timeout /t 3 /nobreak >nul
    "%NSSM%" remove %SVC% confirm >nul 2>&1
    timeout /t 2 /nobreak >nul
)

REM -- 등록 ----------------------------------------------------------
echo [1/4] 서비스 등록 중...
"%NSSM%" install %SVC% "%ROOT%run_watcher.bat"
"%NSSM%" set %SVC% AppDirectory "%ROOT%"
"%NSSM%" set %SVC% DisplayName "FDS 이상거래 워처"
"%NSSM%" set %SVC% Description "inbox 폴더 감시 - ML 분류 - 임계값 초과시 AI 분석 - Slack/Email 발송"
"%NSSM%" set %SVC% Start SERVICE_AUTO_START

echo [2/4] 로그 설정 중...
"%NSSM%" set %SVC% AppStdout "%ROOT%logs\service_out.log"
"%NSSM%" set %SVC% AppStderr "%ROOT%logs\service_err.log"
"%NSSM%" set %SVC% AppRotateFiles 1
"%NSSM%" set %SVC% AppRotateOnline 1
"%NSSM%" set %SVC% AppRotateBytes 10485760

echo [3/4] 재시작 정책 설정 중...
REM 배치 래퍼를 쓰므로 cmd.exe 자식(python)까지 함께 종료해야 한다
"%NSSM%" set %SVC% AppKillProcessTree 1
"%NSSM%" set %SVC% AppStopMethodSkip 0
"%NSSM%" set %SVC% AppStopMethodConsole 5000
REM 예기치 못한 크래시는 15초 후 재시작
"%NSSM%" set %SVC% AppExit Default Restart
"%NSSM%" set %SVC% AppRestartDelay 15000
"%NSSM%" set %SVC% AppThrottle 30000
REM 아래 코드들은 재시작해도 절대 해결되지 않는 종료 사유다.
REM 무한 재시작 루프(= Slack 폭격)를 막기 위해 즉시 중단시킨다.
REM   0 = 정상종료 / 2 = 모델 로드 실패 / 3 = 중복 실행 / 4 = conda 환경 오류
"%NSSM%" set %SVC% AppExit 0 Exit
"%NSSM%" set %SVC% AppExit 2 Exit
"%NSSM%" set %SVC% AppExit 3 Exit
"%NSSM%" set %SVC% AppExit 4 Exit

echo [4/4] 서비스 시작 중...
"%NSSM%" start %SVC%
timeout /t 5 /nobreak >nul

echo.
echo ==============================================================
"%NSSM%" status %SVC%
echo ==============================================================
echo.
echo  등록 완료. 확인 방법:
echo    - 대시보드 세션5 "워처 상태" 패널이 초록색인지
echo    - logs\service_out.log 에 기동 로그가 쌓이는지
echo    - Slack 에 "FDS 워처 기동" 메시지가 왔는지
echo.
echo  [중요] inbox 가 네트워크 공유 폴더라면 서비스 계정을 바꿔야 합니다.
echo         기본 LOCAL SYSTEM 계정은 매핑 드라이브에 접근하지 못합니다.
echo         아래 두 줄을 CMD 에서 직접 실행하세요 (따옴표 포함):
echo.
echo            nssm set FDSWatcher ObjectName ".\terry" "윈도우비밀번호"
echo            nssm restart FDSWatcher
echo.
echo  설정 변경 : nssm edit FDSWatcher
echo  중지/시작 : nssm stop FDSWatcher  /  nssm start FDSWatcher
echo  제거      : service_uninstall.bat
echo.
pause
