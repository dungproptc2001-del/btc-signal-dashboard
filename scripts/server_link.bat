@echo off
:: Lay link cong khai HIEN TAI tu server dang chay, chep vao clipboard, mo trinh duyet.
:: Khong luu URL vao dau ca: quick tunnel doi URL moi lan khoi dong, luu la link chet.
cd /d E:\bitcoin-report

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-RestMethod http://localhost:8000/api/link -TimeoutSec 5 } catch { Write-Host ''; Write-Host '  Server khong tra loi tren cong 8000.'; Write-Host '  Bat bang: BTC Server - Bat'; Write-Host ''; exit 1 };" ^
  "if (-not $r.url) { Write-Host ''; Write-Host '  Server dang chay nhung KHONG co tunnel.'; Write-Host '  Chay --no-tunnel, hoac cloudflared khong len duoc.'; Write-Host '  Xem log: data\server.log'; Write-Host ''; exit 1 };" ^
  "Set-Clipboard -Value $r.url;" ^
  "Write-Host ''; Write-Host ('  Link cong khai : ' + $r.url); Write-Host '  Da chep vao clipboard - Ctrl+V la dan duoc.'; Write-Host ''; Write-Host '  Nguoi la mo link nay se thay trang xin quyen,'; Write-Host '  ong duyet bang nut trong Telegram.'; Write-Host '';" ^
  "Start-Process $r.url"

pause
