"""Bot Telegram: duyệt truy cập bằng nút bấm + lệnh điều khiển server.

Dùng long-poll getUpdates chứ không dùng webhook. Lý do: webhook cần Telegram gọi
ngược vào máy, tunnel sập là mất luôn đường duyệt. Long-poll thì server chủ động gọi
ra, tunnel có sập vẫn duyệt được.

TOÀN BỘ lệnh và callback đi qua đúng MỘT cửa kiểm `access.is_owner()`. Bot công khai,
ai cũng nhắn được — không kiểm là người lạ điều khiển được server.
"""
import asyncio
import traceback
from datetime import datetime

import requests

from ..config import (
    GUEST_TTL_DAYS, OWNER_KEY, SCAN_INTERVAL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
)
from . import access
from .state import STATE

API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Người lạ nhắn bot chỉ nhận đúng câu này – không lộ có gì phía sau
STRANGER_REPLY = "Bot này dùng riêng. Nếu bạn cần xem báo cáo, hãy mở link được chia sẻ."

_stop_event = None
_task = None


# ── GỌI API ───────────────────────────────────────────────────────────────────
def _post(method, payload, timeout=15):
    try:
        r = requests.post(f"{API}/{method}", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [bot] {method} lỗi: {e}")
        return None


def send(text, chat_id=None, buttons=None, preview=False):
    payload = {"chat_id": chat_id or TELEGRAM_CHAT_ID, "text": text,
               "disable_web_page_preview": not preview}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return _post("sendMessage", payload)


def _answer_callback(cb_id, text=""):
    _post("answerCallbackQuery", {"callback_query_id": cb_id, "text": text})


def _edit_text(chat_id, message_id, text):
    _post("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                              "text": text, "reply_markup": {"inline_keyboard": []}})


# ── THÔNG BÁO YÊU CẦU TRUY CẬP ────────────────────────────────────────────────
def notify_access_request(req):
    """Gửi yêu cầu kèm 2 nút cho chủ nhà."""
    text = (
        f"🔐 Yêu cầu truy cập\n\n"
        f"👤 Tên: {req['name']}\n"
        f"💬 Lời nhắn: {req['message']}\n\n"
        f"🌐 IP: {req['ip']}\n"
        f"🖥 {req['ua'][:80]}\n"
        f"⏰ {datetime.now():%d/%m/%Y %H:%M}"
    )
    buttons = [[
        {"text": f"✅ Duyệt {GUEST_TTL_DAYS} ngày", "callback_data": f"approve:{req['id']}"},
        {"text": "❌ Từ chối",                      "callback_data": f"deny:{req['id']}"},
    ]]
    return send(text, buttons=buttons)


def notify_startup(url, port):
    lines = ["🚀 BTC Web Server đã bật", ""]
    if url:
        lines += [f"🌍 Công khai: {url}",
                  f"🔑 Vào thẳng: {url}/login?key={OWNER_KEY}", ""]
    else:
        lines += ["🏠 Chỉ chạy nội bộ (không có tunnel)", ""]
    lines += [f"💻 Trong máy: http://localhost:{port}",
              "", "Gõ /help để xem lệnh điều khiển."]
    send("\n".join(lines))


# ── LỆNH ──────────────────────────────────────────────────────────────────────
def _fmt_duration(seconds):
    h, m = divmod(int(seconds) // 60, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d} ngày {h} giờ"
    return f"{h} giờ {m} phút" if h else f"{m} phút"


def _cmd_status():
    s = STATE.public()["status"]
    if s["standby"]:
        muc = "🔌 ĐANG NGHỈ – link công khai đã đóng (/on để bật lại)"
    elif s["paused"]:
        muc = "⏸ ĐANG TẠM DỪNG quét (web vẫn sống)"
    else:
        muc = "▶️ Đang chạy bình thường"

    lines = [
        "📊 Trạng thái server", "",
        f"⏱ Sống được: {_fmt_duration(s['uptime_seconds'])}",
        muc,
        f"👀 Tab đang mở: {s['viewers']}",
        "",
        f"💰 Giá cập nhật:  {s['last_price_at'] or '—'}",
        f"🔍 Quét gần nhất: {s['last_scan_at'] or '—'}",
        f"📄 Báo cáo:       {s['last_report_at'] or '—'}",
        "",
        f"🔐 Khách có quyền: {len(access.list_guests())}",
    ]
    if STATE.tunnel_url:
        lines += ["", f"🌍 {STATE.tunnel_url}"]
    return "\n".join(lines)


def _cmd_url():
    if not STATE.tunnel_url:
        return "Không có tunnel. Server chỉ chạy nội bộ."
    return (f"🌍 Link công khai:\n{STATE.tunnel_url}\n\n"
            f"🔑 Link vào thẳng của ông:\n{STATE.tunnel_url}/login?key={OWNER_KEY}")


def _cmd_guests():
    guests = access.list_guests()
    if not guests:
        return "Chưa có khách nào đang có quyền."
    lines = [f"🔐 {len(guests)} khách đang có quyền:", ""]
    for g in guests:
        left = f"{g['hours_left']:.0f}h" if g["hours_left"] is not None else "?"
        lines += [f"• {g['name']}  (còn {left})",
                  f"  💬 {g['message'][:60]}",
                  f"  /revoke {g['id']}", ""]
    return "\n".join(lines)


HELP = """🤖 Lệnh điều khiển

📊 Xem
/status  – trạng thái server
/url     – link công khai hiện tại
/scan    – quét ngay, không đợi chu kỳ
/guests  – ai đang có quyền xem
/revoke <id> – cắt quyền một khách

⏸ Dừng quét (web + link vẫn sống)
/pause   /resume

🔌 Nghỉ hẳn (đóng link công khai, bot vẫn nghe)
/off     /on

🛑 Tắt tiến trình – chỉ bật lại được từ chính máy
/stop"""


def _cmd_off_text(res):
    if not res["changed"]:
        return "Server đang nghỉ sẵn rồi. /on để bật lại."
    lines = ["🔌 Server đã nghỉ.", "",
             "• Link công khai đã đóng, khách ngoài không vào được",
             "• Đã dừng quét tín hiệu và dựng báo cáo"]
    if res.get("keepalive_released"):
        lines += ["• Đã nhả keep-alive – máy được ngủ",
                  "",
                  "⚠️ Máy ngủ là bot không nghe được nữa. Gõ /on lúc đó sẽ rơi vào "
                  "khoảng không, phải về mở laptop."]
    else:
        lines += ["• Máy vẫn thức để bot còn nghe được /on"]
    return "\n".join(lines + ["", "/on để bật lại."])


def _cmd_on_text(res):
    if not res["changed"]:
        return "Server đang chạy sẵn rồi."
    if not res.get("url"):
        return ("▶️ Đã bật lại, nhưng KHÔNG mở được link công khai.\n"
                "Server chỉ chạy nội bộ. Xem log để biết vì sao.")
    lines = ["▶️ Server đã bật lại.", "", f"🌍 {res['url']}"]
    if res.get("url_changed"):
        lines += ["",
                  "⚠️ LINK ĐÃ ĐỔI so với trước khi nghỉ. Khách đã duyệt sẽ bấm vào "
                  f"link cũ là vào chỗ chết – phải gửi lại link này cho họ.\n"
                  f"(provider {res.get('provider')} không giữ URL cố định)"]
    return "\n".join(lines)


async def _handle_command(text, chat_id):
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower().strip()
    arg = arg.strip()

    if cmd in ("/start", "/help"):
        send(HELP, chat_id)

    elif cmd == "/status":
        send(_cmd_status(), chat_id)

    elif cmd == "/url":
        send(_cmd_url(), chat_id)

    elif cmd == "/guests":
        send(_cmd_guests(), chat_id)

    elif cmd == "/revoke":
        if not arg:
            send("Dùng: /revoke <id>  (xem id bằng /guests)", chat_id)
        elif access.revoke(arg, chat_id):
            send(f"✅ Đã cắt quyền {arg}.", chat_id)
        else:
            send(f"Không tìm thấy khách có id {arg}.", chat_id)

    elif cmd == "/pause":
        STATE.paused = True
        send(f"⏸ Đã tạm dừng quét. Web vẫn chạy, giá vẫn cập nhật.\n"
             f"/resume để chạy lại.", chat_id)

    elif cmd == "/resume":
        STATE.paused = False
        send(f"▶️ Chạy lại. Lượt quét tới trong tối đa {SCAN_INTERVAL // 60} phút.", chat_id)

    elif cmd == "/scan":
        send("🔍 Đang quét...", chat_id)
        from .scheduler import scan_once
        try:
            alerts = await scan_once()
            if not alerts:
                send("Quét xong – không có gì đổi.", chat_id)
        except Exception as e:
            send(f"Quét lỗi: {type(e).__name__}: {e}", chat_id)

    elif cmd == "/off":
        from .power import standby
        send(_cmd_off_text(await standby()), chat_id)

    elif cmd == "/on":
        send("⏳ Đang bật lại, mở tunnel có thể mất vài giây...", chat_id)
        from .power import wake
        send(_cmd_on_text(await wake()), chat_id)

    elif cmd == "/stop":
        # KHÔNG tắt ngay. Đây là lệnh duy nhất không hoàn tác được từ điện thoại:
        # tiến trình chết là bot chết theo, phải mò về máy mới bật lại được.
        send("🛑 Tắt hẳn tiến trình?\n\n"
             "Bot sẽ chết theo, KHÔNG bật lại được từ Telegram nữa – phải về chính máy.\n"
             "Chỉ muốn đóng link công khai thì dùng /off.",
             chat_id,
             buttons=[[{"text": "🛑 Tắt hẳn", "callback_data": "halt:yes"},
                       {"text": "Huỷ",        "callback_data": "halt:no"}]])

    else:
        send(f"Không hiểu lệnh {cmd}.\n\n{HELP}", chat_id)


# ── CALLBACK NÚT BẤM ──────────────────────────────────────────────────────────
def _handle_callback(cb):
    cb_id   = cb["id"]
    chat_id = cb.get("message", {}).get("chat", {}).get("id")
    msg_id  = cb.get("message", {}).get("message_id")
    data    = cb.get("data", "")

    # CỬA KIỂM – không có dòng này thì ai cũng tự duyệt được cho mình
    if not access.is_owner(chat_id):
        print(f"  [bot] CHẶN callback từ chat_id lạ: {chat_id!r}")
        _answer_callback(cb_id, "Không có quyền.")
        return

    action, _, req_id = data.partition(":")

    # Xác nhận tắt hẳn – nằm SAU cửa kiểm is_owner ở trên, không phải trước
    if action == "halt":
        if req_id == "yes":
            _answer_callback(cb_id, "Đang tắt")
            _edit_text(chat_id, msg_id, "🛑 Đang tắt server. Hẹn gặp lại.")
            if _stop_event:
                _stop_event.set()
        else:
            _answer_callback(cb_id, "Đã huỷ")
            _edit_text(chat_id, msg_id, "Đã huỷ, server vẫn chạy.")
        return

    req = access.get_request(req_id)
    who = req["name"] if req else req_id

    if action == "approve":
        session = access.approve(req_id, chat_id)
        if session:
            _answer_callback(cb_id, "Đã duyệt")
            _edit_text(chat_id, msg_id,
                       f"✅ ĐÃ DUYỆT — {who}\n"
                       f"Quyền {GUEST_TTL_DAYS} ngày · id {session['id']}\n"
                       f"Cắt quyền: /revoke {session['id']}")
        else:
            _answer_callback(cb_id, "Yêu cầu không còn hiệu lực")
            _edit_text(chat_id, msg_id, f"⚠️ Yêu cầu của {who} đã được xử lý trước đó.")

    elif action == "deny":
        if access.deny(req_id, chat_id):
            _answer_callback(cb_id, "Đã từ chối")
            _edit_text(chat_id, msg_id, f"❌ ĐÃ TỪ CHỐI — {who}")
        else:
            _answer_callback(cb_id, "Yêu cầu không còn hiệu lực")
            _edit_text(chat_id, msg_id, f"⚠️ Yêu cầu của {who} đã được xử lý trước đó.")
    else:
        _answer_callback(cb_id, "Không hiểu thao tác")


# ── VÒNG LONG-POLL ────────────────────────────────────────────────────────────
def _get_updates(offset, timeout=25):
    try:
        r = requests.get(f"{API}/getUpdates",
                         params={"offset": offset, "timeout": timeout},
                         timeout=timeout + 10)
        r.raise_for_status()
        return r.json().get("result", [])
    except requests.Timeout:
        return []
    except Exception as e:
        print(f"  [bot] getUpdates lỗi: {e}")
        return []


async def poll_loop(stop_event):
    """Long-poll. Bỏ qua toàn bộ update tồn đọng lúc khởi động."""
    global _stop_event
    _stop_event = stop_event
    loop = asyncio.get_running_loop()

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [bot] Chưa cấu hình token – không bật điều khiển qua Telegram.")
        return

    pending = await loop.run_in_executor(None, _get_updates, 0, 0)
    offset = (pending[-1]["update_id"] + 1) if pending else 0
    print(f"  [bot] Long-poll bắt đầu (bỏ qua {len(pending)} update cũ).")

    while not stop_event.is_set():
        try:
            updates = await loop.run_in_executor(None, _get_updates, offset, 25)
            for u in updates:
                offset = u["update_id"] + 1
                try:
                    if "callback_query" in u:
                        await loop.run_in_executor(None, _handle_callback,
                                                   u["callback_query"])
                    elif "message" in u:
                        msg     = u["message"]
                        chat_id = msg.get("chat", {}).get("id")
                        text    = (msg.get("text") or "").strip()
                        if not text:
                            continue
                        # CỬA KIỂM cho lệnh
                        if not access.is_owner(chat_id):
                            print(f"  [bot] CHẶN lệnh từ chat_id lạ: {chat_id!r}")
                            send(STRANGER_REPLY, chat_id)
                            continue
                        if text.startswith("/"):
                            await _handle_command(text, chat_id)
                except Exception:
                    print("  [bot] xử lý update lỗi:\n" + traceback.format_exc())
        except asyncio.CancelledError:
            raise
        except Exception:
            print("  [bot] poll_loop lỗi:\n" + traceback.format_exc())
            await asyncio.sleep(5)
