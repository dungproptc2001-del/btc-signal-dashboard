"""Cửa kiểm của bot và luồng xác nhận tắt hẳn.

Bot công khai ra internet, ai cũng nhắn được. Chốt `is_owner(chat_id)` là thứ duy
nhất ngăn người lạ điều khiển server — mọi test ở đây canh đúng chỗ đó.
"""
import pytest

from btcreport.server import bot


@pytest.fixture
def gui(monkeypatch):
    """Bắt mọi lời bot định gửi đi, không gọi Telegram thật."""
    da_gui = []
    monkeypatch.setattr(bot, "_post", lambda method, payload, timeout=15:
                        da_gui.append((method, payload)) or {"ok": True})
    return da_gui


@pytest.fixture
def chu_nha(monkeypatch):
    monkeypatch.setattr(bot.access, "is_owner", lambda cid: cid == 999)
    return 999


# ── CỬA KIỂM CALLBACK ─────────────────────────────────────────────────────────
def _callback(data, chat_id):
    return {"id": "cb1", "data": data,
            "message": {"chat": {"id": chat_id}, "message_id": 7}}


def test_nut_tat_han_tu_chat_id_la_BI_CHAN(gui, chu_nha, monkeypatch):
    """Không kiểm thì người lạ chỉ cần gửi đúng callback data là tắt server của ông."""
    da_dung = []
    monkeypatch.setattr(bot, "_stop_event",
                        type("E", (), {"set": lambda self: da_dung.append(1)})())

    bot._handle_callback(_callback("halt:yes", chat_id=12345))

    assert da_dung == [], "người lạ KHÔNG được tắt server"
    methods = [m for m, _ in gui]
    assert "answerCallbackQuery" in methods
    assert "editMessageText" not in methods


def test_nut_tat_han_tu_chu_nha_thi_dung_server(gui, chu_nha, monkeypatch):
    da_dung = []
    monkeypatch.setattr(bot, "_stop_event",
                        type("E", (), {"set": lambda self: da_dung.append(1)})())

    bot._handle_callback(_callback("halt:yes", chat_id=chu_nha))

    assert da_dung == [1]


def test_nut_huy_thi_khong_tat(gui, chu_nha, monkeypatch):
    da_dung = []
    monkeypatch.setattr(bot, "_stop_event",
                        type("E", (), {"set": lambda self: da_dung.append(1)})())

    bot._handle_callback(_callback("halt:no", chat_id=chu_nha))

    assert da_dung == []
    text = [p.get("text", "") for m, p in gui if m == "editMessageText"]
    assert any("vẫn chạy" in t for t in text)


# ── /stop PHẢI HỎI LẠI ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_stop_khong_tat_ngay_ma_hien_nut(gui, chu_nha, monkeypatch):
    """Lệnh duy nhất không hoàn tác được từ điện thoại – bấm nhầm là phải mò về máy."""
    da_dung = []
    monkeypatch.setattr(bot, "_stop_event",
                        type("E", (), {"set": lambda self: da_dung.append(1)})())

    await bot._handle_command("/stop", chu_nha)

    assert da_dung == [], "/stop không được tắt ngay"
    payload = [p for m, p in gui if m == "sendMessage"][-1]
    nut = payload["reply_markup"]["inline_keyboard"][0]
    assert {b["callback_data"] for b in nut} == {"halt:yes", "halt:no"}


# ── SOẠN TIN /off /on ─────────────────────────────────────────────────────────
def test_tin_off_mac_dinh_noi_may_van_thuc():
    t = bot._cmd_off_text({"changed": True, "keepalive_released": False})
    assert "máy vẫn thức" in t.lower()
    assert "/on" in t


def test_tin_off_co_nha_keepalive_thi_CANH_BAO(gui):
    """Nhả keep-alive là máy ngủ được, mà máy ngủ thì bot câm. Phải nói thẳng."""
    t = bot._cmd_off_text({"changed": True, "keepalive_released": True})
    assert "⚠️" in t
    assert "khoảng không" in t or "mở laptop" in t


def test_tin_on_link_doi_thi_CANH_BAO():
    t = bot._cmd_on_text({"changed": True, "url": "https://moi.ts.net",
                          "url_changed": True, "provider": "cloudflare"})
    assert "⚠️" in t and "ĐỔI" in t


def test_tin_on_link_giu_nguyen_thi_khong_doa_nguoi_dung():
    t = bot._cmd_on_text({"changed": True, "url": "https://cu.ts.net",
                          "url_changed": False, "provider": "tailscale"})
    assert "⚠️" not in t
    assert "https://cu.ts.net" in t


def test_tin_on_khong_co_tunnel_thi_noi_that():
    t = bot._cmd_on_text({"changed": True, "url": None, "url_changed": False})
    assert "nội bộ" in t.lower()


# ── HELP ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lenh", ["/off", "/on", "/pause", "/resume", "/stop", "/status"])
def test_help_liet_ke_du_lenh(lenh):
    assert lenh in bot.HELP
