# Feed tín hiệu lên web + nhật ký thời điểm bắn

**Trạng thái: BRAINSTORM. Chưa chốt, chưa code.** Cuối file có 6 câu hỏi cần quyết trước.

## Muốn gì

Tín hiệu mua/bán hiện chỉ chảy xuống Telegram rồi trôi mất. Muốn nó **cũng lên web**,
đúng nội dung như trên Telegram, kèm **nhật ký bắn lúc mấy giờ** để xem lại.

## Đang có gì rồi

`service/watch.py::scan_symbols()` đã trả về danh sách alert — đây là mảnh ghép quan
trọng nhất và nó **đã đúng sẵn**:

```python
{"kind": "signal" | "fetch_failure",
 "name": "BTC", "symbol": "BTCUSDT",
 "text": <đúng chuỗi gửi Telegram>,
 "snapshot": {...}}          # 4 khung, confluence, levels, risk
```

Hàm này **trả alert chứ không tự gửi** — cố ý từ đợt refactor, để monitor và server dùng
chung một logic. Nhờ vậy việc thêm feed **không phải đụng vào engine hay logic debounce**,
chỉ cắm thêm một người tiêu thụ mới vào chỗ alert đi ra.

`scheduler.scan_once()` hiện làm hai việc với alert: gửi Telegram, và đẩy SSE sự kiện
`signal` — nhưng SSE chỉ mang `{name, kind}`, không mang nội dung.

**Chưa có gì lưu lại.** `data/last_signals.json` chỉ giữ trạng thái debounce hiện tại
(verdict đang giữ + bộ đếm), không phải lịch sử. Bắn xong là mất.

## Hình dung

```
scan_symbols() → alerts
                   ├─→ Telegram        (đã có)
                   ├─→ SSE "signal"    (đã có, cần bơm thêm nội dung)
                   └─→ NHẬT KÝ          ← mới
                          ↓
                   data/signals.jsonl
                          ↓
              GET /api/signals/history
                          ↓
              Feed trên web + đẩy realtime
```

## Ghi cái gì cho mỗi tín hiệu

Đây là chỗ quyết định giá trị của cả tính năng. Ghi thiếu là sau này muốn xem lại không có.

| Trường | Vì sao cần |
|---|---|
| `at` | Thời điểm bắn |
| `first_seen_at` | **Debounce giữ 2 lượt quét mới báo** — nên lúc bắn đã trễ ~15 phút so với lúc thị trường thật sự đổi. Ghi cả hai mới biết độ trễ thật |
| `symbol` `name` | BTC / ETH / XAU |
| `from` → `to` | Confluence cũ → mới. Bản thân "đổi từ đâu sang đâu" mới là tín hiệu |
| `price` | **Giá lúc bắn.** Không có trường này thì sau này không cách nào chấm điểm tín hiệu đúng hay sai |
| `timeframes` | Score + verdict từng khung 1W/1D/4H/1H |
| `levels` `risk` | Entry / SL / TP đề xuất lúc đó |
| `text` | Đúng chuỗi đã gửi Telegram — web và Telegram không được lệch nhau |
| `telegram_ok` | Gửi Telegram có thành công không. Có trường này thì web thành nguồn sự thật kể cả khi Telegram hỏng |

`price` và `first_seen_at` là hai trường dễ bỏ sót nhất mà lại đắt nhất nếu thiếu — thêm
sau thì lịch sử cũ vĩnh viễn không có.

## Lưu ở đâu

| | Ưu | Nhược |
|---|---|---|
| **JSONL** `data/signals.jsonl` | Nối thêm một dòng, không đọc lại file cũ. Không thêm phụ thuộc. Mở bằng notepad đọc được | Lọc/đếm phải quét cả file |
| SQLite `data/signals.db` | Lọc theo mã, theo ngày, dựng biểu đồ. Chịu được đọc/ghi đồng thời | Thêm một thứ để hỏng. Sửa tay khó hơn |
| JSON array | — | Mỗi lần ghi phải đọc + ghi lại cả file. Loại |

**Nghiêng về JSONL.** Ước lượng thật: 3 mã, confluence đổi vài lần mỗi ngày → vài chục
dòng/ngày → dưới 1MB/năm. Chưa tới ngưỡng cần database. Chuyển sang SQLite sau vẫn được,
JSONL đọc một lượt là nạp xong.

## Hiện lên web thế nào

- **Feed trên trang chủ**, dưới 3 thẻ giá: 10 tín hiệu gần nhất, mỗi dòng một tag màu
  (STRONG LONG / BIAS / NEUTRAL), thời gian, giá lúc bắn, khoảng cách "2 giờ trước"
- **Trang `/signals`** cho toàn bộ lịch sử, lọc theo mã
- **Realtime**: mở rộng sự kiện SSE `signal` sẵn có để mang cả entry → tín hiệu mới chèn
  lên đầu feed kèm nháy sáng, không cần reload
- `GET /api/signals/history?limit=&symbol=` — qua cửa gác như mọi route khác

## Chỗ cắm vào cho đúng tầng

Ghi nhật ký phải nằm ở **`service/`**, không phải `server/`. Vì `apps/monitor.py` cũng
quét — để ở `server/` thì chạy monitor tay sẽ không ghi gì, lịch sử thủng lỗ chỗ mà không
ai biết. `engine/` thì tuyệt đối không đụng: nó không được biết file hay thời gian thực.

Đề xuất: `service/journal.py` — `append(alert, ...)` và `read(limit, symbol)`.

## Rủi ro đã thấy

**Không có lịch sử cũ.** Feed bắt đầu từ số không, không backfill được vì dữ liệu chưa
từng được lưu. Vài ngày đầu trang sẽ trống.

**Múi giờ.** Code hiện dùng `datetime.now()` — giờ địa phương, không kèm timezone. Khách
xem từ nước khác sẽ đọc sai. Sửa cho đúng là đụng vào cách ghi thời gian ở nhiều chỗ.

**Chạy hai tiến trình cùng lúc thì nhật ký đan xen.** Đã có cảnh báo không chạy
`apps.monitor` lúc server chạy, nhưng nhật ký làm hậu quả rõ hơn: lịch sử lẫn lộn.

**Khách đã duyệt sẽ thấy toàn bộ lịch sử tín hiệu**, không chỉ trạng thái hiện tại. Đó
là lượng thông tin khác hẳn — cần quyết có muốn không.

---

## Cần quyết trước khi viết spec

1. **Ghi cái gì?** Chỉ alert (đúng thứ Telegram nhận, hiếm và có nghĩa), hay mọi lượt
   quét (dày, nhiễu, nhưng vẽ được biểu đồ score theo thời gian)?
2. **JSONL hay SQLite** ngay từ đầu?
3. **Khách đã duyệt có được xem lịch sử không**, hay chỉ chủ nhà?
4. **Múi giờ**: sửa cho đúng chuẩn UTC ngay bây giờ, hay ghi giờ VN rồi dán nhãn?
5. **Feed nằm đâu**: nhét vào trang chủ, trang `/signals` riêng, hay cả hai?
6. **Có ghi cả `fetch_failure` vào nhật ký không**, hay chỉ tín hiệu mua/bán thật?
