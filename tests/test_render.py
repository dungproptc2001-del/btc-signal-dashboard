"""Renderer: render được, đủ thành phần, và không rò rỉ cú pháp template."""
import json
import re
from datetime import datetime

import pytest

from btcreport.engine.analysis import build_context
from btcreport.web.renderer import render_report


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


@pytest.fixture(scope="session")
def html(ctx):
    return render_report(ctx)


def test_render_khong_loi(html):
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")


def test_khong_sot_cu_phap_jinja(html):
    assert "{{" not in html
    assert "{%" not in html
    assert "Undefined" not in html


def test_khong_con_entity_hong(html):
    """&#₿; là entity không hợp lệ, browser in ra chữ thô."""
    assert "&#₿;" not in html
    assert "&#8383;" in html


def test_du_cac_canvas(html):
    for cid in ("priceChart", "rsiChart", "macdChart", "volChart", "chart4h", "chart1h"):
        assert f'id="{cid}"' in html, f"thiếu canvas {cid}"


def test_co_du_4_the_khung(html):
    assert html.count('class="tf-card') == 4
    for label in ("1W", "1D", "4H", "1H"):
        assert f">{label}</div>" in html


def test_co_khoi_quan_ly_rui_ro(html):
    assert "Quản lý rủi ro (ATR)" in html


def test_khoi_rui_ro_khop_voi_verdict(ctx, html):
    if ctx["risk"]["sl"]:
        assert "Stop Loss" in html and "Take Profit" in html
    else:
        assert "không đề xuất entry" in html


def test_bang_ohlcv_du_dong(ctx, html):
    assert html.count("<tr>") == len(ctx["ohlcv"]) + 1      # +1 dòng tiêu đề


def test_css_va_js_duoc_inline(html):
    assert ".verdict-box{" in html          # từ styles.css
    assert "window.REPORT_DATA" in html     # dữ liệu chart
    assert "new Chart(" in html             # từ charts.js


def test_chart_data_la_json_hop_le(ctx, html):
    m = re.search(r"window\.REPORT_DATA = (.*?);\n", html, re.S)
    assert m, "không tìm thấy REPORT_DATA"
    data = json.loads(m.group(1))
    assert set(data) == {"daily", "h4", "h1"}
    assert len(data["daily"]["close"]) == len(ctx["chart"]["daily"]["close"])
    assert len(data["h4"]["close"])    == len(ctx["chart"]["h4"]["close"])


def test_gia_va_verdict_hien_dung(ctx, html):
    assert f"${ctx['price']['last']:,.0f}" in html
    assert ctx["signal"]["verdict"] in html
    assert ctx["confluence"]["verdict"] in html


def test_moi_ly_do_deu_xuat_hien(ctx, html):
    for reason in ctx["signal"]["reasons"]:
        # Jinja autoescape đổi & thành &amp; nên so phần đầu cho chắc
        assert reason.split(" (")[0][:20] in html


def test_thieu_bien_thi_bao_loi_ngay(ctx):
    """StrictUndefined: template dùng biến không có phải nổ, không render rỗng."""
    from jinja2 import UndefinedError
    broken = dict(ctx)
    del broken["levels"]
    with pytest.raises((UndefinedError, KeyError, TypeError)):
        render_report(broken)


def test_html_khong_qua_lon(html):
    """Làm tròn series giữ file gọn – phình to là dấu hiệu serialize sai."""
    assert len(html) < 200_000
