"""Quét BTC / ETH / XAU mỗi 15 phút, alert Telegram khi confluence đổi.

    python -m apps.monitor

Chạy tay. Khi server web đang chạy thì nhịp quét của nó đã lo việc này rồi —
đừng chạy cả hai cùng lúc, sẽ ghi đè state của nhau.
"""
import atexit
import os
import signal
import sys
import time
from datetime import datetime

from btcreport.config import CONFIRM_SCANS, PID_FILE, SCAN_INTERVAL, STATE_FILE, SYMBOLS
from btcreport.notify.messages import format_monitor_startup
from btcreport.notify.telegram import send_telegram
from btcreport.service.watch import load_state, save_state, scan_symbols


# ── PID FILE ──────────────────────────────────────────────────────────────────
def write_pid():
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(remove_pid)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass


def remove_pid():
    try:
        PID_FILE.unlink()
    except OSError:
        pass


def _on_signal(signum, frame):
    print(f"\nNhận signal {signum} – dừng monitor.")
    remove_pid()
    sys.exit(0)


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    write_pid()

    print("=" * 44)
    print("  BTC / ETH / XAU  Signal Monitor")
    print(f"  Quét mỗi {SCAN_INTERVAL // 60} phút · Alert khi confluence đổi")
    print(f"  Debounce: {CONFIRM_SCANS} lần quét liên tiếp")
    print("=" * 44)
    print(f"State file: {STATE_FILE}")
    print(f"PID {os.getpid()} → {PID_FILE}")
    print()

    send_telegram(format_monitor_startup(
        list(SYMBOLS), SCAN_INTERVAL // 60, CONFIRM_SCANS))

    state = load_state()
    while True:
        print(f"[{datetime.now():%d/%m/%Y %H:%M:%S}] Scanning...")
        try:
            state, alerts = scan_symbols(state)
            for alert in alerts:
                send_telegram(alert["text"])
            save_state(state)
        except Exception as e:
            # Một lỗi bất ngờ không được phép giết cả monitor
            print(f"  Scan lỗi: {type(e).__name__}: {e}")
        print(f"  → Next in {SCAN_INTERVAL // 60} min\n")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nĐã dừng monitor.")
        remove_pid()
