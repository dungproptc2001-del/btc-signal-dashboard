@echo off
:: Task "BTC Web Server" goi file nay luc dang nhap. Double-click chay tay cung duoc.
:: Server tu giu may thuc khi dang chay - dung server la may ngu lai binh thuong.
setlocal enabledelayedexpansion
cd /d E:\bitcoin-report
set PYTHONIOENCODING=utf-8

:: Khong khoi dong trung
if exist "data\server.pid" (
    set /p SRVPID=<"data\server.pid"
    tasklist /fi "PID eq !SRVPID!" 2>nul | find "!SRVPID!" >nul
    if not errorlevel 1 (
        echo Server da chay san PID !SRVPID! - bo qua.
        exit /b 0
    )
    del "data\server.pid" >nul 2>&1
)

python -m apps.server %* >> E:\bitcoin-report\data\server.log 2>&1
