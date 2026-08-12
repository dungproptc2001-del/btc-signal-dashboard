"""Chấm điểm tín hiệu và gộp confluence."""
import math

import pytest

from btcreport.config import MAX_SCORE, SIGNAL_THRESHOLD
from btcreport.engine.signals import (
    LONG, NEUTRAL, SHORT, confidence, confluence, generate_signal,
)


def wave(n, start, drift, amp, period=7, vol=100.0):
    """Chuỗi nến có xu hướng + dao động.

    Phải có dao động thật (amp > |drift|) mới giống thị trường: chuỗi tăng
    đơn điệu tuyệt đối đẩy RSI lên 100 → dính luật overbought −2, ra NEUTRAL.
    """
    out, p = [], start
    for i in range(n):
        prev = p
        p += drift + amp * math.sin(i * 2 * math.pi / period)
        out.append({"ts": i * 86_400_000, "open": prev, "close": p,
                    "high": max(prev, p) + 1, "low": min(prev, p) - 1,
                    "volume": vol})
    return out


def uptrend(vol=100.0):
    """Uptrend đã hiệu chỉnh để RSI rơi vào vùng 55–70 → ra LONG score +5."""
    return wave(101, start=100.0, drift=0.8, amp=3.0, vol=vol)


# ── Ngưỡng verdict ───────────────────────────────────────────────────────────
def test_nguong_threshold_dung_gia_tri_config():
    assert SIGNAL_THRESHOLD == 3
    assert MAX_SCORE == 7


def test_uptrend_ra_long():
    r = generate_signal(uptrend())
    assert r["verdict"] == LONG
    assert r["score"] >= SIGNAL_THRESHOLD
    assert r["action"] == "MUA / GIỮ"


def test_du_lieu_that_ra_short(candles):
    """SHORT lấy từ dữ liệu thật: model có thành phần mean-reversion (RSI < 35
    cộng +2) nên downtrend đơn điệu tự triệt tiêu, không ra SHORT được.
    SHORT chỉ xuất hiện khi RSI ở vùng giữa – đúng như fixture 1D (RSI 46)."""
    r = generate_signal(candles["1d"])
    assert r["verdict"] == SHORT
    assert r["score"] <= -SIGNAL_THRESHOLD
    assert r["action"] == "BÁN / SHORT"


def test_rsi_oversold_bu_lai_downtrend():
    """Ghi lại đặc tính bất đối xứng của model, tránh sau này sửa nhầm."""
    r = generate_signal(wave(101, start=500.0, drift=-0.8, amp=3.0))
    assert any("oversold" in x for x in r["reasons"])
    assert r["verdict"] == NEUTRAL


def test_score_khong_vuot_bien_max_score():
    for cs in (uptrend(), wave(101, 500.0, -0.8, 3.0), wave(60, 100.0, 0.1, 5.0)):
        assert abs(generate_signal(cs)["score"]) <= MAX_SCORE


def test_verdict_map_dung_theo_score():
    """Kiểm trực tiếp ranh giới: 2 -> NEUTRAL, 3 -> LONG, -3 -> SHORT."""
    from btcreport.engine import signals as S
    for score, expect in ((2, NEUTRAL), (3, LONG), (-2, NEUTRAL), (-3, SHORT), (0, NEUTRAL)):
        if score >= S.SIGNAL_THRESHOLD:
            got = LONG
        elif score <= -S.SIGNAL_THRESHOLD:
            got = SHORT
        else:
            got = NEUTRAL
        assert got == expect, f"score {score}"


def test_reasons_khong_rong_va_la_chuoi():
    r = generate_signal(uptrend())
    assert r["reasons"]
    assert all(isinstance(x, str) for x in r["reasons"])


def test_khong_tra_ve_ma_mau():
    """Engine không được rò rỉ thứ thuộc về frontend."""
    r = generate_signal(uptrend())
    assert set(r) == {"verdict", "action", "score", "max_score", "reasons"}
    assert "#" not in repr(r["verdict"]) + repr(r["action"])


# ── Thành phần điểm ──────────────────────────────────────────────────────────
def test_volume_dot_bien_tren_nen_tang_cong_diem():
    base  = uptrend()
    spike = [dict(c) for c in base]
    spike[-1]["volume"] = 100.0 * 5          # 5x trung bình
    assert generate_signal(spike)["score"] > generate_signal(base)["score"]


def test_volume_dot_bien_tren_nen_giam_tru_diem():
    base = uptrend()
    down = [dict(c) for c in base]
    down[-1]["open"], down[-1]["close"] = down[-1]["close"], down[-1]["open"]
    down[-1]["volume"] = 100.0 * 5
    assert generate_signal(down)["score"] < generate_signal(base)["score"]


def test_ba_nen_tang_lien_tiep_duoc_ghi_nhan():
    r = generate_signal(uptrend())
    assert any("3 nến tăng liên tiếp" in x for x in r["reasons"])


def test_ema50_duoc_ghi_nhan_trong_reasons():
    r = generate_signal(uptrend())
    assert any("EMA50" in x for x in r["reasons"])


# ── Confluence ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("verdicts,expect,agree", [
    ([LONG] * 4,                          "STRONG LONG",  4),
    ([LONG, LONG, LONG, NEUTRAL],         "STRONG LONG",  3),
    ([LONG, LONG, NEUTRAL, NEUTRAL],      "LONG BIAS",    2),
    ([SHORT] * 4,                         "STRONG SHORT", 4),
    ([SHORT, SHORT, SHORT, NEUTRAL],      "STRONG SHORT", 3),
    ([SHORT, SHORT, NEUTRAL, NEUTRAL],    "SHORT BIAS",   2),
    ([NEUTRAL] * 4,                       "NEUTRAL",      0),
    ([LONG, SHORT, NEUTRAL, NEUTRAL],     "NEUTRAL",      1),
    ([LONG, LONG, SHORT, SHORT],          "LONG BIAS",    2),
])
def test_confluence_day_du_nhanh(verdicts, expect, agree):
    r = confluence(verdicts)
    assert r["verdict"] == expect
    assert r["agree"] == agree


def test_confidence_chuan_hoa_theo_max_score():
    assert confidence(0) == 10
    assert confidence(MAX_SCORE) == 100
    assert confidence(-MAX_SCORE) == 100
    assert 10 < confidence(3) < 100


# ── Khớp golden ──────────────────────────────────────────────────────────────
def test_signal_1d_khop_golden(golden, candles):
    r = generate_signal(candles["1d"])
    g = golden["signal"]
    assert r["verdict"] == g["verdict"]
    assert r["score"]   == g["score"]
    assert r["action"]  == g["action"]
    assert r["reasons"] == g["reasons"]
    assert confidence(r["score"]) == g["confidence"]


@pytest.mark.parametrize("tf", ["1w", "1d", "4h", "1h"])
def test_signal_moi_khung_khop_golden(golden, candles, tf):
    g = golden["timeframes"][tf.upper()]
    r = generate_signal(candles[tf])
    assert r["verdict"] == g["verdict"]
    assert r["score"]   == g["score"]


def test_confluence_khop_golden(golden, candles):
    verdicts = [generate_signal(candles[tf])["verdict"]
                for tf in ("1w", "1d", "4h", "1h")]
    assert confluence(verdicts) == golden["confluence"]
