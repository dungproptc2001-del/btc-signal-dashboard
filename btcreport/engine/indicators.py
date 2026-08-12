"""Chỉ báo kỹ thuật. Thuần Python, không phụ thuộc gì ngoài stdlib.

Quy ước: mọi hàm trả series đều trả list cùng độ dài với input,
phần chưa đủ dữ liệu điền None.
"""
import math


def last_valid(series, default=None):
    """Giá trị hợp lệ gần nhất trong series (bỏ qua None ở đuôi)."""
    return next((v for v in reversed(series) if v is not None), default)


def sma(closes, n):
    result = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        result[i] = sum(closes[i - n + 1:i + 1]) / n
    return result


def ema(closes, n):
    result = [None] * len(closes)
    k = 2 / (n + 1)
    for i in range(len(closes)):
        if i < n - 1:
            result[i] = None
        elif i == n - 1:
            result[i] = sum(closes[:n]) / n
        else:
            result[i] = closes[i] * k + result[i - 1] * (1 - k)
    return result


def rsi(closes, period=14):
    result = [None] * len(closes)
    if len(closes) <= period:
        return result

    gains  = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(closes)):
        idx = i - 1
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - 100 / (1 + rs)
        if i < len(closes) - 1:
            avg_gain = (avg_gain * (period - 1) + gains[idx])  / period
            avg_loss = (avg_loss * (period - 1) + losses[idx]) / period
    return result


def macd_line(closes, fast=12, slow=26, signal=9):
    """Trả về (macd, signal, histogram)."""
    e_fast   = ema(closes, fast)
    e_slow   = ema(closes, slow)
    macd_val = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(e_fast, e_slow)
    ]
    valid    = [v for v in macd_val if v is not None]
    sig_raw  = ema(valid, signal)
    sig_full = [None] * (len(macd_val) - len(valid)) + sig_raw
    hist = [
        (m - s) if m is not None and s is not None else None
        for m, s in zip(macd_val, sig_full)
    ]
    return macd_val, sig_full, hist


def bollinger(closes, n=20, k=2):
    """Trả về (upper, mid, lower)."""
    upper, lower, mid = [], [], []
    for i in range(len(closes)):
        if i < n - 1:
            upper.append(None); lower.append(None); mid.append(None)
        else:
            window = closes[i - n + 1:i + 1]
            m  = sum(window) / n
            sd = math.sqrt(sum((x - m) ** 2 for x in window) / n)
            mid.append(m)
            upper.append(m + k * sd)
            lower.append(m - k * sd)
    return upper, mid, lower


def atr(candles, period=14):
    """Average True Range – dùng để đặt SL/TP theo biến động thật của thị trường."""
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h, l = candles[i]["high"], candles[i]["low"]
        pc   = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    window = trs[-period:] if len(trs) >= period else trs
    return sum(window) / len(window)
