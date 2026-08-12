"""Quét tín hiệu + debounce. Dùng chung cho apps/monitor.py và server.

Điểm mấu chốt của module này: `scan_symbols()` **không gửi Telegram**. Nó trả về danh
sách alert cần gửi, để người gọi tự quyết làm gì — monitor thì gửi Telegram, server thì
vừa gửi Telegram vừa đẩy SSE. Nhờ tách vậy mà test được toàn bộ logic debounce mà không
phải mock Telegram.
"""
import json
import os
from datetime import datetime

from ..config import (
    CONFIRM_SCANS, MAX_CONSEC_FAILS, SCAN_INTERVAL, STATE_FILE, SYMBOLS,
)
from ..engine.analysis import analyze_timeframe
from ..engine.levels import risk_levels, support_resistance
from ..engine.signals import confluence
from ..notify.messages import format_fetch_failure, format_monitor_alert
from ..sources.binance import fetch_klines, fetch_ticker


# ── SNAPSHOT ──────────────────────────────────────────────────────────────────
def get_snapshot(symbol):
    """Ảnh chụp trạng thái một mã.

    Trả (ok, snapshot). ok=False nghĩa là fetch lỗi – KHÔNG được coi là
    'signal không đổi', vì như thế sẽ nuốt mất tín hiệu một cách âm thầm.
    """
    try:
        weekly = fetch_klines(symbol, "1w", 52)
        daily  = fetch_klines(symbol, "1d", 120)
        h4     = fetch_klines(symbol, "4h", 100)
        h1     = fetch_klines(symbol, "1h", 100)
        ticker = fetch_ticker(symbol)

        tfs = [analyze_timeframe("1W", weekly), analyze_timeframe("1D", daily),
               analyze_timeframe("4H", h4),     analyze_timeframe("1H", h1)]

        return True, {
            "confluence": confluence([tf["verdict"] for tf in tfs]),
            "timeframes": tfs,
            "levels":     support_resistance(h4),
            "risk":       risk_levels(h4, tfs[2]["verdict"]),
            "price":      float(ticker["lastPrice"]),
            "change_24h": float(ticker["priceChangePercent"]),
        }
    except Exception as e:
        print(f"    Lỗi: {type(e).__name__}: {e}")
        return False, None


# ── STATE ─────────────────────────────────────────────────────────────────────
def load_state(path=STATE_FILE):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state, path=STATE_FILE):
    """Ghi atomic – tránh file rỗng/hỏng nếu process bị kill giữa chừng."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ── SCAN ──────────────────────────────────────────────────────────────────────
def scan_symbols(state, symbols=None, snapshot_fn=get_snapshot, now=None, log=print):
    """Quét toàn bộ mã, chạy debounce, trả (state mới, danh sách alert).

    Alert là dict:
      {"kind": "signal"|"fetch_failure", "name", "symbol", "text", "snapshot"}

    `snapshot_fn` tiêm được để test không cần mạng.
    """
    symbols = symbols or SYMBOLS
    now_str = (now or datetime.now()).strftime("%d/%m/%Y %H:%M")
    alerts  = []

    for name, symbol in symbols.items():
        ok, snap = snapshot_fn(symbol)
        entry = state.setdefault(symbol, {})

        # Fetch lỗi: đếm, cảnh báo nếu kéo dài, giữ nguyên state cũ
        if not ok:
            fails = entry.get("consec_fails", 0) + 1
            entry["consec_fails"] = fails
            log(f"  {name:<4} lỗi ({fails} lần liên tiếp)")
            if fails == MAX_CONSEC_FAILS:
                alerts.append({
                    "kind": "fetch_failure", "name": name, "symbol": symbol,
                    "text": format_fetch_failure(name, fails, SCAN_INTERVAL // 60),
                    "snapshot": None,
                })
            continue

        if entry.get("consec_fails"):
            entry["consec_fails"] = 0

        conf = snap["confluence"]["verdict"]
        prev = entry.get("confluence", "")

        if conf == prev:
            entry.update(pending="", pending_count=0, timestamp=now_str)
            log(f"  {name:<4} {conf}")
            continue

        # Confluence khác state đã confirm → debounce
        pcount = entry.get("pending_count", 0) + 1 if conf == entry.get("pending") else 1
        entry.update(pending=conf, pending_count=pcount, timestamp=now_str)

        confirmed = True if not prev else pcount >= CONFIRM_SCANS
        if not confirmed:
            log(f"  {name:<4} {conf}  [chờ xác nhận {pcount}/{CONFIRM_SCANS}]")
            continue

        log(f"  {name:<4} {conf}  [CHANGED]")
        alerts.append({
            "kind": "signal", "name": name, "symbol": symbol,
            "text": format_monitor_alert(name, prev, snap, now_str),
            "snapshot": snap,
        })
        entry.update(confluence=conf, pending="", pending_count=0, timestamp=now_str)

    return state, alerts
