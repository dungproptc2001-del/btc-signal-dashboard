"""Lấy nến và ticker từ Binance public API."""
from ..config import BINANCE_URL
from .http import get_json


def parse_klines(raw):
    """Đổi mảng kline thô của Binance thành list dict cho dễ đọc."""
    return [
        {
            "ts":     int(k[0]),
            "open":   float(k[1]),
            "high":   float(k[2]),
            "low":    float(k[3]),
            "close":  float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw
    ]


def fetch_klines(symbol, interval, limit):
    return parse_klines(get_json(
        f"{BINANCE_URL}/klines",
        {"symbol": symbol, "interval": interval, "limit": limit},
    ))


def fetch_klines_range(symbol, interval, start, end):
    """Nến trong khoảng [start, end] (datetime UTC)."""
    return parse_klines(get_json(f"{BINANCE_URL}/klines", {
        "symbol":    symbol,
        "interval":  interval,
        "startTime": int(start.timestamp() * 1000),
        "endTime":   int(end.timestamp() * 1000),
        "limit":     1000,
    }))


def fetch_ticker(symbol):
    return get_json(f"{BINANCE_URL}/ticker/24hr", {"symbol": symbol})
