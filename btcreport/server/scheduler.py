"""Bốn nhịp chạy nền của server.

| Nhịp    | Chu kỳ   | Việc                                                    |
|---------|----------|---------------------------------------------------------|
| price   | 30 giây  | Ticker 3 mã → đẩy giá qua SSE, trang nhảy số liên tục    |
| scan    | 15 phút  | Quét đủ 4 khung, debounce, gửi Telegram nếu đổi          |
| score   | 30 phút  | Chấm tín hiệu cũ: chạm TP trước hay SL trước             |
| report  | 4 tiếng  | Dựng lại báo cáo BTC, ghi file, gửi Telegram             |

Mọi call chặn (requests) đẩy qua threadpool để không nghẽn event loop.
Mỗi vòng bọc try/except riêng – một lỗi không được giết cả nhịp.
"""
import asyncio
import traceback
from datetime import datetime

from ..config import (
    OUTCOME_INTERVAL, PRICE_INTERVAL, REPORT_INTERVAL, SCAN_INTERVAL, SYMBOLS,
)
from ..notify.telegram import send_telegram
from ..service import journal, outcome
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

    entries = []
    for alert in alerts:
        ok = await _run(send_telegram, alert["text"])
        # Ghi SAU khi gửi để biết Telegram có thành công không. Telegram hỏng vẫn
        # phải ghi – đó chính là lúc web có giá trị nhất.
        entry = await _run(lambda a=alert, k=ok: journal.append(a, telegram_ok=bool(k)))
        if entry:
            entries.append(entry)

    STATE.publish("signal", {
        "symbols": STATE.public()["symbols"],
        "alerts":  [{"name": a["name"], "kind": a["kind"]} for a in alerts],
        "entries": entries,
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


# ── NHỊP CHẤM ĐIỂM ────────────────────────────────────────────────────────────
def _score_once():
    """Chấm những tín hiệu chưa ngã ngũ, ghi kết quả. Trả (số chấm, số ghi)."""
    entries = journal.read()
    results = outcome.evaluate(entries, log=log)
    xong    = outcome.save(results)
    return len(results), xong


async def score_once():
    """Một lượt chấm. Gọi được từ score_loop hoặc từ lệnh Telegram."""
    _, xong = await _run(_score_once)
    STATE.last_score_at = datetime.now()
    if xong:
        for r in xong:
            log(f"  {r['id']}: {r['status']}" + (f"  R={r['r']}" if r.get("r") is not None else ""))
        STATE.publish("outcome", {
            "settled": [{k: r.get(k) for k in ("id", "symbol", "status", "r")} for r in xong],
            "at":      STATE.last_score_at.isoformat(timespec="seconds"),
        })
    return xong


async def score_loop():
    while True:
        if not STATE.paused:
            try:
                await score_once()
            except Exception:
                log("score_loop lỗi:\n" + traceback.format_exc())
        await asyncio.sleep(OUTCOME_INTERVAL)


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
    đợi 4 tiếng mới có báo cáo đầu tiên.

    Đang chạy rồi thì không làm gì. Lớp bảo vệ thứ hai sau khoá trong power.py:
    hai bộ scheduler cùng chạy sẽ ghi đè last_signals.json của nhau.
    """
    if _tasks:
        log("Scheduler đang chạy sẵn – bỏ qua.")
        return

    STATE.signal_state = load_state()
    log("Nạp state, chạy lượt đầu...")

    try:
        prices = await _run(_fetch_prices)
        STATE.update_prices(prices)
    except Exception as e:
        log(f"  giá lượt đầu lỗi: {e}")

    _tasks.append(asyncio.create_task(price_loop()))
    _tasks.append(asyncio.create_task(scan_loop()))
    _tasks.append(asyncio.create_task(score_loop()))
    _tasks.append(asyncio.create_task(report_loop()))
    log(f"Scheduler chạy: giá {PRICE_INTERVAL}s · quét {SCAN_INTERVAL // 60}m "
        f"· chấm {OUTCOME_INTERVAL // 60}m · báo cáo {REPORT_INTERVAL // 3600}h")


async def stop():
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    _tasks.clear()
