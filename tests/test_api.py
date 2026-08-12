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


# ── BÁO CÁO ───────────────────────────────────────────────────────────────────
def test_report_chua_co_thi_tra_503(owner):
    STATE.report_html = None
    assert owner.get("/report").status_code == 503


def test_report_co_roi_thi_tra_html(owner):
    STATE.report_html = "<html><body>bao cao thu</body></html>"
    r = owner.get("/report")
    assert r.status_code == 200 and "bao cao thu" in r.text
    STATE.report_html = None
