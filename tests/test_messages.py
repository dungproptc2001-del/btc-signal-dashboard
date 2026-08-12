"""Text Telegram phải khớp byte-for-byte với bản trước refactor."""
from datetime import datetime

import pytest

from btcreport.engine.analysis import build_context
from btcreport.notify.messages import (
    format_fetch_failure, format_monitor_alert, format_monitor_startup,
    format_report_message, icon,
)


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


def test_tin_bao_cao_khop_golden_tuyet_doi(ctx, golden_telegram):
    assert format_report_message(ctx) == golden_telegram


def test_icon_dung_mau():
    assert icon("LONG") == "🟢"
    assert icon("SHORT") == "🔴"
    assert icon("NEUTRAL") == "🟡"
    assert icon("STRONG LONG") == "🟢🟢"
    assert icon("SHORT BIAS") == "🔴"


def test_setup_neutral_khong_de_xuat_entry(ctx):
    neutral = {**ctx, "risk": {**ctx["risk"], "sl": None, "tp": None, "rr": None}}
    msg = format_report_message(neutral)
    assert "chưa vào lệnh" in msg
    assert "Entry $" not in msg


# ── Alert của monitor ────────────────────────────────────────────────────────
def _snapshot(ctx):
    return {
        "confluence": ctx["confluence"],
        "timeframes": ctx["timeframes"],
        "levels":     ctx["levels_4h"],
        "risk":       ctx["risk"],
        "price":      ctx["price"]["last"],
        "change_24h": ctx["price"]["change_24h"],
    }


def test_alert_lan_dau_khong_co_mui_ten(ctx):
    msg = format_monitor_alert("BTC", "", _snapshot(ctx), "12/08/2026 15:00")
    assert "Trạng thái ban đầu" in msg
    assert "→" not in msg.split("\n\n")[2]


def test_alert_doi_trang_thai_co_mui_ten(ctx):
    msg = format_monitor_alert("BTC", "NEUTRAL", _snapshot(ctx), "12/08/2026 15:00")
    assert "Signal thay đổi!" in msg
    assert "→" in msg


def test_alert_liet_ke_du_4_khung(ctx):
    msg = format_monitor_alert("ETH", "NEUTRAL", _snapshot(ctx), "12/08/2026 15:00")
    for label in ("1W", "1D", "4H", "1H"):
        assert f" {label}  " in msg


def test_alert_khong_ket_thuc_bang_dong_trong(ctx):
    msg = format_monitor_alert("BTC", "", _snapshot(ctx), "12/08/2026 15:00")
    assert msg == msg.rstrip()


def test_tin_khoi_dong(ctx):
    msg = format_monitor_startup(["BTC", "ETH", "XAU"], 15, 2)
    assert "BTC, ETH, XAU" in msg and "15 phút" in msg and "2 lần quét" in msg


def test_tin_bao_loi_fetch():
    msg = format_fetch_failure("XAU", 4, 15)
    assert "XAU" in msg and "4 lần liên tiếp" in msg and "~60 phút" in msg
