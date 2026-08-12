"""Quyền truy cập. Trọng tâm: chốt chặn chat_id — thứ duy nhất ngăn người lạ
điều khiển server khi web đã công khai ra internet.
"""
import json
from datetime import datetime, timedelta

import pytest

from btcreport.config import (
    MAX_REQ_GLOBAL, MAX_REQ_PER_IP, MIN_MESSAGE_LEN, TELEGRAM_CHAT_ID,
)
from btcreport.server import access

OWNER = TELEGRAM_CHAT_ID
MSG   = "em la ban o nhom crypto, muon xem tin hieu"


@pytest.fixture
def store(tmp_path):
    """File access.json riêng cho mỗi test."""
    return tmp_path / "access.json"


def req(store, name="Nguyen Van A", message=MSG, ip="1.2.3.4"):
    return access.create_request(name, message, ip=ip, user_agent="pytest", path=store)


# ══════════════════════════════════════════════════════════════════════════════
# CHỐT CHẶN CHAT_ID — phần quan trọng nhất của cả module
# ══════════════════════════════════════════════════════════════════════════════
def test_is_owner_dung_chat_id():
    assert access.is_owner(OWNER)
    assert access.is_owner(int(OWNER))       # Telegram trả int, config trả str
    assert access.is_owner(str(OWNER))


@pytest.mark.parametrize("bad", [None, "", "0", "123456789", 999999999, "  ", "69114135790"])
def test_is_owner_chan_chat_id_la(bad):
    assert not access.is_owner(bad)


def test_nguoi_la_khong_duyet_duoc(store):
    r = req(store)
    assert access.approve(r["id"], "999999", path=store) is None
    assert access.session_status(r["id"], path=store)[0] == "pending", \
        "yêu cầu phải còn nguyên, không bị người lạ động vào"


def test_nguoi_la_khong_tu_choi_duoc(store):
    r = req(store)
    assert access.deny(r["id"], "999999", path=store) is False
    assert access.session_status(r["id"], path=store)[0] == "pending"


def test_nguoi_la_khong_thu_hoi_duoc(store):
    r = req(store)
    s = access.approve(r["id"], OWNER, path=store)
    assert access.revoke(s["id"], "999999", path=store) is False
    assert access.check_session(s["token"], path=store) is not None, \
        "phiên vẫn phải sống sau khi người lạ đòi thu hồi"


def test_chat_id_none_khong_lam_gi_duoc(store):
    r = req(store)
    assert access.approve(r["id"], None, path=store) is None
    assert access.deny(r["id"], None, path=store) is False


# ══════════════════════════════════════════════════════════════════════════════
# TẠO YÊU CẦU
# ══════════════════════════════════════════════════════════════════════════════
def test_tao_yeu_cau_binh_thuong(store):
    r = req(store)
    assert r["status"] == "pending"
    assert r["name"] == "Nguyen Van A"
    assert len(r["id"]) >= 8


def test_thieu_ten_bi_tu_choi(store):
    with pytest.raises(access.InvalidRequest):
        req(store, name="   ")


def test_loi_nhan_qua_ngan_bi_tu_choi(store):
    with pytest.raises(access.InvalidRequest):
        req(store, message="a" * (MIN_MESSAGE_LEN - 1))


def test_loi_nhan_vua_du_thi_qua(store):
    assert req(store, message="a" * MIN_MESSAGE_LEN)["status"] == "pending"


def test_ten_va_loi_nhan_qua_dai_bi_tu_choi(store):
    with pytest.raises(access.InvalidRequest):
        req(store, name="x" * 61)
    with pytest.raises(access.InvalidRequest):
        req(store, message="x" * 501)


def test_user_agent_bi_cat_ngan(store):
    r = access.create_request("A", MSG, ip="1.1.1.1", user_agent="U" * 500, path=store)
    assert len(r["ua"]) <= 200


# ══════════════════════════════════════════════════════════════════════════════
# CHỐNG SPAM
# ══════════════════════════════════════════════════════════════════════════════
def test_qua_nhieu_yeu_cau_tu_mot_ip(store):
    for _ in range(MAX_REQ_PER_IP):
        req(store, ip="9.9.9.9")
    with pytest.raises(access.RateLimited):
        req(store, ip="9.9.9.9")


def test_ip_khac_khong_bi_anh_huong(store):
    for _ in range(MAX_REQ_PER_IP):
        req(store, ip="9.9.9.9")
    assert req(store, ip="8.8.8.8")["status"] == "pending"


def test_tran_nguong_toan_cuc(store):
    for i in range(MAX_REQ_GLOBAL):
        try:
            req(store, ip=f"10.0.0.{i}")
        except access.RateLimited:
            pytest.fail("chưa tới ngưỡng toàn cục mà đã chặn")
    with pytest.raises(access.RateLimited):
        req(store, ip="10.0.1.1")


def test_yeu_cau_cu_khong_tinh_vao_gioi_han(store):
    """Giới hạn tính theo giờ – yêu cầu 2 tiếng trước không được chặn người mới."""
    for _ in range(MAX_REQ_PER_IP):
        req(store, ip="7.7.7.7")
    data = json.loads(store.read_text(encoding="utf-8"))
    old = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
    for r in data["pending"]:
        r["created_at"] = old
    store.write_text(json.dumps(data), encoding="utf-8")
    assert req(store, ip="7.7.7.7")["status"] == "pending"


# ══════════════════════════════════════════════════════════════════════════════
# DUYỆT / TỪ CHỐI / PHIÊN
# ══════════════════════════════════════════════════════════════════════════════
def test_duyet_cap_phien(store):
    r = req(store)
    s = access.approve(r["id"], OWNER, path=store)
    assert s and len(s["token"]) >= 32
    assert access.check_session(s["token"], path=store)["name"] == r["name"]
    assert access.session_status(r["id"], path=store)[0] == "approved"


def test_moi_phien_mot_token_khac_nhau(store):
    tokens = {access.approve(req(store, ip=f"2.2.2.{i}")["id"], OWNER, path=store)["token"]
              for i in range(3)}
    assert len(tokens) == 3


def test_tu_choi_khong_cap_gi(store):
    r = req(store)
    assert access.deny(r["id"], OWNER, path=store)
    assert access.session_status(r["id"], path=store)[0] == "denied"
    assert access.list_guests(path=store) == []


def test_duyet_hai_lan_khong_tao_hai_phien(store):
    r = req(store)
    assert access.approve(r["id"], OWNER, path=store)
    assert access.approve(r["id"], OWNER, path=store) is None
    assert len(access.list_guests(path=store)) == 1


def test_token_sai_khong_vao_duoc(store):
    r = req(store)
    access.approve(r["id"], OWNER, path=store)
    assert access.check_session("token-bia-dat", path=store) is None
    assert access.check_session("", path=store) is None
    assert access.check_session(None, path=store) is None


def test_phien_het_han(store):
    r = req(store)
    s = access.approve(r["id"], OWNER, ttl_days=7, path=store)
    data = json.loads(store.read_text(encoding="utf-8"))
    data["sessions"][0]["expires_at"] = (datetime.now() - timedelta(minutes=1)).isoformat()
    store.write_text(json.dumps(data), encoding="utf-8")
    assert access.check_session(s["token"], path=store) is None
    assert access.list_guests(path=store) == []


def test_phien_con_han_thi_van_vao_duoc(store):
    s = access.approve(req(store)["id"], OWNER, ttl_days=7, path=store)
    g = access.list_guests(path=store)
    assert len(g) == 1 and 160 < g[0]["hours_left"] <= 168


def test_thu_hoi_cat_quyen_ngay(store):
    s = access.approve(req(store)["id"], OWNER, path=store)
    assert access.revoke(s["id"], OWNER, path=store)
    assert access.check_session(s["token"], path=store) is None
    assert access.list_guests(path=store) == []


def test_thu_hoi_id_khong_ton_tai(store):
    assert access.revoke("khong-co-that", OWNER, path=store) is False


# ══════════════════════════════════════════════════════════════════════════════
# DỌN DẸP + LƯU TRỮ
# ══════════════════════════════════════════════════════════════════════════════
def test_purge_don_phien_het_han(store):
    access.approve(req(store)["id"], OWNER, path=store)
    data = json.loads(store.read_text(encoding="utf-8"))
    data["sessions"][0]["expires_at"] = (datetime.now() - timedelta(days=1)).isoformat()
    store.write_text(json.dumps(data), encoding="utf-8")
    assert access.purge_expired(path=store) == 1
    assert access.load(path=store)["sessions"] == []


def test_purge_don_yeu_cau_treo_qua_lau(store):
    req(store)
    data = json.loads(store.read_text(encoding="utf-8"))
    data["pending"][0]["created_at"] = (datetime.now() - timedelta(days=2)).isoformat()
    store.write_text(json.dumps(data), encoding="utf-8")
    access.purge_expired(path=store)
    assert access.load(path=store)["pending"] == []


def test_file_hong_khong_lam_sap_server(store):
    store.write_text("{ khong phai json", encoding="utf-8")
    assert access.load(path=store) == {"sessions": [], "pending": [], "history": []}


def test_ghi_la_atomic(store):
    req(store)
    assert not store.with_suffix(".json.tmp").exists()


def test_lich_su_khong_phinh_vo_han(store):
    data = access._empty()
    data["history"] = [{"id": str(i), "created_at": datetime.now().isoformat()}
                       for i in range(400)]
    access.save(data, path=store)
    access.purge_expired(path=store)
    assert len(access.load(path=store)["history"]) <= 200


def test_status_id_la(store):
    assert access.session_status("khong-co", path=store)[0] == "unknown"
