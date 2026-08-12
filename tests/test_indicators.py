"""Chỉ báo: đúng công thức trên chuỗi tính tay, và khớp golden trên dữ liệu thật."""
import pytest

from btcreport.engine.indicators import (
    atr, bollinger, ema, last_valid, macd_line, rsi, sma,
)

APPROX = dict(rel=1e-9)


# ── Chuỗi nhỏ, kết quả tính tay ──────────────────────────────────────────────
def test_sma_basic():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_giu_do_dai_input():
    closes = list(range(50))
    assert len(sma(closes, 7)) == len(closes)
    assert sma(closes, 7)[:6] == [None] * 6


def test_ema_seed_bang_sma():
    # Phần tử đầu tiên có giá trị của EMA phải bằng SMA cùng chu kỳ
    closes = [1, 2, 3, 4, 5, 6]
    assert ema(closes, 3)[2] == pytest.approx(2.0, **APPROX)
    # k = 2/(3+1) = 0.5 → EMA[3] = 4*0.5 + 2*0.5 = 3.0
    assert ema(closes, 3)[3] == pytest.approx(3.0, **APPROX)


def test_rsi_tang_lien_tuc_bang_100():
    closes = list(range(1, 40))
    assert last_valid(rsi(closes)) == pytest.approx(100.0, **APPROX)


def test_rsi_thieu_du_lieu_tra_toan_none():
    assert rsi([1, 2, 3], period=14) == [None, None, None]


def test_rsi_nam_trong_khoang_0_100():
    closes = [100, 102, 101, 105, 103, 108, 107, 110, 109, 112,
              111, 115, 113, 118, 116, 120, 119, 122, 121, 125]
    for v in rsi(closes):
        if v is not None:
            assert 0 <= v <= 100


def test_bollinger_thu_tu_upper_mid_lower():
    closes = [10] * 25
    upper, mid, lower = bollinger(closes, n=20)
    # Chuỗi phẳng → sd = 0 → ba dải trùng nhau
    assert upper[-1] == mid[-1] == lower[-1] == pytest.approx(10.0, **APPROX)
    assert upper[:19] == [None] * 19


def test_bollinger_upper_luon_lon_hon_lower():
    closes = [10, 12, 9, 15, 11, 14, 8, 16, 12, 13,
              11, 15, 10, 14, 12, 16, 11, 13, 12, 14, 15]
    upper, mid, lower = bollinger(closes)
    assert upper[-1] > mid[-1] > lower[-1]


def test_macd_tra_ba_series_cung_do_dai():
    closes = [float(i) for i in range(60)]
    macd, signal, hist = macd_line(closes)
    assert len(macd) == len(signal) == len(hist) == 60


def test_atr_chuoi_phang_bang_0():
    candles = [{"high": 10, "low": 10, "close": 10} for _ in range(20)]
    assert atr(candles) == 0.0


def test_atr_bien_do_co_dinh():
    # Mỗi nến cao-thấp lệch 2, close không đổi → TR = 2
    candles = [{"high": 11, "low": 9, "close": 10} for _ in range(20)]
    assert atr(candles) == pytest.approx(2.0, **APPROX)


def test_atr_it_hon_2_nen_tra_0():
    assert atr([{"high": 1, "low": 1, "close": 1}]) == 0.0


def test_last_valid_bo_qua_none_o_duoi():
    assert last_valid([1, 2, 3, None, None]) == 3
    assert last_valid([None, None], default=50) == 50


# ── Dữ liệu thật: phải khớp golden của code trước refactor ───────────────────
@pytest.mark.parametrize("key,fn", [
    ("sma7",  lambda c: sma(c, 7)),
    ("sma25", lambda c: sma(c, 25)),
    ("sma99", lambda c: sma(c, 99)),
    ("ema50", lambda c: ema(c, 50)),
    ("rsi",   rsi),
])
def test_khop_golden_series(golden, candles, key, fn):
    closes = [c["close"] for c in candles["1d"]]
    assert fn(closes) == pytest.approx(golden["indicators"][key], **APPROX)


def test_khop_golden_macd(golden, candles):
    closes = [c["close"] for c in candles["1d"]]
    macd, signal, hist = macd_line(closes)
    assert macd   == pytest.approx(golden["indicators"]["macd"], **APPROX)
    assert signal == pytest.approx(golden["indicators"]["macd_signal"], **APPROX)
    assert hist   == pytest.approx(golden["indicators"]["macd_hist"], **APPROX)


def test_khop_golden_bollinger(golden, candles):
    closes = [c["close"] for c in candles["1d"]]
    upper, mid, lower = bollinger(closes)
    assert upper == pytest.approx(golden["indicators"]["bb_upper"], **APPROX)
    assert mid   == pytest.approx(golden["indicators"]["bb_mid"], **APPROX)
    assert lower == pytest.approx(golden["indicators"]["bb_lower"], **APPROX)


def test_khop_golden_atr(golden, candles):
    assert atr(candles["1d"]) == pytest.approx(golden["atr_daily"], **APPROX)
