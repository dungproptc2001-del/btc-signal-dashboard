"""Chấm điểm tín hiệu: chạm TP trước hay SL trước.

Ở tầng `service` cùng chỗ với `journal` – nó đọc nhật ký và gọi Binance, không biết
gì về web. Nhờ vậy `apps/score.py` chạy tay được mà không cần dựng server.

## Hai file, một chiều

    data/signals.jsonl     BẤT BIẾN. Ghi xong không bao giờ sửa.
    data/outcomes.jsonl    Kết quả đã ngã ngũ, khoá theo journal.signal_id().

Chỉ ghi kết quả ĐÃ NGÃ NGŨ. Tín hiệu đang chạy tính lại mỗi lần đọc chứ không lưu –
file chỉ chứa sự thật đã chốt, mỗi dòng đọc một lần là hiểu.

Muốn chấm lại theo quy tắc khác thì XOÁ outcomes.jsonl. Dữ liệu gốc không suy suyển.

## Vì sao nến 1H là đủ

Khoảng SL→TP luôn bằng (ATR_MULT_SL + ATR_MULT_TP) × ATR(4H) = 4.5 × ATR(4H). Một nến
chạm được cả hai thì biên độ của nó phải >= khoảng đó. Đo thật ngày 13/08/2026 trên
1000 nến gần nhất: BTC 0/1000, ETH 0/1000, PAXG 0/1000 – cả 1H lẫn 15m.

Hiếm có tính cấu trúc chứ không phải may: ATR tự nở ra khi thị trường biến động, nên
khoảng SL→TP giãn theo. Thị trường càng loạn thì ngưỡng càng cao.

Vẫn giữ nhánh xử lý ca đó, vì 0/1000 không phải "không bao giờ".
"""
import json
from datetime import datetime, timedelta

from ..config import (
    ATR_MULT_SL, ATR_MULT_TP, OUTCOME_FILE, OUTCOME_PROBE_TF,
    SIGNAL_EXPIRY_DAYS, STATS_MIN_N,
)
from ..engine.signals import LONG, NEUTRAL, SHORT, direction
from ..sources.binance import fetch_klines_range
from .journal import TZ_VN, now_vn, signal_id

WIN, LOSS, EXPIRED, SUPERSEDED, SKIPPED, OPEN = (
    "win", "loss", "expired", "superseded", "skipped", "open")

# Ngã ngũ rồi thì ghi file và không bao giờ chấm lại.
FINAL = (WIN, LOSS, EXPIRED, SUPERSEDED, SKIPPED)


def _dt(iso):
    """Đọc mốc ISO trong nhật ký. Thiếu tzinfo thì coi là giờ VN – nhật ký luôn
    ghi kèm +07:00, nhưng bản ghi tay hoặc file sửa bằng notepad thì chưa chắc."""
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=TZ_VN)


# ── CHẤM MỘT TÍN HIỆU ─────────────────────────────────────────────────────────
def _r(direc, entry, sl, exit_price):
    """Lãi/lỗ tính bằng bội số rủi ro. |entry - sl| = 1.5×ATR, TP = 3×ATR
    ⇒ thắng đúng +2.0, thua đúng -1.0."""
    risk = abs(entry - sl)
    if not risk:
        return None
    return round((exit_price - entry) / risk * (1 if direc == LONG else -1), 3)


def evaluate_one(entry, candles, *, now=None, closed_at=None):
    """Chấm một tín hiệu. Thuần tuý: nến đưa vào sẵn, không gọi mạng.

    `closed_at` là mốc bị tín hiệu đổi hướng đóng sớm (None nếu không có).
    """
    now  = now or now_vn()
    at   = _dt(entry.get("at"))
    direc = direction(entry.get("to"))
    risk = entry.get("risk") or {}
    sl, tp = risk.get("sl"), risk.get("tp")
    price  = risk.get("entry") or entry.get("price")

    base = {"id": signal_id(entry), "symbol": entry.get("symbol"),
            "at": entry.get("at"), "direction": direc,
            "entry": price, "sl": sl, "tp": tp,
            "probe_tf": OUTCOME_PROBE_TF, "evaluated_at": now.isoformat(timespec="seconds")}

    def out(status, **kw):
        return {**base, "status": status, **kw}

    if direc == NEUTRAL:
        return out(SKIPPED, reason="khong-co-huong")
    if sl is None or tp is None or not price:
        # Chỉ còn ở bản ghi cũ – từ khi SL/TP tính theo hướng confluence thì mọi
        # tín hiệu có hướng đều kèm mức.
        return out(SKIPPED, reason="khong-co-muc")
    if at is None:
        return out(SKIPPED, reason="mocgio-hong")

    han = at + timedelta(days=SIGNAL_EXPIRY_DAYS)

    # Nến mở TRƯỚC lúc bắn không được tính. Tín hiệu không thể bị đóng bởi giá xảy
    # ra trước khi nó tồn tại; nến chứa `at` gần như luôn mở trước đó vài chục phút.
    # Bỏ sót chốt này là bịa ra thắng/thua từ quá khứ.
    moc = at.timestamp() * 1000
    het = han.timestamp() * 1000
    nen = [c for c in candles if moc <= c["ts"] <= het]

    # Bị đóng sớm thì giá SAU mốc đó không liên quan gì tới tín hiệu này nữa. Quét
    # cả cửa sổ rồi mới xét mốc đóng là cho một cây nến ba ngày sau "thắng" hộ một
    # lệnh đã đóng từ lâu.
    cham = [c for c in nen if c["ts"] <= closed_at.timestamp() * 1000] if closed_at else nen

    for c in cham:
        if direc == LONG:
            cham_tp, cham_sl = c["high"] >= tp, c["low"] <= sl
        else:
            cham_tp, cham_sl = c["low"] <= tp, c["high"] >= sl

        khi = datetime.fromtimestamp(c["ts"] / 1000, TZ_VN).isoformat(timespec="seconds")

        if cham_tp and cham_sl:
            # Kline không nói cái nào xảy ra trước trong lòng một cây nến. Chọn bi
            # quan để không bao giờ thổi phồng thành tích, và bật cờ để nó không
            # lẩn vào đám đông.
            return out(LOSS, exit=sl, exit_at=khi, r=_r(direc, price, sl, sl),
                       ambiguous=True)
        if cham_tp:
            return out(WIN, exit=tp, exit_at=khi, r=_r(direc, price, sl, tp))
        if cham_sl:
            return out(LOSS, exit=sl, exit_at=khi, r=_r(direc, price, sl, sl))

    if closed_at:
        gia = _gia_cuoi(nen, closed_at)
        if gia is not None:
            return out(SUPERSEDED, exit=gia,
                       exit_at=closed_at.isoformat(timespec="seconds"),
                       r=_r(direc, price, sl, gia))

    if now >= han:
        gia = nen[-1]["close"] if nen else price
        return out(EXPIRED, exit=gia, exit_at=han.isoformat(timespec="seconds"),
                   r=_r(direc, price, sl, gia))

    return out(OPEN)


def _gia_cuoi(nen, moc):
    """Giá đóng của nến cuối cùng trước `moc`."""
    ms = moc.timestamp() * 1000
    truoc = [c for c in nen if c["ts"] <= ms]
    return truoc[-1]["close"] if truoc else (nen[0]["open"] if nen else None)


# ── ĐÓNG SỚM ──────────────────────────────────────────────────────────────────
def closing_marks(entries):
    """Mốc mà mỗi tín hiệu bị tín hiệu sau đóng sớm. Trả {id: datetime}.

    Tín hiệu sau trên CÙNG MỘT MÃ có hướng KHÁC thì đóng cái đang mở – kể cả đổi
    sang NEUTRAL, vì NEUTRAL nghĩa là đứng ngoài, tức là thoát.

    Cùng hướng thì KHÔNG đóng: SHORT BIAS → STRONG SHORT là quan điểm mạnh lên chứ
    không phải đảo chiều. Hai tín hiệu chạy song song, mỗi cái tự chịu trách nhiệm
    cho mức giá của chính nó.
    """
    theo_ma = {}
    for e in entries:
        theo_ma.setdefault(e.get("symbol"), []).append(e)

    marks = {}
    for ds in theo_ma.values():
        ds = sorted(ds, key=lambda e: e.get("at") or "")
        for i, e in enumerate(ds):
            huong = direction(e.get("to"))
            if huong == NEUTRAL:
                continue
            for sau in ds[i + 1:]:
                if direction(sau.get("to")) != huong:
                    moc = _dt(sau.get("at"))
                    if moc:
                        marks[signal_id(e)] = moc
                    break
    return marks


# ── CHẤM CẢ NHẬT KÝ ───────────────────────────────────────────────────────────
def evaluate(entries, *, now=None, fetch=fetch_klines_range, existing=None,
             log=lambda *_: None):
    """Chấm mọi tín hiệu chưa ngã ngũ. Trả danh sách kết quả (kể cả `open`).

    `fetch` tiêm được để test không cần mạng.
    """
    now      = now or now_vn()
    existing = existing if existing is not None else read()
    marks    = closing_marks(entries)
    ket_qua  = []

    for e in entries:
        sid = signal_id(e)
        if sid in existing:
            continue

        at = _dt(e.get("at"))
        if at is None or direction(e.get("to")) == NEUTRAL or not (e.get("risk") or {}).get("sl"):
            # Không cần nến – khỏi tốn một request cho tín hiệu chắc chắn skipped.
            ket_qua.append(evaluate_one(e, [], now=now))
            continue

        het = min(at + timedelta(days=SIGNAL_EXPIRY_DAYS), now)
        try:
            nen = fetch(e["symbol"], OUTCOME_PROBE_TF, at, het)
        except Exception as ex:
            log(f"  {sid}: lấy nến lỗi {type(ex).__name__}: {ex}")
            continue

        ket_qua.append(evaluate_one(e, nen, now=now, closed_at=marks.get(sid)))

    return ket_qua


# ── LƯU / ĐỌC ─────────────────────────────────────────────────────────────────
def save(results, path=None):
    """Chỉ ghi kết quả ĐÃ NGÃ NGŨ. `open` tính lại mỗi lần đọc."""
    path  = path or OUTCOME_FILE
    xong  = [r for r in results if r.get("status") in FINAL]
    if not xong:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in xong:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return xong


def read(path=None):
    """Trả {id: kết quả}. Dòng hỏng bị bỏ qua chứ không ném lỗi."""
    path = path or OUTCOME_FILE
    if not path.exists():
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("id"):
                out[r["id"]] = r      # dòng sau đè dòng trước
    return out


# ── THỐNG KÊ ──────────────────────────────────────────────────────────────────
def _tinh(rs, min_n):
    dem = {k: 0 for k in (WIN, LOSS, EXPIRED, SUPERSEDED, SKIPPED, OPEN)}
    for r in rs:
        dem[r.get("status", OPEN)] = dem.get(r.get("status", OPEN), 0) + 1

    # Mẫu số của tỷ lệ thắng gồm cả `expired`: tín hiệu không đi đâu cả vẫn là tín
    # hiệu sai. Vứt expired đi là cách phổ biến nhất khiến loại thống kê này nói dối.
    n_ty_le = dem[WIN] + dem[LOSS] + dem[EXPIRED]
    # R trung bình tính trên nhiều mẫu hơn, vì `superseded` có lãi/lỗ thật ông chịu.
    co_r    = [r["r"] for r in rs
               if r.get("status") in (WIN, LOSS, EXPIRED, SUPERSEDED)
               and r.get("r") is not None]

    return {
        "counts":     dem,
        "n":          n_ty_le,
        "min_n":      min_n,
        # None khi chưa đủ mẫu. Giao diện KHÔNG được tự tính lấy từ counts –
        # ẩn tỷ lệ lúc mẫu còn bé là một luật, không phải gợi ý.
        "win_rate":   round(dem[WIN] / n_ty_le * 100, 1) if n_ty_le >= min_n else None,
        "n_r":        len(co_r),
        "avg_r":      round(sum(co_r) / len(co_r), 3) if co_r else None,
        "total_r":    round(sum(co_r), 3) if co_r else None,
        "ambiguous":  sum(1 for r in rs if r.get("ambiguous")),
    }


def stats(results, min_n=STATS_MIN_N):
    """Thống kê tổng + theo mã. Mọi tỷ lệ đều đi kèm số mẫu đẻ ra nó."""
    theo_ma = {}
    for r in results:
        theo_ma.setdefault(r.get("symbol"), []).append(r)

    return {
        "expiry_days": SIGNAL_EXPIRY_DAYS,
        "rr":          ATR_MULT_TP / ATR_MULT_SL,
        "overall":     _tinh(results, min_n),
        "by_symbol":   {sym: _tinh(rs, min_n) for sym, rs in sorted(theo_ma.items())},
    }


def load_all(entries, path=None, min_n=STATS_MIN_N):
    """Ghép nhật ký với kết quả đã lưu. Tín hiệu chưa có kết quả tính là `open`.

    Dùng cho API – KHÔNG gọi mạng, nên trang chủ mở nhanh và không phụ thuộc Binance.
    """
    da_co = read(path)
    rs = [da_co.get(signal_id(e), {"id": signal_id(e), "symbol": e.get("symbol"),
                                   "at": e.get("at"), "status": OPEN})
          for e in entries]
    return rs, stats(rs, min_n)
