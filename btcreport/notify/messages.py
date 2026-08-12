"""Soạn text cho Telegram.

Đây là "frontend" của kênh Telegram: emoji, xuống dòng, canh cột nằm ở đây,
không nằm trong engine.
"""
ICON = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "🟡", "N/A": "⚪",
        "STRONG LONG": "🟢🟢", "LONG BIAS": "🟢",
        "STRONG SHORT": "🔴🔴", "SHORT BIAS": "🔴"}


def icon(verdict):
    return ICON.get(verdict, "🟡")


def _setup_block(risk, title, verdict, digits=0):
    """Khối Entry/SL/TP. NEUTRAL thì nói thẳng là chưa vào lệnh."""
    if not risk["sl"]:
        return f"📐 {title}: NEUTRAL – chưa vào lệnh, chờ xác nhận\n"
    d = digits
    return (f"📐 {title} ({verdict})\n"
            f"   Entry ${risk['entry']:,.{d}f}\n"
            f"   SL    ${risk['sl']:,.{d}f}\n"
            f"   TP    ${risk['tp']:,.{d}f}   (R:R 1:{risk['rr']:.0f})\n")


def format_report_message(ctx):
    """Tin nhắn kèm báo cáo 4 tiếng/lần."""
    p    = ctx["price"]
    fg   = ctx["fear_greed"]
    conf = ctx["confluence"]
    lv   = ctx["levels_4h"]
    tfs  = ctx["timeframes"]
    now  = ctx["generated_at"].strftime("%d/%m/%Y %H:%M")

    lines = "".join(
        f"{icon(tf['verdict'])} {tf['label']}  {tf['verdict']:<7}  "
        f"RSI {tf['rsi']:.0f}  MACD {'▲' if tf['macd_bull'] else '▼'}\n"
        for tf in tfs
    )

    return (
        f"🔶 BTC/USDT – Multi-Timeframe\n"
        f"⏰ {now}\n\n"
        f"💰 Giá: ${p['last']:,.0f}  "
        f"({'+' if p['change_24h'] >= 0 else ''}{p['change_24h']:.2f}% 24h)\n"
        f"😱 Fear & Greed: {fg['value']} – {fg['label']}\n\n"
        f"━━━━ CONFLUENCE ━━━━\n"
        f"{icon(conf['verdict'])} {conf['verdict']}  ({conf['agree']}/4 đồng thuận)\n\n"
        f"{lines}\n"
        f"🎯 R1: ${lv['R1']:,.0f}  |  R2: ${lv['R2']:,.0f}\n"
        f"🛡  S1: ${lv['S1']:,.0f}  |  S2: ${lv['S2']:,.0f}\n\n"
        + _setup_block(ctx["risk"], "Setup 1D", tfs[1]["verdict"])
        + f"━━━━━━━━━━━━━━━━━━━━\n"
          f"⚠️ Chỉ tham khảo. Quản lý rủi ro!"
    )


def format_monitor_alert(name, prev, snap, now):
    """Alert khi confluence của một mã đổi trạng thái."""
    conf  = snap["confluence"]["verdict"]
    ci    = icon(conf)
    tfs   = snap["timeframes"]
    lv    = snap["levels"]
    is_new = not prev

    header   = (f"📊 {name} – Trạng thái ban đầu" if is_new
                else f"⚡ {name} – Signal thay đổi!")
    chg_line = "" if is_new else f"{icon(prev)} {prev}  →  {ci} {conf}\n\n"
    tf_lines = "".join(f"{icon(tf['verdict'])} {tf['label']}  {tf['verdict']}\n"
                       for tf in tfs)

    setup = _setup_block(snap["risk"], "Setup 4H", tfs[2]["verdict"], digits=2)

    return (
        f"{header}\n"
        f"⏰ {now}\n\n"
        f"💰 Giá: ${snap['price']:,.2f}  "
        f"({'+' if snap['change_24h'] >= 0 else ''}{snap['change_24h']:.2f}%)\n\n"
        f"{chg_line}"
        f"{ci} {conf}\n\n"
        f"{tf_lines}\n"
        f"🎯 R1: ${lv['R1']:,.2f}   🛡 S1: ${lv['S1']:,.2f}\n\n"
        f"{setup}".rstrip()
    )


def format_monitor_startup(symbols, interval_min, confirm_scans):
    return (f"🚀 Signal Monitor khởi động\n"
            f"Theo dõi: {', '.join(symbols)}\n"
            f"Quét mỗi {interval_min} phút – alert khi signal đổi "
            f"và giữ được {confirm_scans} lần quét.")


def format_fetch_failure(name, fails, interval_min):
    return (f"⚠️ {name} – không lấy được dữ liệu {fails} lần liên tiếp "
            f"(~{fails * interval_min} phút).\n"
            f"Signal đang dừng cập nhật cho mã này. Kiểm tra mạng / Binance API.")


def format_report_error(exc):
    return f"❌ BTC Report lỗi\n{type(exc).__name__}: {exc}"
