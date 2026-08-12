@echo off
:: Task "BTC Signal Monitor" goi file nay luc dang nhap. Vong lap chay lien tuc.
cd /d E:\bitcoin-report
set PYTHONIOENCODING=utf-8

:: Khong khoi dong trung neu monitor da chay
if exist "E:\bitcoin-report\data\monitor.pid" (
    set /p MONPID=<"E:\bitcoin-report\data\monitor.pid"
    tasklist /fi "PID eq %MONPID%" 2>nul | find "%MONPID%" >nul
    if not errorlevel 1 (
        echo Monitor da chay san PID %MONPID% - bo qua. >> E:\bitcoin-report\data\monitor.log
        exit /b 0
    )
    del "E:\bitcoin-report\data\monitor.pid" >nul 2>&1
)

python -m apps.monitor >> E:\bitcoin-report\data\monitor.log 2>&1
