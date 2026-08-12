"""Vùng hỗ trợ / kháng cự và mức quản lý rủi ro."""
from ..config import ATR_MULT_SL, ATR_MULT_TP
from .indicators import atr
from .signals import NEUTRAL


def support_resistance(candles, lookback=20):
    """Pivot point cổ điển trên `lookback` nến gần nhất."""
    highs  = [c["high"]  for c in candles[-lookback:]]
    lows   = [c["low"]   for c in candles[-lookback:]]
    closes = [c["close"] for c in candles[-lookback:]]
    pivot  = (max(highs) + min(lows) + closes[-1]) / 3
    return {
        "pivot": pivot,
        "R1": 2 * pivot - min(lows),
        "R2": pivot + (max(highs) - min(lows)),
        "S1": 2 * pivot - max(highs),
        "S2": pivot - (max(highs) - min(lows)),
    }


def risk_levels(candles, verdict, atr_mult_sl=ATR_MULT_SL, atr_mult_tp=ATR_MULT_TP):
    """Gợi ý entry / SL / TP dựa trên ATR. R:R mặc định 1:2.

    NEUTRAL thì không đề xuất gì – vào lệnh khi chưa có hướng là tự bắn vào chân.
    Khi đó sl/tp/rr đều là None, mọi chỗ tiêu thụ phải kiểm `if risk["sl"]`.
    """
    price = candles[-1]["close"]
    a     = atr(candles)
    if not a or verdict in (NEUTRAL, "N/A"):
        return {"entry": price, "sl": None, "tp": None, "atr": a, "rr": None}

    if verdict == "LONG":
        sl, tp = price - atr_mult_sl * a, price + atr_mult_tp * a
    else:
        sl, tp = price + atr_mult_sl * a, price - atr_mult_tp * a
    return {"entry": price, "sl": sl, "tp": tp, "atr": a,
            "rr": atr_mult_tp / atr_mult_sl}
