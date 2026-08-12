"""Ba nhịp chạy nền của server.

| Nhịp    | Chu kỳ   | Việc                                                    |
|---------|----------|---------------------------------------------------------|
| price   | 30 giây  | Ticker 3 mã → đẩy giá qua SSE, trang nhảy số liên tục    |
| scan    | 15 phút  | Quét đủ 4 khung, debounce, gửi Telegram nếu đổi          |
| report  | 4 tiếng  | Dựng lại báo cáo BTC, ghi file, gửi Telegram             |

Mọi call chặn (requests) đẩy qua threadpool để không nghẽn event loop.
Mỗi vòng bọc try/except riêng – một lỗi không được giết cả nhịp.
"""
import asyncio
import traceback
from datetime import datetime

from ..config import PRICE_INTERVAL, REPORT_INTERVAL, SCAN_INTERVAL, SYMBOLS
from ..notify.telegram import send_telegram
from ..service.report import build_report, save_report
from ..service.watch import load_state, save_state, scan_symbols
from ..sources.binance import fetch_ticker
from .state import STATE


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


async def _run(fn, *args):
    """Chạy hàm chặn trong threadpool."""
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)


# ── NHỊP GIÁ ──────────────────────────────────────────────────────────────────
def _fetch_prices():
    out = {}
    for symbol in SYMBOLS.values():
        try:
            t = fetch_ticker(symbol)
            out[symbol] = {
                "last":       float(t["lastPrice"]),
                "change_24h": float(t["priceChangePercent"]),
                "at":         datetime.now().isoformat(timespec="seconds"),
            }
        except Exception as e:
            log(f"  giá {symbol}: {type(e).__name__}: {e}")
    return out


async def price_loop():
    while True:
        try:
            prices = await _run(_fetch_prices)
            if prices:
                STATE.update_prices(prices)
                STATE.publish("price", {"prices": prices})
        except Exception:
            log("price_loop lỗi:\n" + traceback.format_exc())
        await asyncio.sleep(PRICE_INTERVAL)


# ── NHỊP QUÉT TÍN HIỆU ────────────────────────────────────────────────────────
def _scan_once():
    """Quét đồng bộ, trả (state, alerts, snapshots)."""
    state = STATE.signal_state or load_state()
    snapshots = {}

    from ..service.watch import get_snapshot

    def capture(symbol):
        ok, snap = get_snapshot(symbol)
        snapshots[symbol] = snap if ok else None
        return ok, snap

    state, alerts = scan_symbols(state, SYMBOLS, snapshot_fn=capture, log=log)
    save_state(state)
    return state, alerts, snapshots


async def scan_once():
    """Một lượt quét. Gọi được từ scan_loop hoặc từ lệnh /scan trên Telegram."""
    state, alerts, snapshots = await _run(_scan_once)

    STATE.signal_state = state
    for symbol, snap in snapshots.items():
        if snap:
            STATE.update_snapshot(symbol, snap)
    STATE.last_scan_at = datetime.now()

    for alert in alerts:
        await _run(send_telegram, alert["text"])

    STATE.publish("signal", {
        "symbols": STATE.public()["symbols"],
        "alerts":  [{"name": a["name"], "kind": a["kind"]} for a in alerts],
        "at":      STATE.last_scan_at.isoformat(timespec="seconds"),
    })
    return alerts


async def scan_loop():
    while True:
        if not STATE.paused:
            try:
                log("Quét tín hiệu...")
                await scan_once()
            except Exception:
                STATE.scan_errors += 1
                log("scan_loop lỗi:\n" + traceback.format_exc())
        await asyncio.sleep(SCAN_INTERVAL)


# ── NHỊP BÁO CÁO ──────────────────────────────────────────────────────────────
def _report_once():
    html, message, ctx = build_report(log=log)
    save_report(html)
    return html, message, ctx


async def report_once(notify=True):
    html, message, ctx = await _run(_report_once)
    STATE.update_report(html, ctx)
    if notify:
        await _run(send_telegram, message)
    STATE.publish("report", {"at": STATE.last_report_at.isoformat(timespec="seconds"),
                             "verdict": ctx["signal"]["verdict"]})
    return ctx


async def report_loop():
    while True:
        if not STATE.paused:
            try:
                log("Dựng báo cáo BTC...")
                await report_once()
            except Exception:
                log("report_loop lỗi:\n" + traceback.format_exc())
        await asyncio.sleep(REPORT_INTERVAL)


# ── VÒNG ĐỜI ──────────────────────────────────────────────────────────────────
_tasks = []


async def start():
    """Chạy ngay một lượt mỗi nhịp rồi mới vào chu kỳ – không bắt người dùng
    đợi 4 tiếng mới có báo cáo đầu tiên."""
    STATE.signal_state = load_state()
    log("Nạp state, chạy lượt đầu...")

    try:
        prices = await _run(_fetch_prices)
        STATE.update_prices(prices)
    except Exception as e:
        log(f"  giá lượt đầu lỗi: {e}")

    _tasks.append(asyncio.create_task(price_loop()))
    _tasks.append(asyncio.create_task(scan_loop()))
    _tasks.append(asyncio.create_task(report_loop()))
    log(f"Scheduler chạy: giá {PRICE_INTERVAL}s · quét {SCAN_INTERVAL // 60}m "
        f"· báo cáo {REPORT_INTERVAL // 3600}h")


async def stop():
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    _tasks.clear()
