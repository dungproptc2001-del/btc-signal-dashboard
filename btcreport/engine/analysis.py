"""Gom mọi thứ engine tính được thành một context dict duy nhất.

Hàm `build_context` KHÔNG gọi mạng – nhận dữ liệu thô, trả kết quả. Nhờ vậy
test nạp fixtures vào là chạy được, không cần Binance.

Context trả về chỉ chứa số, chuỗi và list. Không một ký tự HTML, không mã màu,
không emoji – đó là việc của tầng web/ và notify/.
"""
from datetime import datetime, timedelta, timezone

from ..config import SIGNAL_THRESHOLD
from .indicators import atr, bollinger, ema, last_valid, macd_line, rsi, sma
from .levels import risk_levels, support_resistance
from .signals import NA, confidence, confluence, generate_signal

TIMEFRAMES = ("1W", "1D", "4H", "1H")


def get_thu_range(now=None):
    """(thứ 5 tuần trước 00:00 UTC, thứ 5 tuần này 00:00 UTC)."""
    today = now or datetime.now(timezone.utc)
    days_since_thu = (today.weekday() - 3) % 7      # 0 nếu hôm nay là thứ 5
    this_thu = (today - timedelta(days=days_since_thu)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return this_thu - timedelta(days=7), this_thu


def _ts_label(ts, fmt):
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime(fmt)


def analyze_timeframe(label, candles):
    """Verdict + chỉ báo chính của một khung. Khung thiếu dữ liệu trả N/A."""
    if not candles:
        return {"label": label, "verdict": NA, "action": "", "score": 0,
                "rsi": 50.0, "macd": 0.0, "macd_signal": 0.0, "macd_bull": False}

    closes = [c["close"] for c in candles]
    macd_val, sig_full, _ = macd_line(closes)
    sig = generate_signal(candles)
    m   = last_valid(macd_val, 0)
    ms  = last_valid(sig_full, 0)
    return {
        "label":       label,
        "verdict":     sig["verdict"],
        "action":      sig["action"],
        "score":       sig["score"],
        "rsi":         last_valid(rsi(closes), 50),
        "macd":        m,
        "macd_signal": ms,
        "macd_bull":   m > ms,
    }


def _price_series(candles, label_fmt):
    """Bộ series cơ bản cho chart phụ (4H, 1H)."""
    if not candles:
        return {"labels": [], "close": [], "ma7": [], "ma25": []}
    closes = [c["close"] for c in candles]
    return {
        "labels": [_ts_label(c["ts"], label_fmt) for c in candles],
        "close":  closes,
        "ma7":    sma(closes, 7),
        "ma25":   sma(closes, 25),
    }


def _daily_series(daily):
    closes = [c["close"] for c in daily]
    macd_val, sig_full, hist = macd_line(closes)
    bb_u, bb_m, bb_l = bollinger(closes)
    return {
        "labels":      [_ts_label(c["ts"], "%d/%m") for c in daily],
        "open":        [c["open"]   for c in daily],
        "high":        [c["high"]   for c in daily],
        "low":         [c["low"]    for c in daily],
        "close":       closes,
        "volume":      [c["volume"] for c in daily],
        "ma7":         sma(closes, 7),
        "ma25":        sma(closes, 25),
        "ma99":        sma(closes, 99),
        "rsi":         rsi(closes),
        "macd":        macd_val,
        "macd_signal": sig_full,
        "macd_hist":   hist,
        "bb_upper":    bb_u,
        "bb_mid":      bb_m,
        "bb_lower":    bb_l,
    }


def _ohlcv_rows(daily, n=14):
    rows = []
    for c in daily[-n:]:
        rows.append({
            "date":       _ts_label(c["ts"], "%d/%m/%Y"),
            "open":       c["open"],
            "high":       c["high"],
            "low":        c["low"],
            "close":      c["close"],
            "volume":     c["volume"],
            "change_pct": (c["close"] - c["open"]) / c["open"] * 100,
            "up":         c["close"] >= c["open"],
        })
    return rows


def _forecast_kind(score):
    if score >= SIGNAL_THRESHOLD:
        return "positive"
    if score <= -SIGNAL_THRESHOLD:
        return "negative"
    return "sideways"


def build_context(*, symbol, now, daily, weekly, h4, h1,
                  ticker, fear_greed, week_candles, week_start, week_end):
    """Toàn bộ dữ liệu một báo cáo cần, dưới dạng dict thuần."""
    closes = [c["close"] for c in daily]
    sig    = generate_signal(daily)

    timeframes = [
        analyze_timeframe("1W", weekly),
        analyze_timeframe("1D", daily),
        analyze_timeframe("4H", h4),
        analyze_timeframe("1H", h1),
    ]

    if not week_candles:
        week_candles = daily[-7:]      # fallback nếu API không trả về đủ
    w_open, w_close = week_candles[0]["open"], week_candles[-1]["close"]

    fg_value, fg_label = fear_greed
    macd_val, sig_full, _ = macd_line(closes)
    bb_u, _, bb_l = bollinger(closes)

    return {
        "symbol":       symbol,
        "generated_at": now,
        "price": {
            "last":       float(ticker["lastPrice"]),
            "change_24h": float(ticker["priceChangePercent"]),
            "high_24h":   float(ticker["highPrice"]),
            "low_24h":    float(ticker["lowPrice"]),
            "volume_24h": float(ticker["quoteVolume"]) / 1e9,   # tỷ USD
        },
        "fear_greed": {"value": fg_value, "label": fg_label},
        "week": {
            "start":      week_start,
            "end":        week_end,
            "open":       w_open,
            "close":      w_close,
            "high":       max(c["high"] for c in week_candles),
            "low":        min(c["low"]  for c in week_candles),
            "change_pct": (w_close - w_open) / w_open * 100,
            "days":       len(week_candles),
        },
        "signal": {
            **sig,
            "confidence": confidence(sig["score"]),
            "forecast":   _forecast_kind(sig["score"]),
        },
        "timeframes": timeframes,
        "confluence": confluence([tf["verdict"] for tf in timeframes]),
        "levels":     support_resistance(daily),
        "levels_4h":  support_resistance(h4) if h4 else support_resistance(daily),
        "risk":       risk_levels(daily, sig["verdict"]),
        "current": {
            "rsi":         last_valid(rsi(closes), 0),
            "macd":        last_valid(macd_val, 0),
            "macd_signal": last_valid(sig_full, 0),
            "bb_upper":    last_valid(bb_u, 0),
            "bb_lower":    last_valid(bb_l, 0),
            "ma7":         last_valid(sma(closes, 7), 0),
            "ma25":        last_valid(sma(closes, 25), 0),
            "ma99":        last_valid(sma(closes, 99), 0),
            "ema50":       last_valid(ema(closes, 50), 0),
            "atr":         atr(daily),
        },
        "chart": {
            "daily": _daily_series(daily),
            "h4":    _price_series(h4, "%d/%m %Hh"),
            "h1":    _price_series(h1, "%d/%m %Hh"),
        },
        "ohlcv": _ohlcv_rows(daily),
    }
