"""Vùng hỗ trợ/kháng cự và mức quản lý rủi ro."""
import pytest

from btcreport.engine.levels import risk_levels, support_resistance

APPROX = dict(rel=1e-9)


def flat(n=25, price=100.0, spread=2.0):
    return [{"ts": i, "open": price, "high": price + spread,
             "low": price - spread, "close": price, "volume": 10.0}
            for i in range(n)]


# ── support_resistance ───────────────────────────────────────────────────────
def test_pivot_dung_cong_thuc():
    c = flat()          # high 102, low 98, close 100
    r = support_resistance(c)
    assert r["pivot"] == pytest.approx((102 + 98 + 100) / 3, **APPROX)
    assert r["R1"] == pytest.approx(2 * r["pivot"] - 98, **APPROX)
    assert r["S1"] == pytest.approx(2 * r["pivot"] - 102, **APPROX)
    assert r["R2"] == pytest.approx(r["pivot"] + (102 - 98), **APPROX)
    assert r["S2"] == pytest.approx(r["pivot"] - (102 - 98), **APPROX)


def test_thu_tu_cac_muc():
    r = support_resistance(flat())
    assert r["S2"] < r["S1"] < r["pivot"] < r["R1"] < r["R2"]


def test_chi_dung_lookback_nen_cuoi():
    old = [{"ts": i, "open": 1, "high": 9999, "low": 1, "close": 1, "volume": 1}
           for i in range(30)]
    r = support_resistance(old + flat(20), lookback=20)
    assert r["R2"] < 1000       # nến cũ high 9999 không được lọt vào


# ── risk_levels ──────────────────────────────────────────────────────────────
def test_long_thi_sl_duoi_entry_tp_tren():
    r = risk_levels(flat(), "LONG")
    assert r["sl"] < r["entry"] < r["tp"]
    assert r["rr"] == pytest.approx(2.0, **APPROX)


def test_short_thi_nguoc_lai():
    r = risk_levels(flat(), "SHORT")
    assert r["tp"] < r["entry"] < r["sl"]


def test_neutral_khong_de_xuat_gi():
    r = risk_levels(flat(), "NEUTRAL")
    assert r["sl"] is None and r["tp"] is None and r["rr"] is None
    assert r["entry"] == 100.0


def test_na_cung_khong_de_xuat():
    assert risk_levels(flat(), "N/A")["sl"] is None


def test_atr_bang_0_thi_khong_de_xuat():
    """Chuỗi phẳng tuyệt đối → ATR = 0 → SL/TP vô nghĩa."""
    c = [{"ts": i, "open": 100, "high": 100, "low": 100, "close": 100, "volume": 1}
         for i in range(25)]
    assert risk_levels(c, "LONG")["sl"] is None


def test_khoang_cach_sl_tp_theo_ty_le_atr():
    r = risk_levels(flat(), "LONG")
    assert (r["entry"] - r["sl"]) == pytest.approx(1.5 * r["atr"], **APPROX)
    assert (r["tp"] - r["entry"]) == pytest.approx(3.0 * r["atr"], **APPROX)


# ── Khớp golden ──────────────────────────────────────────────────────────────
def test_levels_khop_golden(golden, candles):
    assert support_resistance(candles["1d"]) == pytest.approx(golden["levels"], **APPROX)
    assert support_resistance(candles["4h"]) == pytest.approx(golden["levels_4h"], **APPROX)


def test_risk_khop_golden(golden, candles):
    from btcreport.engine.signals import generate_signal
    r = risk_levels(candles["1d"], generate_signal(candles["1d"])["verdict"])
    for k, v in golden["risk"].items():
        if v is None:
            assert r[k] is None
        else:
            assert r[k] == pytest.approx(v, **APPROX)
