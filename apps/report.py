"""Sinh báo cáo BTC dạng HTML + gửi tín hiệu Telegram.

    python -m apps.report [--no-browser]

Chạy tay. Khi server web đang chạy thì nhịp 4 tiếng của nó đã lo việc này rồi.
"""
import sys
import webbrowser

from btcreport.config import REPORT_FILE
from btcreport.notify.messages import format_report_error
from btcreport.notify.telegram import send_telegram
from btcreport.service.report import build_report, save_report


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("[1/4] Lấy dữ liệu và phân tích...")
    html, message, _ = build_report(log=lambda m: print(m))

    print("[2/4] Ghi file...")
    save_report(html)
    print(f"  Đã lưu: {REPORT_FILE}")

    print("[3/4] Gửi Telegram...")
    send_telegram(message)

    if "--no-browser" in argv:
        print("[4/4] Bỏ qua browser (--no-browser)")
    else:
        print("[4/4] Mở browser...")
        webbrowser.open(REPORT_FILE.as_uri())

    print("Xong!")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Chạy qua Task Scheduler → không ai nhìn console. Báo qua Telegram.
        print(f"FATAL: {type(exc).__name__}: {exc}")
        send_telegram(format_report_error(exc))
        raise
