"""Chấm điểm tín hiệu: chạm TP trước hay SL trước.

Trọng tâm là mấy chỗ dễ tự lừa mình:

  - nến xảy ra TRƯỚC lúc bắn tín hiệu không được tính (bịa thắng/thua từ quá khứ)
  - `expired` phải nằm trong mẫu số của tỷ lệ thắng
  - chưa đủ mẫu thì `win_rate` phải là None, không phải một con số nhỏ trông có vẻ đúng
  - nến chạm cả TP lẫn SL tính là THUA và bị đánh dấu

Không gọi mạng: mọi test tự dựng nến và tiêm `fetch`.
"""
from datetime import datetime, timedelta

import pytest

from btcreport.engine.signals import LONG, NEUTRAL, SHORT, direction
from btcreport.service import outcome
from btcreport.service.journal import TZ_VN, signal_id

T0 = datetime(2026, 8, 1, 10, 0, tzinfo=TZ_VN)

# entry 100 · sl 90 · tp 120 ⇒ đơn vị rủi ro = 10, thắng đúng +2R, thua đúng -1R
ENTRY, SL, TP = 100.0, 90.0, 120.0


def tin(at=T0, symbol="BTCUSDT", to="STRONG LONG", entry=ENTRY, sl=SL, tp=TP, **kw):
    e = {
        "id": f"{symbol}@{at.isoformat(timespec='seconds')}",
        "at": at.isoformat(timespec="seconds"),
        "symbol": symbol, "name": symbol[:3], "to": to,
        "price": entry,
        "risk": {"entry": entry, "sl": sl, "tp": tp, "atr": 6.67, "rr": 2.0},
    }
    e.update(kw)
    return e


def nen(at, high, low, close=None):
    return {"ts": int(at.timestamp() * 1000), "open": ENTRY,
            "high": high, "low": low, "close": close if close is not None else ENTRY,
            "volume": 1.0}


def gio(n):
    return T0 + timedelta(hours=n)


# ── HƯỚNG LẤY TỪ CONFLUENCE ───────────────────────────────────────────────────
@pytest.mark.parametrize("verdict,mong_doi", [
    ("STRONG LONG", LONG), ("LONG BIAS", LONG),
    ("STRONG SHORT", SHORT), ("SHORT BIAS", SHORT),
    ("NEUTRAL", NEUTRAL), ("", NEUTRAL), (None, NEUTRAL),
])
def test_direction(verdict, mong_doi):
    assert direction(verdict) == mong_doi


def test_verdict_la_khong_lam_cam_monitor():
    """Hàm này nằm trên đường đi của mọi lượt quét. Verdict thêm sau này mà ném
    lỗi ở đây là chết cả vòng quét chứ không phải hỏng một tính năng phụ."""
    assert direction("CAI GI DO MOI") == NEUTRAL


# ── THẮNG / THUA ──────────────────────────────────────────────────────────────
def test_cham_tp_truoc_la_thang():
    r = outcome.evaluate_one(tin(), [nen(gio(1), high=121, low=99)], now=gio(2))
    assert r["status"] == outcome.WIN
    assert r["r"] == 2.0, "TP = 3×ATR, SL = 1.5×ATR ⇒ đúng +2R"
    assert r["exit_at"].startswith("2026-08-01T11:00")


def test_cham_sl_truoc_la_thua():
    r = outcome.evaluate_one(tin(), [nen(gio(1), high=105, low=89)], now=gio(2))
    assert r["status"] == outcome.LOSS
    assert r["r"] == -1.0


def test_nen_dau_tien_cham_moi_tinh():
    """Nến sau đó chạm TP không cứu được tín hiệu đã dính SL trước."""
    r = outcome.evaluate_one(tin(), [
        nen(gio(1), high=105, low=89),        # dính SL
        nen(gio(2), high=130, low=100),       # sau mới lên TP
    ], now=gio(5))
    assert r["status"] == outcome.LOSS


def test_short_dao_nguoc_huong():
    t = tin(to="STRONG SHORT", entry=100.0, sl=110.0, tp=80.0)
    thang = outcome.evaluate_one(t, [nen(gio(1), high=101, low=79)], now=gio(2))
    thua  = outcome.evaluate_one(t, [nen(gio(1), high=111, low=95)], now=gio(2))
    assert thang["status"] == outcome.WIN and thang["r"] == 2.0
    assert thua["status"] == outcome.LOSS and thua["r"] == -1.0


# ── CHỐT QUAN TRỌNG NHẤT: KHÔNG ĂN GIÁ CỦA QUÁ KHỨ ────────────────────────────
def test_nen_TRUOC_luc_ban_khong_duoc_tinh():
    """Tín hiệu không thể bị đóng bởi giá xảy ra trước khi nó tồn tại.

    Nến chứa `at` gần như luôn mở trước đó vài chục phút. Không loại nó ra là bịa
    ra thắng/thua từ quá khứ – và bịa theo hướng nào thì tuỳ hôm đó thị trường đi
    đâu, tức là một cái sai không có quy luật, không ai phát hiện được từ con số.
    """
    r = outcome.evaluate_one(tin(), [
        nen(T0 - timedelta(hours=1), high=999, low=1),   # quá khứ: chạm cả hai
        nen(gio(1), high=105, low=95),                   # sau đó: không chạm gì
    ], now=gio(2))
    assert r["status"] == outcome.OPEN, "nến quá khứ phải bị bỏ hoàn toàn"


def test_nen_dung_luc_ban_thi_van_tinh():
    """Biên: nến mở đúng giây bắn tín hiệu là hợp lệ."""
    r = outcome.evaluate_one(tin(), [nen(T0, high=121, low=99)], now=gio(2))
    assert r["status"] == outcome.WIN


# ── NẾN CHẠM CẢ HAI ───────────────────────────────────────────────────────────
def test_cham_ca_hai_trong_mot_nen_la_THUA_va_bi_danh_dau():
    """Kline không nói cái nào xảy ra trước trong lòng một cây nến.

    Đo thật 13/08/2026: 0/1000 nến 1H của cả 3 mã đủ biên độ để rơi vào ca này –
    nhưng 0/1000 không phải 'không bao giờ'.
    """
    r = outcome.evaluate_one(tin(), [nen(gio(1), high=121, low=89)], now=gio(2))
    assert r["status"] == outcome.LOSS
    assert r["ambiguous"] is True
    assert r["r"] == -1.0


def test_binh_thuong_thi_khong_bat_co_ambiguous():
    r = outcome.evaluate_one(tin(), [nen(gio(1), high=121, low=99)], now=gio(2))
    assert not r.get("ambiguous")


# ── HẾT HẠN ───────────────────────────────────────────────────────────────────
def test_chua_cham_gi_va_chua_het_han_thi_dang_chay():
    r = outcome.evaluate_one(tin(), [nen(gio(1), high=105, low=95)], now=gio(24))
    assert r["status"] == outcome.OPEN
    assert "r" not in r


def test_qua_han_thi_expired_kem_R_that():
    """`expired` phải có R thật chứ không phải 0 – tín hiệu đi ngang 7 ngày vẫn
    có lãi/lỗ, và nó phải hiện ra."""
    sau = T0 + timedelta(days=outcome.SIGNAL_EXPIRY_DAYS, hours=1)
    r = outcome.evaluate_one(
        tin(), [nen(gio(1), high=105, low=95, close=105.0)], now=sau)
    assert r["status"] == outcome.EXPIRED
    assert r["r"] == 0.5, "(105-100)/10 = +0.5R"


def test_nen_ngoai_han_khong_duoc_tinh():
    """Chạm TP ở ngày thứ 9 thì tín hiệu đã hết hạn từ ngày thứ 7 rồi."""
    sau = T0 + timedelta(days=10)
    r = outcome.evaluate_one(tin(), [
        nen(gio(1), high=105, low=95, close=100.0),
        nen(T0 + timedelta(days=9), high=200, low=100),
    ], now=sau)
    assert r["status"] == outcome.EXPIRED


# ── BỎ QUA ────────────────────────────────────────────────────────────────────
def test_neutral_thi_bo_qua():
    r = outcome.evaluate_one(tin(to="NEUTRAL"), [], now=gio(2))
    assert r["status"] == outcome.SKIPPED
    assert r["reason"] == "khong-co-huong"


def test_khong_co_muc_thi_bo_qua():
    """Bản ghi cũ, từ trước khi SL/TP tính theo hướng confluence."""
    r = outcome.evaluate_one(tin(sl=None, tp=None), [], now=gio(2))
    assert r["status"] == outcome.SKIPPED
    assert r["reason"] == "khong-co-muc"


# ── ĐÓNG SỚM KHI ĐỔI HƯỚNG ────────────────────────────────────────────────────
def test_doi_huong_thi_dong_cai_cu():
    cu  = tin(at=T0, to="STRONG LONG")
    moi = tin(at=gio(5), to="STRONG SHORT")
    marks = outcome.closing_marks([cu, moi])
    assert signal_id(cu) in marks
    assert signal_id(moi) not in marks, "cái mới chưa bị gì đóng"


def test_cung_huong_thi_KHONG_dong():
    """SHORT BIAS → STRONG SHORT là quan điểm mạnh lên, không phải đảo chiều."""
    cu  = tin(at=T0, to="SHORT BIAS")
    moi = tin(at=gio(5), to="STRONG SHORT")
    assert outcome.closing_marks([cu, moi]) == {}


def test_doi_sang_neutral_cung_dong():
    """NEUTRAL nghĩa là đứng ngoài, tức là thoát."""
    cu  = tin(at=T0, to="STRONG LONG")
    moi = tin(at=gio(5), to="NEUTRAL")
    assert signal_id(cu) in outcome.closing_marks([cu, moi])


def test_ma_khac_khong_dong_lan_nhau():
    btc = tin(at=T0,     symbol="BTCUSDT", to="STRONG LONG")
    eth = tin(at=gio(5), symbol="ETHUSDT", to="STRONG SHORT")
    assert outcome.closing_marks([btc, eth]) == {}


def test_superseded_lay_gia_luc_dong_va_R_that():
    r = outcome.evaluate_one(
        tin(), [nen(gio(1), high=108, low=99, close=106.0),
                nen(gio(9), high=130, low=100, close=125.0)],
        now=gio(20), closed_at=gio(5))
    assert r["status"] == outcome.SUPERSEDED
    assert r["exit"] == 106.0, "giá đóng của nến cuối TRƯỚC mốc đóng"
    assert r["r"] == 0.6


def test_cham_TP_truoc_moc_dong_thi_van_la_THANG():
    """Đóng sớm không được cướp mất một tín hiệu đã thắng xong."""
    r = outcome.evaluate_one(tin(), [nen(gio(1), high=121, low=99)],
                             now=gio(20), closed_at=gio(5))
    assert r["status"] == outcome.WIN


# ── ĐỊNH DANH ─────────────────────────────────────────────────────────────────
def test_ban_ghi_cu_khong_co_id_van_khoa_dung():
    """File lịch sử đã hứa là bất biến – khoá phải suy được từ dữ liệu có sẵn."""
    moi = tin()
    cu  = {k: v for k, v in moi.items() if k != "id"}
    assert signal_id(cu) == signal_id(moi) == "BTCUSDT@2026-08-01T10:00:00+07:00"


# ── LƯU / ĐỌC ─────────────────────────────────────────────────────────────────
@pytest.fixture
def kq(tmp_path):
    return tmp_path / "outcomes.jsonl"


def test_chi_ghi_ket_qua_da_nga_ngu(kq):
    """`open` tính lại mỗi lần đọc chứ không lưu – file chỉ chứa sự thật đã chốt."""
    outcome.save([
        {"id": "a", "status": outcome.WIN, "r": 2.0},
        {"id": "b", "status": outcome.OPEN},
        {"id": "c", "status": outcome.SKIPPED},
    ], path=kq)
    assert set(outcome.read(kq)) == {"a", "c"}


def test_khong_co_gi_nga_ngu_thi_khong_tao_file(kq):
    outcome.save([{"id": "b", "status": outcome.OPEN}], path=kq)
    assert not kq.exists()


def test_dong_hong_khong_lam_no(kq):
    outcome.save([{"id": "a", "status": outcome.WIN, "r": 2.0}], path=kq)
    with open(kq, "a", encoding="utf-8") as f:
        f.write("{day khong phai json\n\n")
    outcome.save([{"id": "b", "status": outcome.LOSS, "r": -1.0}], path=kq)
    assert set(outcome.read(kq)) == {"a", "b"}


def test_dong_sau_de_dong_truoc(kq):
    outcome.save([{"id": "a", "status": outcome.OPEN, "r": None}], path=kq)  # không ghi
    outcome.save([{"id": "a", "status": outcome.WIN, "r": 2.0}], path=kq)
    outcome.save([{"id": "a", "status": outcome.LOSS, "r": -1.0}], path=kq)
    assert outcome.read(kq)["a"]["status"] == outcome.LOSS


def test_chua_co_file_thi_tra_rong(kq):
    assert outcome.read(kq) == {}


# ── CHẤM CẢ NHẬT KÝ ───────────────────────────────────────────────────────────
def test_evaluate_bo_qua_cai_da_cham_roi():
    goi = []

    def fetch(sym, tf, a, b):
        goi.append(sym)
        return [nen(gio(1), high=121, low=99)]

    t = tin()
    rs = outcome.evaluate([t], now=gio(3), fetch=fetch,
                          existing={signal_id(t): {"status": outcome.WIN}})
    assert rs == [] and goi == [], "không được tốn một request nào cho cái đã xong"


def test_evaluate_khong_goi_mang_cho_tin_hieu_chac_chan_skipped():
    goi = []

    def fetch(sym, tf, a, b):
        goi.append(sym)
        return []

    rs = outcome.evaluate([tin(to="NEUTRAL"), tin(at=gio(1), sl=None, tp=None)],
                          now=gio(3), fetch=fetch, existing={})
    assert goi == []
    assert [r["status"] for r in rs] == [outcome.SKIPPED, outcome.SKIPPED]


def test_evaluate_loi_mang_khong_giet_ca_luot():
    def fetch(sym, tf, a, b):
        if sym == "ETHUSDT":
            raise RuntimeError("Binance 451")
        return [nen(gio(1), high=121, low=99)]

    rs = outcome.evaluate([tin(symbol="ETHUSDT"), tin(symbol="BTCUSDT")],
                          now=gio(3), fetch=fetch, existing={})
    assert [r["symbol"] for r in rs] == ["BTCUSDT"], "mã lỗi bị bỏ qua, mã kia vẫn chấm"


def test_evaluate_gan_dung_moc_dong_som():
    rs = outcome.evaluate(
        [tin(at=T0, to="STRONG LONG"), tin(at=gio(5), to="STRONG SHORT")],
        now=gio(20), existing={},
        fetch=lambda *a: [nen(gio(1), high=105, low=99, close=104.0)])
    assert rs[0]["status"] == outcome.SUPERSEDED
    assert rs[1]["status"] == outcome.OPEN


# ── THỐNG KÊ ──────────────────────────────────────────────────────────────────
def kqua(status, r=None, symbol="BTCUSDT", **kw):
    return {"id": f"x{id(kw)}", "symbol": symbol, "status": status, "r": r, **kw}


def test_chua_du_mau_thi_KHONG_hien_ty_le():
    """Con số thuyết phục trên mẫu bé còn tệ hơn không có con số nào."""
    tk = outcome.stats([kqua(outcome.WIN, 2.0)] * 5 + [kqua(outcome.LOSS, -1.0)] * 2,
                       min_n=20)
    assert tk["overall"]["win_rate"] is None
    assert tk["overall"]["n"] == 7
    assert tk["overall"]["counts"]["win"] == 5, "số đếm thô thì vẫn hiện"


def test_du_mau_thi_hien_kem_n():
    rs = [kqua(outcome.WIN, 2.0)] * 12 + [kqua(outcome.LOSS, -1.0)] * 8
    tk = outcome.stats(rs, min_n=20)
    assert tk["overall"]["win_rate"] == 60.0
    assert tk["overall"]["n"] == 20


def test_expired_NAM_TRONG_mau_so():
    """Vứt expired đi là cách phổ biến nhất khiến loại thống kê này nói dối:
    tín hiệu không đi đâu cả vẫn là tín hiệu sai."""
    rs = [kqua(outcome.WIN, 2.0)] * 10 + [kqua(outcome.EXPIRED, 0.1)] * 10
    tk = outcome.stats(rs, min_n=20)
    assert tk["overall"]["n"] == 20
    assert tk["overall"]["win_rate"] == 50.0, "không phải 100%"


def test_superseded_ngoai_mau_so_nhung_TRONG_R_trung_binh():
    """Nó chưa được chạy hết đời mình nên không tính đúng/sai, nhưng lãi/lỗ của nó
    là thật và phải hiện ra."""
    rs = [kqua(outcome.WIN, 2.0)] * 20 + [kqua(outcome.SUPERSEDED, -0.5)] * 4
    tk = outcome.stats(rs, min_n=20)
    o = tk["overall"]
    assert o["n"] == 20 and o["win_rate"] == 100.0
    assert o["n_r"] == 24, "R tính trên nhiều mẫu hơn tỷ lệ thắng"
    assert o["avg_r"] == round((2.0 * 20 - 0.5 * 4) / 24, 3)


def test_skipped_va_open_khong_vao_mau_so_nao():
    rs = [kqua(outcome.WIN, 2.0)] + [kqua(outcome.SKIPPED)] * 9 + [kqua(outcome.OPEN)] * 9
    o = outcome.stats(rs, min_n=1)["overall"]
    assert o["n"] == 1 and o["win_rate"] == 100.0 and o["n_r"] == 1


def test_thong_ke_tach_theo_ma():
    rs = ([kqua(outcome.WIN, 2.0, symbol="BTCUSDT")] * 2 +
          [kqua(outcome.LOSS, -1.0, symbol="ETHUSDT")])
    tk = outcome.stats(rs, min_n=1)
    assert tk["by_symbol"]["BTCUSDT"]["win_rate"] == 100.0
    assert tk["by_symbol"]["ETHUSDT"]["win_rate"] == 0.0


def test_thong_ke_dem_so_nen_map_mo():
    rs = [kqua(outcome.LOSS, -1.0, ambiguous=True), kqua(outcome.LOSS, -1.0)]
    assert outcome.stats(rs, min_n=1)["overall"]["ambiguous"] == 1


def test_chua_co_gi_thi_khong_no():
    o = outcome.stats([], min_n=20)["overall"]
    assert o["n"] == 0 and o["win_rate"] is None and o["avg_r"] is None


def test_load_all_khong_goi_mang(kq, monkeypatch):
    """Trang chủ không được phụ thuộc Binance để mở lên được."""
    monkeypatch.setattr(outcome, "fetch_klines_range",
                        lambda *a: pytest.fail("không được gọi mạng"))
    t = tin()
    outcome.save([{**t, "id": signal_id(t), "status": outcome.WIN, "r": 2.0}], path=kq)
    rs, tk = outcome.load_all([t, tin(at=gio(9))], path=kq, min_n=1)
    assert [r["status"] for r in rs] == [outcome.WIN, outcome.OPEN]
    assert tk["overall"]["win_rate"] == 100.0
