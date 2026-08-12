"""Dựng báo cáo BTC. Dùng chung cho apps/report.py và server."""
from datetime import datetime, timedelta

from ..config import REPORT_FILE, SYMBOL
from ..engine.analysis import build_context, get_thu_range
from ..notify.messages import format_report_message
from ..sources.binance import fetch_klines, fetch_klines_range, fetch_ticker
from ..sources.feargreed import fetch_fear_greed
from ..web.renderer import render_report


def build_report(symbol=SYMBOL, log=print):
    """Fetch → phân tích → HTML + text Telegram.

    Trả về (html, message, context).
    """
    week_start, week_end = get_thu_range()
    log(f"  Khoảng tuần: {week_start:%d/%m/%Y} -> {week_end:%d/%m/%Y}")

    daily        = fetch_klines(symbol, "1d", 120)
    weekly       = fetch_klines(symbol, "1w", 26)
    h4           = fetch_klines(symbol, "4h", 100)
    h1           = fetch_klines(symbol, "1h", 100)
    week_candles = fetch_klines_range(symbol, "1d", week_start,
                                      week_end + timedelta(days=1))
    ticker       = fetch_ticker(symbol)
    fear_greed   = fetch_fear_greed()

    ctx = build_context(
        symbol=symbol, now=datetime.now(),
        daily=daily, weekly=weekly, h4=h4, h1=h1,
        ticker=ticker, fear_greed=fear_greed,
        week_candles=week_candles, week_start=week_start, week_end=week_end,
    )

    log(f"  Giá hiện tại  : ${ctx['price']['last']:,.2f}")
    log(f"  Fear & Greed  : {ctx['fear_greed']['value']} - {ctx['fear_greed']['label']}")
    log(f"  Verdict       : {ctx['signal']['verdict']} "
        f"(score {ctx['signal']['score']:+d}) · {ctx['confluence']['verdict']}")

    return render_report(ctx), format_report_message(ctx), ctx


def save_report(html, path=REPORT_FILE):
    path.write_text(html, encoding="utf-8")
    return path
