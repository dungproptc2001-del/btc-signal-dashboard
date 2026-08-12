# Spec: log tín hiệu mua/bán lên web

Thực thi [plan](../plan/signal-feed-plan.md). Nhánh `feat/signal-dashboard`.

**Đã thực thi xong 12/08/2026.** 259 test xanh, 0 vi phạm ranh giới tầng, đã chạy thật
trên server và ghi được bản ghi đầu tiên.

Hai chỗ từng nghi, đã kiểm và đều ổn: không có vòng import `watch → journal`; và
`_run(lambda ...)` trong `scan_once()` chạy đúng — giờ có test gọi thật một lượt quét
giả lập canh nó, không dựa vào suy luận.

Một khoảng hở lúc chuyển đổi: mã nào đang dở một chu kỳ chờ lúc nâng cấp thì state cũ
chưa có `pending_since`, nên bản ghi đầu tiên của mã đó có `first_seen_at` bằng `at`.
Tự lành từ chu kỳ sau. Đã thấy thật với BTC ở lượt quét đầu.

---

## Sáu quyết định đã chốt

| | Chốt |
|---|---|
| Ghi cái gì | **Chỉ alert `kind == "signal"`** — đúng thứ Telegram nhận. Không ghi `fetch_failure` |
| Lưu ở đâu | **File JSON**, không database |
| Ai xem được | **Khách đã duyệt xem hết lịch sử**, như chủ nhà |
| Múi giờ | **UTC+7**, giờ Việt Nam, ghi kèm offset rõ ràng |
| Hiện ở đâu | **Trang chủ**, mục tên `signals` |
| Lỗi fetch | **Không ghi.** Chỉ mua/bán thật |

---

## `btcreport/service/journal.py` (mới)

Tầng `service` — **không** phải `server`. Vì `apps/monitor.py` cũng quét; để ở `server/`
thì chạy monitor tay sẽ không ghi gì, lịch sử thủng lỗ chỗ mà không ai biết.

```python
TZ_VN = timezone(timedelta(hours=7))

def append(alert, *, first_seen_at=None, telegram_ok=None, now=None) -> dict | None
def read(limit=None, symbol=None) -> list[dict]
```

`append()` trả `None` và **không ghi gì** nếu `alert["kind"] != "signal"`. Chốt chặn nằm
ở đây chứ không ở người gọi — sau này thêm loại alert mới sẽ không lỡ lọt vào log.

### Định dạng: JSONL (`data/signals.jsonl`)

Mỗi dòng một object JSON. Vẫn là JSON thuần, mở bằng notepad đọc được, **không phải
database**. Chọn JSONL thay vì một mảng JSON vì:

- Ghi = nối thêm một dòng. Mảng JSON thì mỗi lần bắn phải đọc cả file rồi ghi đè lại —
  file càng dài càng chậm, và kill giữa chừng là **mất sạch lịch sử**, không phải mất
  một dòng.
- Dòng hỏng chỉ mất đúng dòng đó, phần còn lại vẫn đọc được.

`read()` bỏ qua dòng hỏng thay vì ném lỗi — một dòng rác không được làm sập trang chủ.

### Một bản ghi

```json
{
  "at":            "2026-08-12T18:30:00+07:00",
  "first_seen_at": "2026-08-12T18:15:00+07:00",
  "symbol":        "BTCUSDT",
  "name":          "BTC",
  "from":          "SHORT BIAS",
  "to":            "STRONG LONG",
  "price":         64128.0,
  "timeframes":    [{"label": "1W", "verdict": "LONG", "score": 4}, ...],
  "levels":        {...},
  "risk":          {...},
  "text":          "<đúng chuỗi đã gửi Telegram>",
  "telegram_ok":   true
}
```

**`price`** — giá lúc bắn. Không có trường này thì sau này không cách nào chấm điểm tín
hiệu đúng hay sai. Thêm sau là lịch sử cũ vĩnh viễn không có.

**`first_seen_at`** — debounce giữ `CONFIRM_SCANS=2` lượt quét mới báo, nên lúc bắn đã
trễ ~15 phút so với lúc thị trường thật sự đổi. Ghi cả hai mới biết độ trễ thật.

---

## `btcreport/service/watch.py`

Thêm `pending_since` vào state debounce: đặt khi `pending_count` về 1 (bắt đầu một chuỗi
chờ mới), đọc ra lúc confirm để làm `first_seen_at`.

Alert thêm hai trường `prev` và `pending_since` — `journal` cần, mà bắt nó tự suy từ
`text` thì phải parse chuỗi, hỏng ngay khi đổi câu chữ.

**Không đổi logic debounce, không đổi ngưỡng, không đổi nội dung `text`.** Golden test
canh `text` byte-for-byte phải vẫn xanh.

---

## `btcreport/server/scheduler.py`

Trong `scan_once()`, sau khi gửi Telegram:

```python
ok = await _run(send_telegram, alert["text"])
entry = journal.append(alert, telegram_ok=bool(ok))
```

Ghi **sau** khi gửi để biết Telegram có thành công không. Telegram hỏng vẫn phải ghi —
đó chính là lúc web có giá trị nhất.

Sự kiện SSE `signal` mang thêm `entries` (các bản ghi vừa tạo) để feed chèn realtime.

`apps/monitor.py` cũng phải gọi `journal.append` — không thì chạy tay sẽ mất lịch sử.

---

## Web

| | |
|---|---|
| `GET /api/signals/history?limit=&symbol=` | Qua cửa gác như mọi route. Khách đã duyệt xem được |
| Trang chủ | Mục `signals` dưới 3 thẻ giá: 20 tín hiệu gần nhất |
| SSE | Tín hiệu mới chèn lên đầu feed kèm nháy sáng, không reload |

Mỗi dòng feed: giờ VN · mã · `từ → sang` kèm tag màu · giá lúc bắn · "2 giờ trước".
Bấm vào giãn ra xem `text` đầy đủ — đúng chữ đã nhận trên Telegram.

---

## Test (`tests/test_journal.py`)

- `fetch_failure` **không** được ghi vào log
- `append` rồi `read` ra đúng bản ghi, đủ `price` và `first_seen_at`
- Thời gian có offset `+07:00`
- Dòng hỏng giữa file không làm `read()` ném lỗi
- `read(limit=)` trả mới nhất trước
- `read(symbol=)` lọc đúng
- Telegram hỏng vẫn ghi, `telegram_ok=False`
- `test_watch`: `pending_since` đặt đúng lúc bắt đầu chờ, không bị reset khi đang chờ
- Golden `text` không đổi

Test ghi vào `tmp_path`, không đụng `data/signals.jsonl` thật.
