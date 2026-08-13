"""Debounce và xử lý lỗi fetch của vòng quét.

Toàn bộ test dùng snapshot_fn giả — không mạng, không Telegram.
"""
import json

import pytest

from btcreport.config import CONFIRM_SCANS, MAX_CONSEC_FAILS
from btcreport.service.watch import load_state, save_state, scan_symbols

ONE = {"BTC": "BTCUSDT"}


def snap(conf, price=100.0):
    """Snapshot giả tối thiểu đủ để format_monitor_alert chạy."""
    tf = lambda label, v: {"label": label, "verdict": v, "action": "", "score": 0,
                           "rsi": 50.0, "macd": 0.0, "macd_signal": 0.0,
                           "macd_bull": False}
    verdict = "LONG" if "LONG" in conf else "SHORT" if "SHORT" in conf else "NEUTRAL"
    return {
        "confluence": {"verdict": conf, "agree": 2},
        "timeframes": [tf("1W", verdict), tf("1D", verdict),
                       tf("4H", verdict), tf("1H", verdict)],
        "levels": {"pivot": 100, "R1": 110, "R2": 120, "S1": 90, "S2": 80},
        "risk":   {"entry": price, "sl": None, "tp": None, "atr": 5.0, "rr": None},
        "price":  price,
        "change_24h": 1.23,
    }


def feed(*sequence):
    """snapshot_fn trả lần lượt từng phần tử. None = fetch lỗi."""
    it = iter(sequence)

    def fn(symbol):
        try:
            v = next(it)
        except StopIteration:
            raise AssertionError("scan gọi nhiều lần hơn dữ liệu đã chuẩn bị")
        return (False, None) if v is None else (True, snap(v))
    return fn


def run(state, *sequence):
    """Chạy N lượt quét, mỗi lượt một phần tử. Trả (state, list alert mỗi lượt)."""
    per_scan = []
    for item in sequence:
        state, alerts = scan_symbols(state, ONE, snapshot_fn=feed(item),
                                     log=lambda *_: None)
        per_scan.append(alerts)
    return state, per_scan


# ── Debounce ─────────────────────────────────────────────────────────────────
def test_lan_dau_bao_ngay():
    """Chưa có baseline thì không đợi xác nhận – báo trạng thái ban đầu luôn."""
    state, scans = run({}, "NEUTRAL")
    assert len(scans[0]) == 1
    assert "Trạng thái ban đầu" in scans[0][0]["text"]
    assert state["BTCUSDT"]["confluence"] == "NEUTRAL"


def test_khong_doi_thi_im_lang():
    state, scans = run({}, "NEUTRAL", "NEUTRAL", "NEUTRAL")
    assert scans[0] and not scans[1] and not scans[2]


def test_doi_mot_lan_chua_bao():
    state, scans = run({}, "NEUTRAL", "LONG BIAS")
    assert not scans[1], "mới lật 1 lần đã báo là hỏng debounce"
    assert state["BTCUSDT"]["pending"] == "LONG BIAS"
    assert state["BTCUSDT"]["pending_count"] == 1
    assert state["BTCUSDT"]["confluence"] == "NEUTRAL", "chưa xác nhận thì chưa đổi state"


def test_doi_du_hai_lan_moi_bao():
    state, scans = run({}, "NEUTRAL", "LONG BIAS", "LONG BIAS")
    assert not scans[1]
    assert len(scans[2]) == 1
    assert "Signal thay đổi" in scans[2][0]["text"]
    assert state["BTCUSDT"]["confluence"] == "LONG BIAS"
    assert state["BTCUSDT"]["pending"] == ""


def test_lat_gia_khong_sinh_alert_nao():
    """NEUTRAL → LONG → NEUTRAL: nhiễu quanh ngưỡng, phải nuốt sạch."""
    state, scans = run({}, "NEUTRAL", "LONG BIAS", "NEUTRAL")
    assert not scans[1] and not scans[2]
    assert state["BTCUSDT"]["confluence"] == "NEUTRAL"
    assert state["BTCUSDT"]["pending"] == ""
    assert state["BTCUSDT"]["pending_count"] == 0


def test_lat_qua_lai_nhieu_lan_van_im():
    state, scans = run({}, "NEUTRAL", "LONG BIAS", "NEUTRAL",
                       "LONG BIAS", "NEUTRAL", "LONG BIAS")
    assert sum(len(a) for a in scans[1:]) == 0


def test_pending_khac_nhau_thi_dem_lai_tu_dau():
    """LONG rồi SHORT: không được cộng dồn pending_count qua hai giá trị khác nhau."""
    state, scans = run({}, "NEUTRAL", "LONG BIAS", "SHORT BIAS")
    assert not scans[2]
    assert state["BTCUSDT"]["pending"] == "SHORT BIAS"
    assert state["BTCUSDT"]["pending_count"] == 1


def test_confirm_scans_dung_gia_tri_config():
    assert CONFIRM_SCANS == 2


# ── Fetch lỗi ────────────────────────────────────────────────────────────────
def test_fetch_loi_khong_lam_mat_state():
    state, scans = run({}, "LONG BIAS", None, None)
    assert state["BTCUSDT"]["confluence"] == "LONG BIAS", "lỗi fetch không được xoá state"
    assert state["BTCUSDT"]["consec_fails"] == 2


def test_fetch_loi_khong_bi_coi_la_khong_doi():
    """Lỗi phải đếm riêng, không được im lặng như trường hợp 'giống state cũ'."""
    state, _ = run({}, "LONG BIAS", None)
    assert state["BTCUSDT"].get("consec_fails") == 1


def test_canh_bao_dung_nguong_fetch_loi():
    state, scans = run({}, "LONG BIAS", *([None] * MAX_CONSEC_FAILS))
    fails = [a for s in scans for a in s if a["kind"] == "fetch_failure"]
    assert len(fails) == 1, "phải cảnh báo đúng MỘT lần, không spam mỗi lượt"
    assert f"{MAX_CONSEC_FAILS} lần liên tiếp" in fails[0]["text"]


def test_khoi_phuc_thi_reset_bo_dem():
    state, _ = run({}, "LONG BIAS", None, None, "LONG BIAS")
    assert state["BTCUSDT"]["consec_fails"] == 0


def test_khong_canh_bao_lai_khi_van_loi_tiep():
    state, scans = run({}, "LONG BIAS", *([None] * (MAX_CONSEC_FAILS + 3)))
    fails = [a for s in scans for a in s if a["kind"] == "fetch_failure"]
    assert len(fails) == 1


# ── Hình dạng alert ──────────────────────────────────────────────────────────
def test_alert_du_khoa():
    """`prev` và `pending_since` là hợp đồng với journal.

    Cố ý so bằng `==` chứ không phải `>=`: journal đọc thẳng mấy khoá này, đổi tên
    hay bỏ đi là nhật ký mất trường mà không ai biết cho tới lúc xem lại lịch sử.
    """
    _, scans = run({}, "NEUTRAL")
    a = scans[0][0]
    assert set(a) == {"kind", "name", "symbol", "text", "snapshot",
                      "prev", "pending_since"}
    assert a["kind"] == "signal" and a["symbol"] == "BTCUSDT" and a["name"] == "BTC"
    assert a["snapshot"]["confluence"]["verdict"] == "NEUTRAL"


def test_pending_since_dat_luc_bat_dau_cho_va_khong_bi_reset():
    """Mốc thị trường THẬT SỰ đổi, khác lúc alert bắn ra.

    Debounce giữ CONFIRM_SCANS lượt mới báo. Nếu pending_since bị ghi đè mỗi lượt
    quét thì nó thành = thời điểm bắn, và nhật ký mất luôn khả năng nói độ trễ thật.
    """
    state, _ = run({}, "NEUTRAL")            # confirm lần đầu
    entry = state["BTCUSDT"]

    state, scans = run(state, "STRONG LONG")  # lượt 1: bắt đầu chờ
    moc = state["BTCUSDT"]["pending_since"]
    assert moc, "phải đặt mốc ngay lượt đầu thấy đổi"
    assert scans[0] == [], "chưa đủ debounce thì chưa được bắn"

    state, scans = run(state, "STRONG LONG")  # lượt 2: đủ, bắn
    assert scans[0], "đủ debounce thì phải bắn"
    assert scans[0][0]["pending_since"] == moc, "mốc phải giữ nguyên, không bị ghi đè"


# ── SL/TP THEO HƯỚNG CONFLUENCE ───────────────────────────────────────────────
@pytest.fixture
def gia_lap_nguon(monkeypatch):
    """get_snapshot thật, nhưng verdict từng khung do test đặt.

    Giữ nguyên `confluence()` và `risk_levels()` thật – nếu mock cả hai thì test chỉ
    còn kiểm chính cái mock của mình.
    """
    from btcreport.service import watch

    nen = [{"ts": i * 1000, "open": 100.0, "high": 104.0, "low": 96.0,
            "close": 100.0, "volume": 10.0} for i in range(100)]
    monkeypatch.setattr(watch, "fetch_klines", lambda *a: nen)
    monkeypatch.setattr(watch, "fetch_ticker",
                        lambda s: {"lastPrice": "100.0", "priceChangePercent": "1.0"})

    def dat(**theo_khung):
        monkeypatch.setattr(watch, "analyze_timeframe", lambda label, candles: {
            "label": label, "verdict": theo_khung[label], "action": "", "score": 0,
            "rsi": 50.0, "macd": 0.0, "macd_signal": 0.0, "macd_bull": False,
        })
        ok, snap = watch.get_snapshot("BTCUSDT")
        assert ok
        return snap

    return dat


def test_sl_tp_theo_confluence_chu_khong_theo_4H(gia_lap_nguon):
    """Chuyện đã xảy ra thật: 12/08/2026 PAXG báo LONG BIAS lên Telegram trong khi
    khung 4H đang NEUTRAL → sl=tp=None, tín hiệu có hướng mà không kèm mức nào.

    Chấm điểm mà không sửa chỗ này thì con số ra được không biết đang đo gì.
    """
    snap = gia_lap_nguon(**{"1W": "LONG", "1D": "LONG", "4H": "NEUTRAL", "1H": "NEUTRAL"})

    assert snap["confluence"]["verdict"] == "LONG BIAS"
    assert snap["timeframes"][2]["verdict"] == "NEUTRAL", "khung 4H vẫn NEUTRAL"
    assert snap["risk"]["sl"] is not None, "đã báo có hướng thì phải kèm mức"
    assert snap["risk"]["sl"] < snap["risk"]["entry"] < snap["risk"]["tp"]


def test_4H_nguoc_huong_confluence_thi_muc_theo_confluence(gia_lap_nguon):
    """Ca tệ nhất: SL/TP đặt ngược chiều tín hiệu được báo."""
    snap = gia_lap_nguon(**{"1W": "SHORT", "1D": "SHORT", "4H": "LONG", "1H": "SHORT"})

    assert snap["confluence"]["verdict"] == "STRONG SHORT"
    assert snap["timeframes"][2]["verdict"] == "LONG"
    assert snap["risk"]["tp"] < snap["risk"]["entry"] < snap["risk"]["sl"], \
        "SHORT thì chốt lời nằm DƯỚI giá vào, dừng lỗ nằm trên"


def test_confluence_neutral_thi_van_khong_de_xuat_gi(gia_lap_nguon):
    """Đứng ngoài thì không đưa mức nào – vào lệnh khi chưa có hướng là tự bắn
    vào chân, đúng như risk_levels() vẫn làm."""
    snap = gia_lap_nguon(**{"1W": "LONG", "1D": "SHORT", "4H": "NEUTRAL", "1H": "NEUTRAL"})

    assert snap["confluence"]["verdict"] == "NEUTRAL"
    assert snap["risk"]["sl"] is None and snap["risk"]["tp"] is None


def test_scan_khong_tu_gui_telegram(monkeypatch):
    """Bảo đảm scan_symbols thuần: nếu nó lỡ gọi send_telegram thì test này nổ."""
    import btcreport.notify.telegram as tg

    def boom(*a, **kw):
        raise AssertionError("scan_symbols không được tự gửi Telegram")

    monkeypatch.setattr(tg, "send_telegram", boom)
    run({}, "NEUTRAL", "LONG BIAS", "LONG BIAS")


# ── State file ───────────────────────────────────────────────────────────────
def test_ghi_doc_state_giu_nguyen_noi_dung(tmp_path):
    p = tmp_path / "s.json"
    data = {"BTCUSDT": {"confluence": "SHORT BIAS", "timestamp": "12/08/2026 15:00",
                        "pending": "", "pending_count": 0}}
    save_state(data, p)
    assert load_state(p) == data


def test_ghi_state_la_atomic(tmp_path):
    """Ghi xong không được để lại file .tmp."""
    p = tmp_path / "s.json"
    save_state({"A": 1}, p)
    assert not (tmp_path / "s.json.tmp").exists()
    assert json.loads(p.read_text(encoding="utf-8")) == {"A": 1}


def test_state_hong_thi_tra_dict_rong(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{ khong phai json", encoding="utf-8")
    assert load_state(p) == {}


def test_state_khong_ton_tai_tra_dict_rong(tmp_path):
    assert load_state(tmp_path / "chua-co.json") == {}


# ── Nhiều mã ─────────────────────────────────────────────────────────────────
def test_mot_ma_loi_khong_anh_huong_ma_khac():
    calls = {"n": 0}

    def fn(symbol):
        calls["n"] += 1
        if symbol == "ETHUSDT":
            return False, None
        return True, snap("LONG BIAS")

    state, alerts = scan_symbols({}, {"BTC": "BTCUSDT", "ETH": "ETHUSDT"},
                                snapshot_fn=fn, log=lambda *_: None)
    assert state["BTCUSDT"]["confluence"] == "LONG BIAS"
    assert state["ETHUSDT"]["consec_fails"] == 1
    assert [a["symbol"] for a in alerts] == ["BTCUSDT"]
