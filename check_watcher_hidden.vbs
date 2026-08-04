' check_watcher_hidden.vbs
' 작업 스케줄러가 10분마다 콘솔 창을 띄우면 업무에 방해가 되므로,
' 이 VBScript 로 감싸 창 없이 실행한다. (0 = 숨김, False = 완료를 기다리지 않음)
Dim sh, here
Set sh = CreateObject("WScript.Shell")
here = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
sh.Run """" & here & "check_watcher.bat""", 0, False
