"""Nhịp tim: phân biệt "không có tín hiệu" với "hệ thống đã chết".

Hai thứ này trông y hệt nhau nếu không ai đo, và đó là lỗi thiết kế nguy hiểm nhất của
cả hệ thống — nó hỏng đúng lúc người ta tin tưởng nhất. Test ở đây canh ba chuyện:

  1. `stale` bật đúng lúc, và KHÔNG bật khi chủ nhà chủ động cho nghỉ
  2. `/healthz` nói được ba trạng thái mà vẫn không lộ gì
  3. Nhịp nền chết âm thầm thì được dựng lại, còn nhịp bị huỷ thì để yên
"""
import asyncio
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from btcreport.config import SCAN_INTERVAL, STALE_AFTER, STALE_AFTER_SCANS
from btcreport.server import app as app_module, scheduler
from btcreport.server.app import app
from btcreport.server.state import STATE


@pytest.fixture
def sach():
    """STATE là singleton dùng chung cả file test — trả nguyên trạng sau mỗi lượt."""
    truoc = (STATE.last_scan_at, STATE.paused, STATE.standby, STATE.task_restarts)
    yield STATE
    (STATE.last_scan_at, STATE.paused, STATE.standby, STATE.task_restarts) = truoc


def _quet_cach_day(giay):
    STATE.last_scan_at = datetime.now() - timedelta(seconds=giay)


# ── NGƯỠNG ────────────────────────────────────────────────────────────────────
def test_nguong_dung_bang_3_nhip_quet():
    """Một nhịp lỡ là chuyện thường. Ba nhịp liên tiếp mới là có chuyện."""
    assert STALE_AFTER_SCANS == 3
    assert STALE_AFTER == 3 * SCAN_INTERVAL


def test_chua_quet_lan_nao_thi_khong_phai_la_cu(sach):
    """Server vừa bật, chưa kịp chạy nhịp đầu — không được báo động vì chuyện đó."""
    STATE.last_scan_at = None
    assert STATE.scan_age() is None
    assert STATE.is_stale() is False


def test_vua_quet_xong_thi_khong_cu(sach):
    STATE.paused = STATE.standby = False
    _quet_cach_day(5)
    assert STATE.scan_age() < 10
    assert STATE.is_stale() is False


def test_qua_han_thi_cu(sach):
    STATE.paused = STATE.standby = False
    _quet_cach_day(STALE_AFTER + 60)
    assert STATE.is_stale() is True


def test_dung_sat_nguong_thi_chua_cu(sach):
    """Ranh giới là `>` chứ không phải `>=`: đúng ngưỡng vẫn còn được coi là sống."""
    STATE.paused = STATE.standby = False
    _quet_cach_day(STALE_AFTER)
    assert STATE.is_stale() is False


# ── CHỦ ĐỘNG NGHỈ KHÔNG PHẢI LÀ HỎNG ──────────────────────────────────────────
def test_tam_dung_thi_khong_bao_cu(sach):
    """Báo động lúc chủ nhà tự tắt là tự tạo báo động giả cho chính mình."""
    _quet_cach_day(STALE_AFTER * 10)
    STATE.standby = False
    STATE.paused  = True
    assert STATE.is_stale() is False


def test_nghi_han_thi_khong_bao_cu(sach):
    _quet_cach_day(STALE_AFTER * 10)
    STATE.paused  = False
    STATE.standby = True
    assert STATE.is_stale() is False


def test_thoi_nghi_thi_bao_cu_lai_ngay(sach):
    """Bật lại mà vòng quét chưa chạy được lượt nào thì vẫn phải báo là cũ."""
    _quet_cach_day(STALE_AFTER * 10)
    STATE.paused = STATE.standby = True
    assert STATE.is_stale() is False
    STATE.paused = STATE.standby = False
    assert STATE.is_stale() is True


# ── PUBLIC ────────────────────────────────────────────────────────────────────
def test_public_mang_du_nguong_lan_tuoi(sach):
    """Client phải nhận được NGƯỠNG của server, không tự đặt luật lấy."""
    STATE.paused = STATE.standby = False
    _quet_cach_day(120)
    s = STATE.public()["status"]
    assert s["stale"] is False
    assert s["stale_after"] == STALE_AFTER
    assert 110 <= s["scan_age_seconds"] <= 130
    assert "task_restarts" in s


# ── /healthz ──────────────────────────────────────────────────────────────────
@pytest.fixture
def khach():
    original = app_module._is_owner_request
    app_module._is_owner_request = lambda request: False
    with TestClient(app) as c:
        yield c
    app_module._is_owner_request = original


def test_healthz_noi_duoc_ba_trang_thai(khach, sach):
    STATE.paused = STATE.standby = False
    _quet_cach_day(60)
    d = khach.get("/healthz").json()
    assert d["ok"] is True and d["stale"] is False and d["standby"] is False

    STATE.standby = True
    assert khach.get("/healthz").json()["standby"] is True

    STATE.standby = False
    _quet_cach_day(STALE_AFTER + 60)
    d = khach.get("/healthz").json()
    assert d["ok"] is True and d["stale"] is True, \
        "server sống mà vòng quét chết – đây mới là kiểu hỏng câm cần bắt"


def test_healthz_mang_theo_nguong_de_ben_ngoai_khong_phai_doan(khach, sach):
    d = khach.get("/healthz").json()
    assert d["stale_after"] == STALE_AFTER


def test_healthz_van_khong_lo_gia_ca(khach, sach):
    """Thêm trường vào /healthz là thêm thứ người lạ đọc được.

    `last_price_at` từng suýt được thêm vào đây. Tên trường chứa chữ `price`, và test
    canh rò rỉ bắt đúng chữ đó — nó chặn được một trường mà route công khai này không
    có lý do gì phải có.
    """
    body = json.dumps(khach.get("/healthz").json())
    for cam in ("token", "symbols", "price", "confluence", "verdict"):
        assert cam not in body


# ── NHỊP NỀN CHẾT ÂM THẦM ─────────────────────────────────────────────────────
async def _nhip_hong():
    raise RuntimeError("nhịp lăn ra chết")


async def _nhip_song():
    await asyncio.sleep(3600)


@pytest.fixture
def gia_lap_nhip(monkeypatch):
    """Thay 4 nhịp thật bằng một nhịp giả, và chặn Telegram."""
    gui = []
    monkeypatch.setattr(scheduler, "_tasks", {})
    monkeypatch.setattr(scheduler, "send_telegram",
                        lambda text: (gui.append(text), True)[1])
    return gui


@pytest.mark.asyncio
async def test_nhip_chet_thi_duoc_dung_lai(monkeypatch, gia_lap_nhip, sach):
    monkeypatch.setattr(scheduler, "_LOOPS", {"thử": _nhip_hong})
    cu = asyncio.create_task(_nhip_hong())
    await asyncio.sleep(0.05)
    assert cu.done()

    scheduler._tasks["thử"] = cu
    truoc = STATE.task_restarts

    song_lai = await scheduler.revive_dead()

    assert song_lai == ["thử"]
    assert scheduler._tasks["thử"] is not cu, "phải là task MỚI, không phải cái xác cũ"
    assert STATE.task_restarts == truoc + 1
    scheduler._tasks["thử"].cancel()


@pytest.mark.asyncio
async def test_dung_lai_thi_bao_telegram_kem_ten_loi(monkeypatch, gia_lap_nhip, sach):
    """Nhịp chết là chuyện chưa từng xảy ra – nếu xảy ra thật thì đó là tin đắt."""
    monkeypatch.setattr(scheduler, "_LOOPS", {"quét": _nhip_hong})
    cu = asyncio.create_task(_nhip_hong())
    await asyncio.sleep(0.05)
    scheduler._tasks["quét"] = cu

    await scheduler.revive_dead()

    assert len(gia_lap_nhip) == 1
    tin = gia_lap_nhip[0]
    assert "quét" in tin and "RuntimeError" in tin and "nhịp lăn ra chết" in tin
    scheduler._tasks["quét"].cancel()


@pytest.mark.asyncio
async def test_nhip_bi_HUY_thi_khong_dung_lai(monkeypatch, gia_lap_nhip, sach):
    """`stop()` huỷ hết task. Dựng lại lúc đó là hồi sinh cái vừa cố tình giết."""
    monkeypatch.setattr(scheduler, "_LOOPS", {"thử": _nhip_song})
    t = asyncio.create_task(_nhip_song())
    await asyncio.sleep(0)
    t.cancel()
    await asyncio.sleep(0.05)
    assert t.cancelled()

    scheduler._tasks["thử"] = t
    truoc = STATE.task_restarts

    assert await scheduler.revive_dead() == []
    assert STATE.task_restarts == truoc
    assert gia_lap_nhip == [], "không được nhắn tin cho việc mình tự làm"


@pytest.mark.asyncio
async def test_nhip_dang_song_thi_de_yen(monkeypatch, gia_lap_nhip, sach):
    monkeypatch.setattr(scheduler, "_LOOPS", {"thử": _nhip_song})
    t = asyncio.create_task(_nhip_song())
    await asyncio.sleep(0)
    scheduler._tasks["thử"] = t

    assert await scheduler.revive_dead() == []
    assert scheduler._tasks["thử"] is t
    assert gia_lap_nhip == []
    t.cancel()


# ── CHỐT MÚI GIỜ CHO GIAO DIỆN ────────────────────────────────────────────────
def test_js_khong_parse_moc_quet_thanh_thoi_gian_tuyet_doi():
    """`last_scan_at` là giờ địa phương KHÔNG kèm offset.

    Trình duyệt ở múi giờ khác parse nó ra lệch hàng tiếng → khách nước ngoài sẽ thấy
    băng đỏ vĩnh viễn dù hệ thống hoàn toàn khoẻ, và đếm ngược sai cả tiếng. Giao diện
    phải đếm bằng SỐ GIÂY (`scan_age_seconds`), không parse mốc.

    Test tĩnh vì lỗi này câm: trang vẫn render, chỉ là báo sai cho đúng những người
    không ngồi cạnh cái máy chủ.
    """
    js = (app_module.STATIC / "dashboard.js").read_text(encoding="utf-8")
    assert "new Date(s.last_scan_at)" not in js
    assert "scan_age_seconds" in js and "markAge" in js


def test_js_khong_tu_sinh_moc_thoi_gian_bang_dong_ho_trinh_duyet():
    """Mọi mốc hiện trên thanh trạng thái phải là đồng hồ SERVER.

    `new Date().toISOString()` ra giờ UTC. Trang mở lên hiện đúng giờ VN vì server gửi
    xuống, rồi 30 giây sau nhịp giá đầu tiên về là con số nhảy lùi 7 tiếng và nằm luôn
    ở đó — sai cho tất cả mọi người, kể cả người ngồi ngay cạnh cái máy chủ.
    """
    js = (app_module.STATIC / "dashboard.js").read_text(encoding="utf-8")

    # Bóc chú thích trước khi soi. Không bóc thì test này đỏ vì đúng cái comment giải
    # thích lỗi cũ – grep trúng mã nguồn thay vì thứ đang chạy, đúng loại nhầm đã làm
    # hỏng một lần nghiệm thu trước đây.
    ma = "\n".join(d for d in js.splitlines() if not d.strip().startswith("//"))
    assert "toISOString" not in ma


@pytest.mark.asyncio
async def test_watch_loop_khong_chet_theo_loi_ben_trong(monkeypatch, gia_lap_nhip):
    """Vòng canh mà chết theo thì không còn ai canh. Nó phải nuốt mọi lỗi."""
    monkeypatch.setattr(scheduler, "TASK_WATCH_INTERVAL", 0.01)

    async def no_tung():
        raise RuntimeError("revive_dead hỏng")

    monkeypatch.setattr(scheduler, "revive_dead", no_tung)
    t = asyncio.create_task(scheduler.watch_loop())
    await asyncio.sleep(0.08)          # đủ cho vài vòng

    assert not t.done(), "watch_loop phải sống sót qua lỗi của revive_dead"
    t.cancel()
