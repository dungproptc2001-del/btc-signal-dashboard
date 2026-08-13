"""Route và cửa gác của server web.

Trọng tâm: không có quyền thì không lấy được dữ liệu, và không rò rỉ secret ra web.
"""
import json

import pytest
from fastapi.testclient import TestClient

from btcreport.config import OWNER_KEY, SESSION_COOKIE
from btcreport.server import access, app as app_module
from btcreport.server.app import app
from btcreport.server.state import STATE


@pytest.fixture
def guest():
    """Client giả làm người ngoài — ghi đè kiểm localhost."""
    original = app_module._is_owner_request
    app_module._is_owner_request = lambda request: False
    with TestClient(app) as c:
        yield c
    app_module._is_owner_request = original


@pytest.fixture
def owner():
    """Client giả làm chủ nhà.

    TestClient khai host là "testclient" chứ không phải 127.0.0.1, nên phải ghi đè
    — và đó là hành vi ĐÚNG: chỉ localhost thật mới được coi là chủ nhà.
    """
    original = app_module._is_owner_request
    app_module._is_owner_request = lambda request: True
    with TestClient(app) as c:
        yield c
    app_module._is_owner_request = original


# ── NHẬN DIỆN CHỦ NHÀ ─────────────────────────────────────────────────────────
class _FakeReq:
    def __init__(self, host, headers=None):
        self.client = type("C", (), {"host": host})() if host else None
        self.cookies = {}
        self.headers = headers or {}


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_localhost_la_chu_nha(host):
    assert app_module._is_owner_request(_FakeReq(host))


@pytest.mark.parametrize("host", ["10.61.181.249", "1.2.3.4", "testclient", "", None])
def test_dia_chi_khac_khong_phai_chu_nha(host):
    assert not app_module._is_owner_request(_FakeReq(host))


@pytest.mark.parametrize("header", [
    "cf-connecting-ip", "x-forwarded-for", "x-real-ip", "forwarded", "cf-ray",
])
def test_co_header_proxy_thi_KHONG_phai_chu_nha(header):
    """Cloudflared kết nối vào server từ chính 127.0.0.1.

    Chỉ nhìn địa chỉ thì mọi khách trên internet đều thành chủ nhà — đây là
    lớp chặn thứ hai, không dựa vào mặc định của uvicorn hay Cloudflare.
    """
    assert not app_module._is_owner_request(
        _FakeReq("127.0.0.1", {header: "127.0.0.1"}))


def test_khach_khong_the_gia_mao_localhost():
    """Kể cả tự khai đủ mọi header về loopback cũng không thành chủ nhà."""
    spoof = {"x-forwarded-for": "127.0.0.1", "cf-connecting-ip": "127.0.0.1",
             "x-real-ip": "::1"}
    assert not app_module._is_owner_request(_FakeReq("127.0.0.1", spoof))


def test_tailscale_funnel_khong_phai_chu_nha():
    """Đúng những gì đo được từ ngoài internet qua Funnel (12/08/2026).

    Hai lớp cùng đỡ ở đây: địa chỉ là interface tailscale chứ không phải
    loopback, VÀ có x-forwarded-for.
    """
    funnel = {"x-forwarded-for": "203.0.113.9", "x-forwarded-proto": "https",
              "x-forwarded-host": "laptop.tailXXXX.ts.net",
              "tailscale-user-login": "", "tailscale-headers-info": ""}
    assert not app_module._is_owner_request(_FakeReq("100.113.107.39", funnel))


def test_header_tailscale_user_khong_cap_quyen_gi():
    """Funnel bơm sẵn tailscale-user-* vào MỌI request công khai.

    Người lạ tự khai mình là chủ tailnet cũng không được gì – code không đọc
    mấy header đó, và test này canh để nó đừng bao giờ được đọc.
    """
    gia_mao = {"tailscale-user-login": "dungproptc2001@gmail.com",
               "tailscale-user-name": "Chu nha"}
    assert not app_module._is_owner_request(_FakeReq("1.2.3.4", gia_mao))


# ── CỬA GÁC ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("path", ["/api/signals", "/api/report", "/events"])
def test_api_khong_cookie_tra_401(guest, path):
    assert guest.get(path).status_code == 401


def test_api_401_khong_lo_du_lieu(guest):
    body = guest.get("/api/signals").json()
    assert "symbols" not in body and "error" in body


def test_trang_chu_khong_quyen_thi_hien_form_xin(guest):
    r = guest.get("/")
    assert r.status_code == 200
    assert "Yêu cầu truy cập" in r.text or "yêu cầu" in r.text.lower()
    assert "Confluence" not in r.text, "không được lộ dashboard cho người chưa duyệt"


def test_healthz_khong_can_quyen(guest):
    r = guest.get("/healthz")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_healthz_khong_lo_gi_nhay_cam(guest):
    body = json.dumps(guest.get("/healthz").json())
    assert OWNER_KEY not in body
    for k in ("token", "symbols", "price"):
        assert k not in body


def test_chu_nha_tu_localhost_vao_thang(owner):
    r = owner.get("/")
    assert r.status_code == 200
    assert "Chủ nhà" in r.text


def test_api_cho_chu_nha_chay_duoc(owner):
    r = owner.get("/api/signals")
    assert r.status_code == 200
    assert "symbols" in r.json() and "status" in r.json()


# ── LOGIN CỬA SAU ─────────────────────────────────────────────────────────────
def test_login_dung_key_thi_cap_cookie(guest):
    r = guest.get(f"/login?key={OWNER_KEY}", follow_redirects=False)
    assert r.status_code == 303
    assert SESSION_COOKIE in r.cookies


def test_login_sai_key_khong_cap_gi(guest):
    r = guest.get("/login?key=doan-bua", follow_redirects=False)
    assert r.status_code == 200
    assert SESSION_COOKIE not in r.cookies


def test_login_khong_key_khong_cap_gi(guest):
    assert SESSION_COOKIE not in guest.get("/login", follow_redirects=False).cookies


def test_cookie_chu_nha_dung_duoc_o_request_sau(guest):
    guest.get(f"/login?key={OWNER_KEY}", follow_redirects=False)
    assert guest.get("/api/signals").status_code == 200


def test_cookie_la_httponly(guest):
    r = guest.get(f"/login?key={OWNER_KEY}", follow_redirects=False)
    assert "httponly" in r.headers.get("set-cookie", "").lower()


# ── LUỒNG XIN QUYỀN ───────────────────────────────────────────────────────────
def test_xin_quyen_thieu_thong_tin_bi_tu_choi(guest, monkeypatch):
    monkeypatch.setattr(app_module.bot, "notify_access_request", lambda req: None)
    r = guest.post("/access/request", data={"name": "A", "message": "ngan"})
    assert r.status_code == 400


def test_xin_quyen_hop_le_thi_tao_yeu_cau(guest, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(app_module.bot, "notify_access_request", lambda req: sent.append(req))
    monkeypatch.setattr(access, "ACCESS_FILE", tmp_path / "a.json")

    r = guest.post("/access/request",
                   data={"name": "Nguyen Van A", "message": "toi muon xem tin hieu BTC"})
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    assert len(sent) == 1, "phải gửi Telegram đúng một lần"


def test_bi_chan_rate_limit_thi_KHONG_gui_telegram(guest, monkeypatch, tmp_path):
    """Điểm này quan trọng: chặn phải xảy ra TRƯỚC khi bot nhắn, không thì
    bất kỳ ai cũng làm ngập điện thoại chủ nhà."""
    sent = []
    monkeypatch.setattr(app_module.bot, "notify_access_request", lambda req: sent.append(req))
    monkeypatch.setattr(access, "ACCESS_FILE", tmp_path / "a.json")

    payload = {"name": "Spammer", "message": "cho toi xem voi nhe ban oi"}
    codes = [guest.post("/access/request", data=payload).status_code for _ in range(6)]

    assert 429 in codes, "phải có lúc bị chặn"
    assert len(sent) == codes.count(200), "số lần nhắn Telegram phải bằng số lần được nhận"
    assert len(sent) < 6


def test_status_id_la_tra_unknown(guest):
    assert guest.get("/access/status?id=khong-co-that").json()["status"] == "unknown"


# ── KHÔNG RÒ RỈ SECRET ────────────────────────────────────────────────────────
def test_public_state_khong_chua_secret():
    blob = json.dumps(STATE.public(), default=str)
    from btcreport.config import TELEGRAM_BOT_TOKEN
    assert OWNER_KEY not in blob
    assert TELEGRAM_BOT_TOKEN not in blob
    assert "token" not in blob.lower()


def test_dashboard_khong_nhung_owner_key(owner):
    assert OWNER_KEY not in owner.get("/").text


def test_trang_xin_quyen_khong_lo_gi(guest):
    from btcreport.config import TELEGRAM_BOT_TOKEN
    body = guest.get("/").text
    assert TELEGRAM_BOT_TOKEN not in body
    assert OWNER_KEY not in body


# ── LINK CÔNG KHAI ────────────────────────────────────────────────────────────
def test_link_khong_quyen_thi_401(guest):
    assert guest.get("/api/link").status_code == 401


def test_link_khach_da_duyet_van_bi_chan(guest, monkeypatch):
    """Chốt chặn thứ hai. Cửa gác chỉ hỏi 'có phiên không', mà khách đã duyệt
    thì có phiên – nên route phải tự kiểm quyền chủ nhà lần nữa."""
    monkeypatch.setattr(access, "check_session",
                        lambda t: {"name": "Khach", "owner": False})
    guest.cookies.set(SESSION_COOKIE, "phien-khach-hop-le")
    r = guest.get("/api/link")
    assert r.status_code == 403
    assert "tail" not in r.text.lower()


def test_chu_nha_lay_duoc_link(owner):
    STATE.tunnel_url = "https://vi-du.tail0000.ts.net"
    try:
        r = owner.get("/api/link")
        assert r.status_code == 200
        assert r.json()["url"] == "https://vi-du.tail0000.ts.net"
    finally:
        STATE.tunnel_url = None


def test_link_khong_kem_owner_key(owner):
    """Link này để gửi cho người khác. Kèm OWNER_KEY là khách tự cấp quyền chủ
    nhà cho mình, thu hồi phiên cũng vô nghĩa."""
    STATE.tunnel_url = "https://vi-du.tail0000.ts.net"
    try:
        assert OWNER_KEY not in owner.get("/api/link").text
    finally:
        STATE.tunnel_url = None


def test_khong_co_tunnel_thi_link_None(owner):
    STATE.tunnel_url = None
    assert owner.get("/api/link").json()["url"] is None


# ── CSS/JS NHÚNG VÀO TRANG PHẢI CHẠY ĐƯỢC ─────────────────────────────────────
# Lỗi câm đã từng xảy ra: autoescape biến ' thành &#39; trong <script>, script chết
# ngay dòng đầu và CSS mất hết font-family. Trang vẫn trả 200, vẫn đủ chữ, chỉ là
# KHÔNG CÓ GÌ CHẠY — grep chuỗi trong HTML không phát hiện được, vì chuỗi cần tìm
# nằm ngay trong mã nguồn JS nhúng vào.
import re


def _khoi_script(html):
    return re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)


def _khoi_style(html):
    return re.findall(r"<style[^>]*>(.*?)</style>", html, re.S)


# Chỉ dò &#39; và &quot;. KHÔNG dò &lt; &gt; &amp; — hàm esc() trong dashboard.js
# chứa đúng ba chuỗi đó làm giá trị thay thế, chúng nằm đấy hợp lệ.
@pytest.mark.parametrize("entity", ["&#39;", "&quot;"])
def test_js_nhung_vao_KHONG_bi_html_escape(owner, entity):
    for khoi in _khoi_script(owner.get("/").text):
        assert entity not in khoi, f"script bị escape ({entity}) – JS sẽ chết ngay"


def test_css_nhung_vao_KHONG_bi_html_escape(owner):
    for khoi in _khoi_style(owner.get("/").text):
        assert "&#39;" not in khoi and "&gt;" not in khoi


def test_trang_xin_quyen_cung_khong_bi_escape(guest):
    for khoi in _khoi_style(guest.get("/").text):
        assert "&#39;" not in khoi


def test_js_giu_nguyen_dau_nhay_that(owner):
    """Chốt dương tính: phải thấy đúng mã nguồn, không phải bản đã escape."""
    js = "\n".join(_khoi_script(owner.get("/").text))
    assert "return 'na';" in js
    assert "getElementById" in js


# ── NHẬT KÝ TÍN HIỆU ──────────────────────────────────────────────────────────
def test_lich_su_khong_quyen_thi_401(guest):
    assert guest.get("/api/signals/history").status_code == 401


def test_khach_da_duyet_XEM_DUOC_het_lich_su(guest, monkeypatch):
    """Đã chốt: khách được duyệt xem hết lịch sử, như chủ nhà.

    Khác hẳn /api/link — cái đó chỉ chủ nhà. Test này canh đúng sự khác biệt đó,
    để sau này không ai siết nhầm cả hai về một mức.
    """
    monkeypatch.setattr(access, "check_session",
                        lambda t: {"name": "Khach", "owner": False})
    guest.cookies.set(SESSION_COOKIE, "phien-khach-hop-le")
    r = guest.get("/api/signals/history")
    assert r.status_code == 200
    assert "entries" in r.json()


def test_lich_su_cho_chu_nha(owner):
    r = owner.get("/api/signals/history")
    assert r.status_code == 200 and isinstance(r.json()["entries"], list)


def test_limit_bi_kep_khong_cho_hut_ca_file(owner):
    """limit=999999 mà không kẹp là một request kéo cả lịch sử vào RAM."""
    assert owner.get("/api/signals/history?limit=999999").status_code == 200
    assert owner.get("/api/signals/history?limit=0").status_code == 200
    assert owner.get("/api/signals/history?limit=-5").status_code == 200


# ── CHẤM ĐIỂM TÍN HIỆU ────────────────────────────────────────────────────────
@pytest.fixture
def co_ket_qua(monkeypatch, tmp_path):
    """Một nhật ký 2 tín hiệu, một cái đã chấm là THẮNG."""
    from btcreport.service import journal, outcome

    e1 = {"id": "BTCUSDT@2026-08-01T10:00:00+07:00", "at": "2026-08-01T10:00:00+07:00",
          "symbol": "BTCUSDT", "name": "BTC", "to": "STRONG LONG", "price": 100.0,
          "risk": {"entry": 100.0, "sl": 90.0, "tp": 120.0}, "text": "x"}
    e2 = {**e1, "id": "ETHUSDT@2026-08-02T10:00:00+07:00",
          "at": "2026-08-02T10:00:00+07:00", "symbol": "ETHUSDT", "name": "ETH"}

    kq = tmp_path / "outcomes.jsonl"
    outcome.save([{"id": e1["id"], "symbol": "BTCUSDT", "status": "win", "r": 2.0}],
                 path=kq)
    monkeypatch.setattr(outcome, "OUTCOME_FILE", kq)
    monkeypatch.setattr(journal, "read",
                        lambda limit=None, symbol=None, path=None: [e2, e1])
    return e1, e2


def test_lich_su_kem_ket_qua_cham_diem(owner, co_ket_qua):
    es = {e["symbol"]: e for e in owner.get("/api/signals/history").json()["entries"]}
    assert es["BTCUSDT"]["outcome"]["status"] == "win"
    assert es["BTCUSDT"]["outcome"]["r"] == 2.0


def test_chua_cham_thi_la_dang_chay_chu_khong_phai_o_trong(owner, co_ket_qua):
    """Trả None thì giao diện phải đoán ý nghĩa của một ô trống."""
    es = {e["symbol"]: e for e in owner.get("/api/signals/history").json()["entries"]}
    assert es["ETHUSDT"]["outcome"] == {"status": "open"}


def test_lich_su_KHONG_goi_mang(owner, co_ket_qua, monkeypatch):
    """Trang chủ không được phụ thuộc Binance để mở lên được."""
    from btcreport.service import outcome
    monkeypatch.setattr(outcome, "fetch_klines_range",
                        lambda *a: pytest.fail("không được gọi mạng"))
    assert owner.get("/api/signals/history").status_code == 200
    assert owner.get("/api/signals/stats").status_code == 200


def test_thong_ke_khong_quyen_thi_401(guest):
    assert guest.get("/api/signals/stats").status_code == 401


def test_khach_da_duyet_xem_duoc_thong_ke(guest, monkeypatch, co_ket_qua):
    """Đồng bộ với lịch sử: khách đã duyệt xem được hết."""
    monkeypatch.setattr(access, "check_session",
                        lambda t: {"name": "Khach", "owner": False})
    guest.cookies.set(SESSION_COOKIE, "phien-khach-hop-le")
    assert guest.get("/api/signals/stats").status_code == 200


def test_thong_ke_AN_ty_le_khi_chua_du_mau(owner, co_ket_qua):
    """Con số thuyết phục trên mẫu bé còn tệ hơn không có con số nào.

    `win_rate` phải là None để giao diện không có gì mà hiện – không được trả 100%
    rồi trông cậy vào frontend tự biết mà giấu đi.
    """
    tk = owner.get("/api/signals/stats").json()
    o = tk["overall"]
    assert o["win_rate"] is None
    assert o["n"] == 1 and o["min_n"] > 1
    assert o["counts"]["win"] == 1, "số đếm thô thì vẫn hiện"


def test_thong_ke_tach_theo_ma(owner, co_ket_qua):
    tk = owner.get("/api/signals/stats").json()
    assert set(tk["by_symbol"]) == {"BTCUSDT", "ETHUSDT"}
    assert tk["total_signals"] == 2


def test_thong_ke_khong_lo_secret(owner, co_ket_qua):
    from btcreport.config import TELEGRAM_BOT_TOKEN
    body = json.dumps(owner.get("/api/signals/stats").json())
    assert OWNER_KEY not in body
    if TELEGRAM_BOT_TOKEN:
        assert TELEGRAM_BOT_TOKEN not in body


# ── BÁO CÁO ───────────────────────────────────────────────────────────────────
def test_report_chua_co_thi_tra_503(owner):
    STATE.report_html = None
    assert owner.get("/report").status_code == 503


def test_report_co_roi_thi_tra_html(owner):
    STATE.report_html = "<html><body>bao cao thu</body></html>"
    r = owner.get("/report")
    assert r.status_code == 200 and "bao cao thu" in r.text
    STATE.report_html = None
