# Dung scheduled task cho bitcoin-report.
#
# Sau khi len web, MOT task duy nhat: "BTC Web Server".
# Server gop ca ba viec - phuc vu web, quet tin hieu 15 phut, dung bao cao 4 tieng -
# nen hai task cu (BTC Report 4H, BTC Signal Monitor) bi go bo. De ca hai cung chay
# se tranh ghi file data\last_signals.json cua nhau.
#
# Chay: powershell -ExecutionPolicy Bypass -File E:\bitcoin-report\scripts\setup_tasks.ps1
# Chay lai bao nhieu lan cung duoc - task cu bi ghi de.

$ErrorActionPreference = 'Stop'
$root    = Split-Path -Parent $PSScriptRoot
$scripts = Join-Path $root 'scripts'
$user    = "$env:USERDOMAIN\$env:USERNAME"

# ── Go cac task doi truoc ────────────────────────────────────────────────────
# Task tao boi schtasks.exe doi khi khong go duoc bang Unregister-ScheduledTask
# (Access denied) - fallback sang schtasks /delete. Van khong duoc thi bao ro
# de chu nha tu chay lai bang quyen admin, chu KHONG nuot loi im lang.
# Goi schtasks qua cmd: stderr cua native exe bi ErrorActionPreference='Stop'
# bien thanh loi ket thuc, cmd nuot ho.
function Invoke-Schtasks([string]$Arguments) {
    cmd /c "schtasks $Arguments >nul 2>&1"
}

$stubborn = @()
foreach ($old in 'BTC 4H Report', 'BTC Report 4H', 'BTC Signal Monitor') {
    if (-not (Get-ScheduledTask -TaskName $old -ErrorAction SilentlyContinue)) { continue }

    Invoke-Schtasks "/end /tn `"$old`""
    try { Unregister-ScheduledTask -TaskName $old -Confirm:$false -ErrorAction Stop }
    catch { Invoke-Schtasks "/delete /tn `"$old`" /f" }

    if (Get-ScheduledTask -TaskName $old -ErrorAction SilentlyContinue) {
        $stubborn += $old
        Write-Host "  [!!] $old - khong go duoc (can quyen admin)"
    } else {
        Write-Host "  [go ] $old"
    }
}

# Giet process con sot lai cua task cu.
# Loc theo ten tien trinh python VA loai tru chinh minh - neu khong, PowerShell
# dang chay script nay se tu khop voi chuoi tim kiem trong command line cua no.
$me = $PID
Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -like 'python*' -and $_.ProcessId -ne $me -and
        ($_.CommandLine -like '*apps.monitor*' -or $_.CommandLine -like '*signal_monitor*')
    } |
    ForEach-Object {
        Write-Host "  [kill] monitor PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
Remove-Item (Join-Path $root 'data\monitor.pid') -Force -ErrorAction SilentlyContinue

# ── Task moi: BTC Web Server ─────────────────────────────────────────────────
Unregister-ScheduledTask -TaskName 'BTC Web Server' -Confirm:$false -ErrorAction SilentlyContinue

# AllowStartIfOnBatteries la thu fix loi 0x800710E0 (task bi tu choi khi may chay pin)
# - mac dinh cua schtasks.exe khong bat cai nay.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -RestartCount 999

Register-ScheduledTask -TaskName 'BTC Web Server' -User $user `
    -Description 'Web dashboard BTC/ETH/XAU + quet tin hieu + bao cao, duyet truy cap qua Telegram' `
    -Action  (New-ScheduledTaskAction  -Execute "$scripts\server_start.bat" -WorkingDirectory $root) `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $user) `
    -Settings $settings | Out-Null
Write-Host '  [OK] BTC Web Server  - tu bat khi dang nhap, tu restart neu chet'

# ── Don rac cu ───────────────────────────────────────────────────────────────
$old = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\btc_signal_monitor.bat"
if (Test-Path $old) { Remove-Item $old -Force; Write-Host '  [OK] Da go launcher cu khoi Startup folder' }

if ($stubborn.Count) {
    Write-Host ''
    Write-Host '  ---------------------------------------------------------------'
    Write-Host '  CON TASK CU CHUA GO DUOC. Mo PowerShell bang quyen Admin va chay:'
    foreach ($t in $stubborn) { Write-Host "    schtasks /delete /tn `"$t`" /f" }
    Write-Host '  Khong go cung khong sao: no tro vao file da xoa nen chi fail vo hai.'
    Write-Host '  ---------------------------------------------------------------'
}

Write-Host ''
Write-Host 'Xong. Dieu khien server:'
Write-Host '  Bat    : scripts\server_start.bat   (hoac schtasks /run /tn "BTC Web Server")'
Write-Host '  Dung   : scripts\server_stop.bat'
Write-Host '  Trang thai: scripts\server_status.bat'
Write-Host '  Tu Telegram: /status  /url  /pause  /resume  /guests  /stop'
Write-Host ''
Write-Host 'Chay tay khi can (dung luc server dang chay se tranh state):'
Write-Host '  python -m apps.report --no-browser'
Write-Host '  python -m apps.monitor'
