"""build_context: khớp golden của code trước refactor, và giữ đúng ranh giới tầng."""
import json
from datetime import datetime

import pytest

from btcreport.engine.analysis import build_context, get_thu_range

APPROX = dict(rel=1e-9)


@pytest.fixture(scope="session")
def ctx(raw, candles):
    meta = raw["meta"]
    return build_context(
        symbol=meta["symbol"],
        now=datetime.fromisoformat(meta["now"]),
        daily=candles["1d"], weekly=candles["1w"],
        h4=candles["4h"], h1=candles["1h"],
        ticker=raw["ticker"],
        fear_greed=(raw["fg"]["value"], raw["fg"]["label"]),
        week_candles=candles["week"],
        week_start=datetime.fromisoformat(meta["week_start"]),
        week_end=datetime.fromisoformat(meta["week_end"]),
    )


# ── Khớp golden ──────────────────────────────────────────────────────────────
def test_signal_khop_golden(ctx, golden):
    g = golden["signal"]
    assert ctx["signal"]["verdict"]    == g["verdict"]
    assert ctx["signal"]["score"]      == g["score"]
    assert ctx["signal"]["action"]     == g["action"]
    assert ctx["signal"]["reasons"]    == g["reasons"]
    assert ctx["signal"]["confidence"] == g["confidence"]


def test_confluence_khop_golden(ctx, golden):
    assert ctx["confluence"] == golden["confluence"]


@pytest.mark.parametrize("i,label", [(0, "1W"), (1, "1D"), (2, "4H"), (3, "1H")])
def test_timeframes_khop_golden(ctx, golden, i, label):
    tf = ctx["timeframes"][i]
    g  = golden["timeframes"][label]
    assert tf["label"]     == label
    assert tf["verdict"]   == g["verdict"]
    assert tf["score"]     == g["score"]
    assert tf["macd_bull"] == g["macd_bull"]
    assert tf["rsi"]  == pytest.approx(g["rsi"], **APPROX)
    assert tf["macd"] == pytest.approx(g["macd"], **APPROX)


def test_levels_khop_golden(ctx, golden):
    assert ctx["levels"]    == pytest.approx(golden["levels"], **APPROX)
    assert ctx["levels_4h"] == pytest.approx(golden["levels_4h"], **APPROX)


def test_risk_khop_golden(ctx, golden):
    for k, v in golden["risk"].items():
        assert ctx["risk"][k] == pytest.approx(v, **APPROX) if v is not None \
            else ctx["risk"][k] is None


def test_atr_khop_golden(ctx, golden):
    assert ctx["current"]["atr"] == pytest.approx(golden["atr_daily"], **APPROX)


def test_chart_series_khop_golden(ctx, golden):
    d = ctx["chart"]["daily"]
    g = golden["indicators"]
    assert d["ma7"]         == pytest.approx(g["sma7"],  **APPROX)
    assert d["ma25"]        == pytest.approx(g["sma25"], **APPROX)
    assert d["ma99"]        == pytest.approx(g["sma99"], **APPROX)
    assert d["rsi"]         == pytest.approx(g["rsi"],   **APPROX)
    assert d["macd"]        == pytest.approx(g["macd"],  **APPROX)
    assert d["macd_signal"] == pytest.approx(g["macd_signal"], **APPROX)
    assert d["bb_upper"]    == pytest.approx(g["bb_upper"], **APPROX)


def test_so_luong_nen_khop_golden(ctx, golden):
    c = golden["counts"]
    assert len(ctx["chart"]["daily"]["close"]) == c["daily"]
    assert len(ctx["chart"]["h4"]["close"])    == c["h4"]
    assert len(ctx["chart"]["h1"]["close"])    == c["h1"]
    assert ctx["week"]["days"] == c["week"]


# ── Ranh giới tầng ───────────────────────────────────────────────────────────
def test_context_khong_chua_html_hay_ma_mau(ctx):
    blob = json.dumps(ctx, default=str)
    for banned in ("<div", "<span", "<strong", "#00c853", "#d50000", "#ffa000"):
        assert banned not in blob, f"context rò rỉ {banned!r} – đó là việc của frontend"


def test_context_json_dump_duoc(ctx):
    json.dumps(ctx, default=str)      # không raise


def test_cac_khoa_bat_buoc_deu_co(ctx):
    assert set(ctx) >= {"symbol", "generated_at", "price", "fear_greed", "week",
                        "signal", "timeframes", "confluence", "levels",
                        "levels_4h", "risk", "current", "chart", "ohlcv"}


def test_ohlcv_14_dong_cuoi(ctx, candles):
    assert len(ctx["ohlcv"]) == 14
    assert ctx["ohlcv"][-1]["close"] == candles["1d"][-1]["close"]


def test_khung_thieu_du_lieu_tra_na():
    from btcreport.engine.analysis import analyze_timeframe
    tf = analyze_timeframe("4H", [])
    assert tf["verdict"] == "N/A" and tf["score"] == 0


# ── get_thu_range ────────────────────────────────────────────────────────────
def test_thu_range_cach_nhau_7_ngay():
    start, end = get_thu_range()
    assert (end - start).days == 7


def test_thu_range_roi_dung_vao_thu_5():
    start, end = get_thu_range()
    assert start.weekday() == 3 and end.weekday() == 3


def test_thu_range_hom_nay_la_thu_5_thi_end_la_hom_nay():
    from datetime import timezone
    thursday = datetime(2026, 8, 6, 10, 30, tzinfo=timezone.utc)   # thứ 5
    start, end = get_thu_range(thursday)
    assert end.date() == thursday.date()
    assert start.date() == datetime(2026, 7, 30).date()
