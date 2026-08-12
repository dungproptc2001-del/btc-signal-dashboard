@echo off
:: Tat server, nha keep-alive (may ngu lai binh thuong), dong tunnel.
:: Can thiet: "schtasks /end" chi giet cmd.exe bao ngoai, python van song tiep.
setlocal enabledelayedexpansion
cd /d E:\bitcoin-report

schtasks /end /tn "BTC Web Server" >nul 2>&1

if exist "data\server.pid" (
    set /p SRVPID=<"data\server.pid"
    taskkill /pid !SRVPID! /t /f >nul 2>&1
    if errorlevel 1 (
        echo PID !SRVPID! khong con chay - don dep pid file.
    ) else (
        echo Da dung server PID !SRVPID!.
    )
    del "data\server.pid" >nul 2>&1
) else (
    echo Khong co server.pid - tim theo command line...
    powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*apps.server*' -and $_.ProcessId -ne $PID }; if ($p) { $p | ForEach-Object { Write-Host ('  Kill PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force } } else { Write-Host '  Khong co server nao dang chay.' }"
)

:: cloudflared la process con, kill rieng cho chac
taskkill /im cloudflared.exe /f >nul 2>&1

echo.
echo May se ngu lai binh thuong tu gio.
pause
