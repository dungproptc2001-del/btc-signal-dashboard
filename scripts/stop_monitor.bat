@echo off
:: Can thiet: "schtasks /end" chi giet cmd.exe bao ngoai, python van song tiep.
setlocal enabledelayedexpansion
cd /d E:\bitcoin-report

schtasks /end /tn "BTC Signal Monitor" >nul 2>&1

if exist "data\monitor.pid" (
    set /p MONPID=<"data\monitor.pid"
    taskkill /pid !MONPID! /t /f >nul 2>&1
    if errorlevel 1 (
        echo PID !MONPID! khong con chay - don dep pid file.
    ) else (
        echo Da dung monitor PID !MONPID!.
    )
    del "data\monitor.pid" >nul 2>&1
) else (
    echo Khong co monitor.pid - tim theo command line...
    powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*apps.monitor*' -and $_.ProcessId -ne $PID }; if ($p) { $p | ForEach-Object { Write-Host ('  Kill PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force } } else { Write-Host '  Khong co monitor nao dang chay.' }"
)
echo.
pause
