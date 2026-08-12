@echo off
:: Server dang chay khong, URL nao, quet lan cuoi luc nao.
setlocal enabledelayedexpansion
cd /d E:\bitcoin-report

echo ============================================
echo   BTC Web Server - trang thai
echo ============================================

if exist "data\server.pid" (
    set /p SRVPID=<"data\server.pid"
    tasklist /fi "PID eq !SRVPID!" 2>nul | find "!SRVPID!" >nul
    if errorlevel 1 (
        echo   Process : KHONG CHAY  ^(pid file mo coi: !SRVPID!^)
    ) else (
        echo   Process : dang chay, PID !SRVPID!
    )
) else (
    echo   Process : KHONG CHAY  ^(khong co pid file^)
)

echo.
powershell -NoProfile -Command "try { $r = Invoke-RestMethod http://localhost:8000/healthz -TimeoutSec 4; $h=[int]($r.uptime_seconds/3600); $m=[int](($r.uptime_seconds%%3600)/60); Write-Host \"  HTTP    : OK, song $h gio $m phut\"; if ($r.paused) { Write-Host '  Quet    : DANG TAM DUNG' } else { Write-Host '  Quet    : dang chay' } } catch { Write-Host '  HTTP    : khong tra loi tren cong 8000' }"

echo.
echo   Log     : data\server.log
echo   Dung    : scripts\server_stop.bat
echo   Telegram: /status  /url  /guests
echo.
pause
