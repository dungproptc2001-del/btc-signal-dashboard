"""Sinh tín hiệu giao dịch từ nến.

Không biết gì về HTML, màu sắc hay emoji – chỉ trả verdict và điểm số.
Việc tô màu là của frontend, việc gắn icon là của notify/messages.py.
"""
from ..config import MAX_SCORE, SIGNAL_THRESHOLD
from .indicators import ema, last_valid, macd_line, rsi, sma

LONG    = "LONG"
SHORT   = "SHORT"
NEUTRAL = "NEUTRAL"
NA      = "N/A"

ACTIONS = {LONG: "MUA / GIỮ", SHORT: "BÁN / SHORT", NEUTRAL: "CHỜ XÁC NHẬN"}


def generate_signal(candles):
    """Chấm điểm ±MAX_SCORE trên một khung thời gian.

    Trả về {"verdict", "action", "score", "max_score", "reasons"}.
    """
    closes  = [c["close"] for c in candles]
    score   = 0
    reasons = []

    # RSI
    cur_rsi = last_valid(rsi(closes), 50)
    if cur_rsi < 35:
        score += 2; reasons.append(f"RSI oversold ({cur_rsi:.1f}) → phục hồi sắp xảy ra")
    elif cur_rsi > 70:
        score -= 2; reasons.append(f"RSI overbought ({cur_rsi:.1f}) → rủi ro điều chỉnh")
    elif cur_rsi > 55:
        score += 1; reasons.append(f"RSI tích cực ({cur_rsi:.1f})")

    # MACD
    macd_val, sig_full, _ = macd_line(closes)
    if last_valid(macd_val, 0) > last_valid(sig_full, 0):
        score += 1; reasons.append("MACD trên Signal → momentum tăng")
    else:
        score -= 1; reasons.append("MACD dưới Signal → momentum giảm")

    # MA cross
    m7  = last_valid(sma(closes, 7))
    m25 = last_valid(sma(closes, 25))
    if m7 and m25:
        if m7 > m25:
            score += 1; reasons.append("MA7 trên MA25 → xu hướng tăng ngắn hạn")
        else:
            score -= 1; reasons.append("MA7 dưới MA25 → xu hướng giảm ngắn hạn")

    # Trend filter: giá so với EMA50 – lọc bớt tín hiệu ngược xu hướng chính
    e50 = last_valid(ema(closes, 50))
    if e50:
        if closes[-1] > e50:
            score += 1; reasons.append(f"Giá trên EMA50 (${e50:,.0f}) → xu hướng chính tăng")
        else:
            score -= 1; reasons.append(f"Giá dưới EMA50 (${e50:,.0f}) → xu hướng chính giảm")

    # Volume confirmation: nến cuối có volume vượt trội mới tính là xác nhận
    vols = [c["volume"] for c in candles]
    if len(vols) >= 21:
        avg_vol = sum(vols[-21:-1]) / 20
        last    = candles[-1]
        if avg_vol > 0 and vols[-1] > avg_vol * 1.5:
            bullish = last["close"] > last["open"]
            score += 1 if bullish else -1
            reasons.append(
                f"Volume đột biến ({vols[-1] / avg_vol:.1f}x TB20) trên nến "
                f"{'tăng' if bullish else 'giảm'} → xác nhận lực "
                f"{'mua' if bullish else 'bán'}"
            )

    # Momentum: 3 nến cùng chiều liên tiếp
    if len(candles) >= 3:
        if all(candles[-i]["close"] > candles[-i]["open"] for i in range(1, 4)):
            score += 1; reasons.append("3 nến tăng liên tiếp → momentum dương")
        elif all(candles[-i]["close"] < candles[-i]["open"] for i in range(1, 4)):
            score -= 1; reasons.append("3 nến giảm liên tiếp → momentum âm")

    if score >= SIGNAL_THRESHOLD:
        verdict = LONG
    elif score <= -SIGNAL_THRESHOLD:
        verdict = SHORT
    else:
        verdict = NEUTRAL

    return {"verdict": verdict, "action": ACTIONS[verdict], "score": score,
            "max_score": MAX_SCORE, "reasons": reasons}


def confluence(verdicts):
    """Gộp verdict của nhiều khung thành một kết luận chung.

    Bản duy nhất – trước refactor logic này bị copy ở 3 chỗ.
    """
    lc = verdicts.count(LONG)
    sc = verdicts.count(SHORT)
    if   lc >= 3: verdict = "STRONG LONG"
    elif lc == 2: verdict = "LONG BIAS"
    elif sc >= 3: verdict = "STRONG SHORT"
    elif sc == 2: verdict = "SHORT BIAS"
    else:         verdict = "NEUTRAL"
    return {"verdict": verdict, "agree": max(lc, sc)}


def confidence(score):
    """Chuẩn hoá |score| thành phần trăm cho thanh confidence."""
    return min(round(abs(score) / MAX_SCORE * 90) + 10, 100)
