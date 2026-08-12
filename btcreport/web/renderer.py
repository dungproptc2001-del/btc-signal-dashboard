"""Render context dict thành một file HTML tự chứa.

Không tính toán gì – chỉ định dạng và sắp xếp. Mọi con số đã có sẵn trong context.
CSS và JS được inline lúc render để file mở được bằng double-click, không cần server.
"""
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from . import filters

WEB_DIR       = Path(__file__).resolve().parent
TEMPLATE_DIR  = WEB_DIR / "templates"
STATIC_DIR    = WEB_DIR / "static"

# Series chart làm tròn 2 chữ số trước khi serialize – file HTML nhỏ đi đáng kể
# mà biểu đồ không đổi một pixel.
_CHART_DIGITS = 2


def _env():
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,   # thiếu biến thì lỗi ngay, không render ra rỗng
    )
    env.filters.update(filters.ALL)
    return env


def _round_chart(chart):
    """Làm tròn mọi series số trong nhánh chart."""
    out = {}
    for tf, series in chart.items():
        out[tf] = {
            key: (values if key == "labels"
                  else [None if v is None else round(v, _CHART_DIGITS) for v in values])
            for key, values in series.items()
        }
    return out


def _static(name):
    with open(STATIC_DIR / name, encoding="utf-8") as f:
        return f.read()


def render_report(ctx):
    week_label = (f"{ctx['week']['start'].strftime('%d/%m/%Y')} – "
                  f"{ctx['week']['end'].strftime('%d/%m/%Y')}")

    return _env().get_template("report.html").render(
        **ctx,
        week_label=week_label,
        chart_json=Markup(json.dumps(_round_chart(ctx["chart"]),
                                     ensure_ascii=False, separators=(",", ":"))),
        inline_css=Markup(_static("styles.css")),
        inline_js=Markup(_static("charts.js")),
    )
