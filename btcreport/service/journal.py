"""Nhật ký tín hiệu mua/bán — đúng những gì đã đẩy xuống Telegram.

Ở tầng `service` chứ không phải `server`, vì `apps/monitor.py` cũng quét. Để ở `server/`
thì chạy monitor tay sẽ không ghi gì, lịch sử thủng lỗ chỗ mà không ai biết.

Định dạng JSONL: mỗi dòng một object JSON. Vẫn là JSON thuần, mở bằng notepad đọc được,
không phải database. Chọn JSONL thay vì một mảng JSON vì:

  - Ghi = nối thêm một dòng. Mảng JSON thì mỗi lần bắn phải đọc cả file rồi ghi đè lại;
    kill giữa chừng là mất SẠCH lịch sử chứ không phải mất một dòng.
  - Dòng hỏng chỉ mất đúng dòng đó, phần còn lại vẫn đọc được.
"""
import json
from datetime import datetime, timedelta, timezone

from ..config import DATA_DIR

# Giờ Việt Nam, ghi kèm offset rõ ràng. Không dùng datetime.now() trần: khách xem từ
# múi giờ khác sẽ đọc sai mà không có gì báo cho họ biết.
TZ_VN = timezone(timedelta(hours=7))

JOURNAL_FILE = DATA_DIR / "signals.jsonl"


def now_vn():
    return datetime.now(TZ_VN)


def _iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


def signal_id(entry):
    """Khoá định danh một tín hiệu, để gắn kết quả chấm điểm vào.

    Suy được từ `(symbol, at)` nên bản ghi CŨ – ghi từ trước khi có trường `id` –
    vẫn khoá ra đúng cùng một giá trị. Không phải sửa file lịch sử, mà file lịch sử
    thì đã hứa là bất biến.

    Duy nhất vì một mã không thể bắn hai tín hiệu trong cùng một giây: debounce giữ
    tối thiểu CONFIRM_SCANS lượt quét mới cho báo lại.
    """
    return entry.get("id") or f'{entry.get("symbol")}@{entry.get("at")}'


def append(alert, *, telegram_ok=None, now=None, path=None):
    """Ghi một tín hiệu. Trả bản ghi, hoặc None nếu không phải tín hiệu mua/bán.

    Chốt lọc nằm ở ĐÂY chứ không ở người gọi: sau này thêm loại alert mới sẽ không
    lỡ lọt vào nhật ký chỉ vì ai đó quên kiểm ở đầu bên kia.
    """
    if alert.get("kind") != "signal":
        return None

    path = path or JOURNAL_FILE
    snap = alert.get("snapshot") or {}
    at   = now or now_vn()

    entry = {
        "id":            f'{alert.get("symbol")}@{_iso(at)}',
        "at":            _iso(at),
        "first_seen_at": alert.get("pending_since") or _iso(at),
        "symbol":        alert.get("symbol"),
        "name":          alert.get("name"),
        "from":          alert.get("prev") or "",
        "to":            (snap.get("confluence") or {}).get("verdict", ""),
        # Giá lúc bắn. Thiếu trường này thì sau không cách nào chấm điểm tín hiệu
        # đúng hay sai — và thêm sau thì lịch sử cũ vĩnh viễn không có.
        "price":         snap.get("price"),
        "timeframes":    [{k: tf.get(k) for k in ("label", "verdict", "score")}
                          for tf in snap.get("timeframes", [])],
        "levels":        snap.get("levels"),
        "risk":          snap.get("risk"),
        "text":          alert.get("text", ""),
        "telegram_ok":   telegram_ok,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read(limit=None, symbol=None, path=None):
    """Đọc nhật ký, mới nhất trước.

    Dòng hỏng bị bỏ qua chứ không ném lỗi — một dòng rác không được làm sập trang chủ.
    """
    path = path or JOURNAL_FILE
    if not path.exists():
        return []

    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if symbol:
        out = [e for e in out if e.get("symbol") == symbol or e.get("name") == symbol]

    out.reverse()
    return out[:limit] if limit else out


def count(path=None):
    return len(read(path=path))
