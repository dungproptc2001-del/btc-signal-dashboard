"""Nhật ký tín hiệu mua/bán.

Trọng tâm: chỉ ghi tín hiệu thật, ghi đủ hai trường đắt nhất (`price`,
`first_seen_at`), và một dòng rác không được làm sập trang chủ.

Mọi test ghi vào tmp_path — không đụng data/signals.jsonl thật.
"""
import json
from datetime import datetime, timedelta

import pytest

from btcreport.service import journal
from btcreport.service.journal import TZ_VN


@pytest.fixture
def log(tmp_path):
    return tmp_path / "signals.jsonl"


def alert(conf="STRONG LONG", prev="NEUTRAL", price=64128.0, name="BTC",
          symbol="BTCUSDT", pending_since=None, kind="signal"):
    return {
        "kind": kind, "name": name, "symbol": symbol,
        "text": f"{name}: {prev} -> {conf}",
        "prev": prev,
        "pending_since": pending_since,
        "snapshot": {
            "confluence": {"verdict": conf, "agree": 3},
            "price": price,
            "change_24h": 1.23,
            "timeframes": [{"label": "1W", "verdict": "LONG", "score": 4,
                            "rsi": 61.0, "macd_bull": True}],
            "levels": {"pivot": 100},
            "risk":   {"entry": price, "sl": 60000.0, "tp": 70000.0},
        },
    }


# ── CHỈ GHI TÍN HIỆU MUA/BÁN ──────────────────────────────────────────────────
def test_fetch_failure_KHONG_duoc_ghi(log):
    """Chốt lọc nằm trong append() chứ không ở người gọi – thêm loại alert mới
    sau này sẽ không lỡ lọt vào nhật ký vì ai đó quên kiểm ở đầu bên kia."""
    assert journal.append({"kind": "fetch_failure", "name": "BTC"}, path=log) is None
    assert not log.exists(), "không được tạo cả file"


def test_tin_hieu_that_thi_ghi(log):
    entry = journal.append(alert(), path=log)
    assert entry is not None
    assert log.exists()
    assert len(log.read_text(encoding="utf-8").strip().splitlines()) == 1


# ── ĐỦ TRƯỜNG ─────────────────────────────────────────────────────────────────
def test_ghi_du_gia_luc_ban(log):
    """Thiếu price thì sau này không cách nào chấm điểm tín hiệu đúng hay sai."""
    e = journal.append(alert(price=64128.0), path=log)
    assert e["price"] == 64128.0
    assert journal.read(path=log)[0]["price"] == 64128.0


def test_ghi_du_tu_dau_sang_dau(log):
    e = journal.append(alert(conf="STRONG LONG", prev="SHORT BIAS"), path=log)
    assert e["from"] == "SHORT BIAS"
    assert e["to"] == "STRONG LONG"


def test_first_seen_at_lay_tu_pending_since(log):
    moc = "2026-08-12T18:15:00+07:00"
    e = journal.append(alert(pending_since=moc), path=log)
    assert e["first_seen_at"] == moc
    assert e["at"] != moc, "lúc bắn phải khác lúc thấy – đó là độ trễ debounce"


def test_khong_co_pending_since_thi_first_seen_bang_luc_ban(log):
    """Lần quét đầu tiên confirm ngay, không qua debounce."""
    e = journal.append(alert(pending_since=None), path=log)
    assert e["first_seen_at"] == e["at"]


def test_giu_nguyen_text_da_gui_telegram(log):
    a = alert()
    e = journal.append(a, path=log)
    assert e["text"] == a["text"], "web và Telegram không được lệch nhau"


# ── MÚI GIỜ ───────────────────────────────────────────────────────────────────
def test_thoi_gian_kem_offset_07(log):
    """Khách xem từ múi giờ khác phải đọc được đúng là giờ Việt Nam."""
    e = journal.append(alert(), path=log)
    assert e["at"].endswith("+07:00")
    assert datetime.fromisoformat(e["at"]).utcoffset() == timedelta(hours=7)


def test_now_vn_dung_mui_gio():
    assert journal.now_vn().utcoffset() == timedelta(hours=7)


# ── ĐỌC ───────────────────────────────────────────────────────────────────────
def test_read_moi_nhat_truoc(log):
    for i in range(3):
        journal.append(alert(name=f"M{i}"), path=log)
    tens = [e["name"] for e in journal.read(path=log)]
    assert tens == ["M2", "M1", "M0"]


def test_read_limit(log):
    for i in range(5):
        journal.append(alert(name=f"M{i}"), path=log)
    assert len(journal.read(limit=2, path=log)) == 2
    assert journal.read(limit=2, path=log)[0]["name"] == "M4"


def test_read_loc_theo_ma(log):
    journal.append(alert(name="BTC", symbol="BTCUSDT"), path=log)
    journal.append(alert(name="ETH", symbol="ETHUSDT"), path=log)
    journal.append(alert(name="BTC", symbol="BTCUSDT"), path=log)

    assert len(journal.read(symbol="BTCUSDT", path=log)) == 2
    assert len(journal.read(symbol="ETH", path=log)) == 1, "lọc được cả bằng tên ngắn"


def test_chua_co_file_thi_tra_rong(log):
    assert journal.read(path=log) == []


def test_dong_hong_khong_lam_no(log):
    """Một dòng rác không được làm sập trang chủ."""
    journal.append(alert(name="TRUOC"), path=log)
    with open(log, "a", encoding="utf-8") as f:
        f.write("{day khong phai json\n")
    journal.append(alert(name="SAU"), path=log)

    tens = [e["name"] for e in journal.read(path=log)]
    assert tens == ["SAU", "TRUOC"], "bỏ đúng dòng hỏng, giữ phần còn lại"


def test_dong_trong_bi_bo_qua(log):
    journal.append(alert(), path=log)
    with open(log, "a", encoding="utf-8") as f:
        f.write("\n\n")
    assert len(journal.read(path=log)) == 1


# ── TELEGRAM HỎNG ─────────────────────────────────────────────────────────────
def test_telegram_hong_VAN_ghi(log):
    """Đó chính là lúc web có giá trị nhất."""
    e = journal.append(alert(), telegram_ok=False, path=log)
    assert e is not None
    assert journal.read(path=log)[0]["telegram_ok"] is False


def test_telegram_ok_duoc_ghi_lai(log):
    journal.append(alert(), telegram_ok=True, path=log)
    assert journal.read(path=log)[0]["telegram_ok"] is True


# ── GHI RA JSON ĐỌC ĐƯỢC ──────────────────────────────────────────────────────
def test_moi_dong_la_json_hop_le(log):
    journal.append(alert(), path=log)
    journal.append(alert(name="ETH"), path=log)
    for line in log.read_text(encoding="utf-8").strip().splitlines():
        json.loads(line)


def test_tieng_viet_khong_bi_escape(log):
    a = alert()
    a["text"] = "Tín hiệu đảo chiều mạnh"
    journal.append(a, path=log)
    assert "Tín hiệu đảo chiều mạnh" in log.read_text(encoding="utf-8")


# ── CẮM VÀO scan_once() ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_scan_once_ghi_nhat_ky_va_day_len_SSE(log, monkeypatch):
    """Canh đúng chỗ đã nghi: `_run(lambda ...)` trong scan_once có chạy thật không.

    Suy luận rằng nó đúng là không đủ – ở đây gọi thật một lượt quét giả lập.
    """
    from btcreport.server import scheduler
    from btcreport.server.state import STATE

    a = alert(name="BTC", prev="NEUTRAL", conf="STRONG LONG")
    monkeypatch.setattr(journal, "JOURNAL_FILE", log)
    monkeypatch.setattr(scheduler, "_scan_once",
                        lambda: ({}, [a], {"BTCUSDT": a["snapshot"]}))
    monkeypatch.setattr(scheduler, "send_telegram", lambda text: True)

    day_di = []
    monkeypatch.setattr(STATE, "publish",
                        lambda ev, data: day_di.append((ev, data)))

    await scheduler.scan_once()

    ghi = journal.read(path=log)
    assert len(ghi) == 1, "phải ghi đúng một dòng vào nhật ký"
    assert ghi[0]["telegram_ok"] is True

    sk = [d for ev, d in day_di if ev == "signal"]
    assert sk and sk[0]["entries"], "SSE phải mang entries để feed chèn realtime"


@pytest.mark.asyncio
async def test_telegram_hong_thi_scan_once_van_ghi(log, monkeypatch):
    from btcreport.server import scheduler
    from btcreport.server.state import STATE

    a = alert()
    monkeypatch.setattr(journal, "JOURNAL_FILE", log)
    monkeypatch.setattr(scheduler, "_scan_once",
                        lambda: ({}, [a], {"BTCUSDT": a["snapshot"]}))
    monkeypatch.setattr(scheduler, "send_telegram", lambda text: None)
    monkeypatch.setattr(STATE, "publish", lambda ev, data: None)

    await scheduler.scan_once()

    ghi = journal.read(path=log)
    assert len(ghi) == 1
    assert ghi[0]["telegram_ok"] is False
