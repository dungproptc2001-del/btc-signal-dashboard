"""Nghỉ / bật lại mà không giết tiến trình.

Trọng tâm: gọi chồng không được đẻ ra nhiều bộ scheduler, và mặc định không được
nhả keep-alive — nhả là máy ngủ, bot câm, /on rơi vào khoảng không.

Không mở tunnel thật, không gọi mạng: mọi thứ bên ngoài đều bị monkeypatch.
"""
import asyncio

import pytest

from btcreport import config
from btcreport.server import power
from btcreport.server.state import STATE


@pytest.fixture
def gia_lap(monkeypatch):
    """Thay tunnel/scheduler/keepalive bằng bản đếm số lần gọi."""
    goi = {"tunnel_start": 0, "tunnel_stop": 0,
           "sched_start": 0, "sched_stop": 0,
           "hold": 0, "release": 0,
           "thu_tu": []}

    def tunnel_start(port):
        goi["tunnel_start"] += 1
        goi["thu_tu"].append("tunnel_start")
        return "https://vi-du.tail0000.ts.net"

    def tunnel_stop():
        goi["tunnel_stop"] += 1
        goi["thu_tu"].append("tunnel_stop")

    async def sched_start():
        goi["sched_start"] += 1
        goi["thu_tu"].append("sched_start")

    async def sched_stop():
        goi["sched_stop"] += 1
        goi["thu_tu"].append("sched_stop")

    monkeypatch.setattr(power.tunnel, "start", tunnel_start)
    monkeypatch.setattr(power.tunnel, "stop", tunnel_stop)
    monkeypatch.setattr(power.scheduler, "start", sched_start)
    monkeypatch.setattr(power.scheduler, "stop", sched_stop)
    monkeypatch.setattr(power.keepalive, "hold",
                        lambda: (goi.__setitem__("hold", goi["hold"] + 1), True)[1])
    monkeypatch.setattr(power.keepalive, "release",
                        lambda: goi.__setitem__("release", goi["release"] + 1))

    STATE.standby         = False
    STATE.standby_since   = None
    STATE.tunnel_url      = "https://vi-du.tail0000.ts.net"
    STATE.last_tunnel_url = "https://vi-du.tail0000.ts.net"
    yield goi
    STATE.standby         = False
    STATE.standby_since   = None
    STATE.tunnel_url      = None
    STATE.last_tunnel_url = None


# ── NGHỈ ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_standby_dong_tunnel_va_dung_scheduler(gia_lap):
    res = await power.standby()
    assert res["changed"] is True
    assert STATE.standby is True
    assert gia_lap["tunnel_stop"] == 1
    assert gia_lap["sched_stop"] == 1


@pytest.mark.asyncio
async def test_standby_dong_duong_ra_ngoai_TRUOC_khi_dung_viec(gia_lap):
    """Ngược thứ tự thì có một khoảng khách vẫn vào được trang mà dữ liệu đã chết."""
    await power.standby()
    assert gia_lap["thu_tu"].index("tunnel_stop") < gia_lap["thu_tu"].index("sched_stop")


@pytest.mark.asyncio
async def test_standby_MAC_DINH_khong_nha_keepalive(gia_lap, monkeypatch):
    """Nhả là máy ngủ, bot câm, gõ /on rơi vào khoảng không.

    Bảo đảm cứng của thiết kế: tắt được từ điện thoại thì bật lại được từ điện thoại.
    """
    monkeypatch.setattr(config, "SLEEP_ON_OFF", False)
    res = await power.standby()
    assert gia_lap["release"] == 0
    assert res["keepalive_released"] is False


@pytest.mark.asyncio
async def test_co_co_sleep_on_off_thi_nha_keepalive(gia_lap, monkeypatch):
    monkeypatch.setattr(config, "SLEEP_ON_OFF", True)
    res = await power.standby()
    assert gia_lap["release"] == 1
    assert res["keepalive_released"] is True


@pytest.mark.asyncio
async def test_standby_hai_lan_khong_lam_gi_them(gia_lap):
    await power.standby()
    res = await power.standby()
    assert res["changed"] is False
    assert gia_lap["tunnel_stop"] == 1


@pytest.mark.asyncio
async def test_standby_xoa_tunnel_url_khoi_state(gia_lap):
    await power.standby()
    assert STATE.tunnel_url is None
    assert STATE.last_tunnel_url == "https://vi-du.tail0000.ts.net", "phải nhớ để so sánh"


# ── BẬT LẠI ───────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_wake_dung_lai_du_ba_thu(gia_lap):
    await power.standby()
    res = await power.wake()
    assert res["changed"] is True
    assert STATE.standby is False
    assert gia_lap["hold"] == 1
    assert gia_lap["sched_start"] == 1
    assert gia_lap["tunnel_start"] == 1


@pytest.mark.asyncio
async def test_wake_dung_nen_TRUOC_khi_mo_duong_ra_ngoai(gia_lap):
    await power.standby()
    gia_lap["thu_tu"].clear()
    await power.wake()
    assert gia_lap["thu_tu"].index("sched_start") < gia_lap["thu_tu"].index("tunnel_start")


@pytest.mark.asyncio
async def test_wake_ba_lan_lien_tiep_chi_start_scheduler_MOT_lan(gia_lap):
    """Không có khoá thì /on bấm 3 lần đẻ 3 bộ scheduler, mỗi bộ một vòng quét
    riêng, ghi đè last_signals.json của nhau."""
    await power.standby()
    await asyncio.gather(power.wake(), power.wake(), power.wake())
    assert gia_lap["sched_start"] == 1
    assert gia_lap["tunnel_start"] == 1


@pytest.mark.asyncio
async def test_wake_khi_dang_chay_khong_lam_gi(gia_lap):
    res = await power.wake()
    assert res["changed"] is False
    assert gia_lap["sched_start"] == 0


@pytest.mark.asyncio
async def test_link_giu_nguyen_thi_khong_canh_bao(gia_lap):
    await power.standby()
    res = await power.wake()
    assert res["url_changed"] is False


@pytest.mark.asyncio
async def test_link_doi_thi_PHAI_canh_bao(gia_lap, monkeypatch):
    """Cloudflare quick tunnel đổi URL mỗi lần mở lại. Không cảnh báo thì khách đã
    duyệt bấm link cũ vào chỗ chết mà chủ nhà không biết."""
    await power.standby()
    monkeypatch.setattr(power.tunnel, "start", lambda port: "https://khac-han.ts.net")
    res = await power.wake()
    assert res["url_changed"] is True


@pytest.mark.asyncio
async def test_mo_tunnel_that_bai_van_bat_lai_duoc(gia_lap, monkeypatch):
    """Tunnel hỏng không được kẹt server lại trong trạng thái nghỉ."""
    await power.standby()
    monkeypatch.setattr(power.tunnel, "start", lambda port: None)
    res = await power.wake()
    assert res["url"] is None
    assert STATE.standby is False, "phải thoát nghỉ dù không có tunnel"


# ── TRẠNG THÁI RA WEB ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_public_co_standby(gia_lap):
    await power.standby()
    s = STATE.public()["status"]
    assert s["standby"] is True and s["standby_since"]


@pytest.mark.asyncio
async def test_public_van_khong_chua_secret_khi_standby(gia_lap):
    import json

    from btcreport.config import OWNER_KEY, TELEGRAM_BOT_TOKEN
    await power.standby()
    blob = json.dumps(STATE.public(), default=str)
    assert OWNER_KEY not in blob
    if TELEGRAM_BOT_TOKEN:
        assert TELEGRAM_BOT_TOKEN not in blob
