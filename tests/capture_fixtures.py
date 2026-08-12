"""Chụp một lát cắt dữ liệu Binance thật vào tests/fixtures/.

Chạy tay khi cần làm mới mốc so sánh:
    python tests/capture_fixtures.py

Lý do tồn tại: giá thị trường đổi mỗi lần fetch, nên không thể so output
trước/sau refactor bằng cách chạy live hai lần. Đóng băng input rồi mới so được.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

BASE     = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(BASE, "fixtures")
BINANCE  = "https://api.binance.com/api/v3"
SYMBOL   = "BTCUSDT"


def _get(url, params=None):
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def _save(name, obj):
    path = os.path.join(FIXTURES, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    print(f"  {name:<22} {len(json.dumps(obj)):>9,} bytes")


def thu_range():
    today = datetime.now(timezone.utc)
    days_since_thu = (today.weekday() - 3) % 7
    this_thu = (today - timedelta(days=days_since_thu)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return this_thu - timedelta(days=7), this_thu


def main():
    os.makedirs(FIXTURES, exist_ok=True)
    print(f"Chup fixtures tu Binance ({SYMBOL})...")

    for interval, limit in (("1w", 52), ("1d", 120), ("4h", 100), ("1h", 100)):
        _save(f"klines_{interval}.json",
              _get(f"{BINANCE}/klines",
                   {"symbol": SYMBOL, "interval": interval, "limit": limit}))

    start, end = thu_range()
    _save("klines_week.json",
          _get(f"{BINANCE}/klines", {
              "symbol": SYMBOL, "interval": "1d",
              "startTime": int(start.timestamp() * 1000),
              "endTime":   int((end + timedelta(days=1)).timestamp() * 1000),
              "limit": 1000}))

    _save("ticker.json", _get(f"{BINANCE}/ticker/24hr", {"symbol": SYMBOL}))

    try:
        fg = _get("https://api.alternative.me/fng/?limit=1")["data"][0]
        _save("feargreed.json", {"value": int(fg["value"]),
                                 "label": fg["value_classification"]})
    except Exception as e:
        print(f"  feargreed loi ({e}) - dung gia tri co dinh")
        _save("feargreed.json", {"value": 27, "label": "Fear"})

    # Mốc thời gian cố định để context có generated_at tất định
    _save("meta.json", {
        "symbol":     SYMBOL,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "now":        "2026-08-12T15:00:00",
        "week_start": start.isoformat(),
        "week_end":   end.isoformat(),
    })
    print("Xong.")


if __name__ == "__main__":
    sys.exit(main())
