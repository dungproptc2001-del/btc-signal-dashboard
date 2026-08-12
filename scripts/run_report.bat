@echo off
:: Task "BTC Report 4H" goi file nay. Double-click thu cong cung duoc.
cd /d E:\bitcoin-report
set PYTHONIOENCODING=utf-8
python -m apps.report --no-browser >> E:\bitcoin-report\data\run.log 2>&1
echo [%date% %time%] Done (exit %errorlevel%) >> E:\bitcoin-report\data\run.log
