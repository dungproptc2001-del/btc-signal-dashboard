"""Jinja filter: định dạng số và map verdict sang class CSS.

Toàn bộ chuyện "LONG thì màu gì" nằm ở đây và trong styles.css – engine không
biết gì về màu.
"""

_VERDICT_SLUG = {
    "LONG": "long", "SHORT": "short", "NEUTRAL": "neutral", "N/A": "na",
    "STRONG LONG": "long", "LONG BIAS": "long",
    "STRONG SHORT": "short", "SHORT BIAS": "short",
}

_VERDICT_ICON = {
    "LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "🟡", "N/A": "⚪",
    "STRONG LONG": "🟢🟢", "LONG BIAS": "🟢",
    "STRONG SHORT": "🔴🔴", "SHORT BIAS": "🔴",
}


def usd(v):
    """63739.24 -> $63,739"""
    return "—" if v is None else f"${v:,.0f}"


def usd2(v):
    """63739.24 -> $63,739.24"""
    return "—" if v is None else f"${v:,.2f}"


def num(v, digits=0):
    return "—" if v is None else f"{v:,.{digits}f}"


def pct(v, digits=2):
    return "—" if v is None else f"{v:.{digits}f}%"


def signed_pct(v, digits=2):
    return "—" if v is None else f"{'+' if v >= 0 else ''}{v:.{digits}f}%"


def signed(v):
    return "—" if v is None else f"{'+' if v > 0 else ''}{v}"


def verdict_slug(verdict):
    return _VERDICT_SLUG.get(verdict, "neutral")


def verdict_class(verdict):
    """Class dùng cho container: v-long / v-short / v-neutral / v-na"""
    return "v-" + verdict_slug(verdict)


def verdict_color_class(verdict):
    """Class chỉ tô chữ: c-long / c-short / ..."""
    return "c-" + verdict_slug(verdict)


def verdict_icon(verdict):
    return _VERDICT_ICON.get(verdict, "🟡")


def pill_class(up):
    return "pill-green" if up else "pill-red"


def rsi_class(v):
    if v is None:
        return "rsi-mid"
    return "rsi-hot" if v > 70 else "rsi-cold" if v < 30 else "rsi-mid"


def fg_class(v):
    if v is None:
        return "muted"
    return "c-short" if v < 25 else "c-neutral" if v < 50 else \
           "c-long" if v > 75 else "muted"


def datetime_fmt(dt, fmt="%d/%m/%Y %H:%M:%S"):
    return dt.strftime(fmt)


def round_series(seq, digits=2):
    """Làm gọn series trước khi tojson – file HTML nhỏ đi đáng kể."""
    return [None if v is None else round(v, digits) for v in seq]


ALL = {
    "usd": usd, "usd2": usd2, "num": num, "pct": pct,
    "signed_pct": signed_pct, "signed": signed,
    "verdict_class": verdict_class, "verdict_color_class": verdict_color_class,
    "verdict_slug": verdict_slug, "verdict_icon": verdict_icon,
    "pill_class": pill_class, "rsi_class": rsi_class, "fg_class": fg_class,
    "datetime_fmt": datetime_fmt, "round_series": round_series,
}
