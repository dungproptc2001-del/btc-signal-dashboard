"""Gửi tin qua Telegram Bot API."""
import time

import requests

from ..config import HTTP_BACKOFF_SEC, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram(text, retries=3):
    """Gửi tin nhắn plain text. Trả về True nếu gửi được.

    Chưa cấu hình token thì cảnh báo rồi trả False – không raise, vì báo cáo
    vẫn có giá trị kể cả khi không gửi được tin.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [Telegram] Chưa cấu hình TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID "
              "(xem file .env) – bỏ qua.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for attempt in range(retries):
        try:
            r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
                              timeout=10)
            r.raise_for_status()
            print("  [Telegram] Đã gửi tín hiệu!")
            return True
        except Exception as e:
            print(f"  [Telegram] Lỗi (lần {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(HTTP_BACKOFF_SEC * (2 ** attempt))
    return False
