# Kiến trúc

Sơ đồ trực quan: [structure.html](structure.html) — mở bằng browser.

## Ý tưởng một câu

Engine nhận nến, trả về **một context dict thuần Python**. Mọi thứ phía sau —
HTML, tin Telegram, dashboard web — chỉ là các cách trình bày khác nhau của cùng
cái dict đó.

```
Binance  →  sources/  →  engine/  →  context dict  ┬→  web/     →  HTML
                                                   ├→  notify/  →  Telegram
                                                   └→  server/  →  dashboard + API
```

Trước refactor, ba việc này quấn vào nhau trong một hàm 639 dòng: cùng chỗ vừa gọi
API, vừa tính RSI, vừa nối chuỗi `<div>`. Đổi màu một cái nút phải mở file 1142 dòng
và đếm dấu `{{`.

Nhờ ranh giới đó mà khi thêm web server, **bốn tầng cũ không phải sửa một dòng nào** —
chỉ thêm người gọi mới.

---

## Sáu tầng

| Tầng | Thư mục | Được phép | Cấm |
|---|---|---|---|
| **Nguồn** | `btcreport/sources/` | Gọi mạng, retry, parse JSON | Tính toán chỉ báo |
| **Engine** | `btcreport/engine/` | Tính toán thuần | `import requests`, chuỗi HTML, mã màu, emoji |
| **Trình bày** | `btcreport/web/`, `btcreport/notify/` | Định dạng, tô màu, gắn icon | Gọi indicator, so sánh ngưỡng |
| **Orchestration** | `btcreport/service/` | Ghép nguồn + engine thành một việc hoàn chỉnh | Gửi thông báo, dựng HTML |
| **Server** | `btcreport/server/` | HTTP, phiên, lịch chạy nền, bot | Tính toán tín hiệu |
| **Ứng dụng** | `apps/` | Ghép tất cả, xử lý vòng đời process | Chứa logic nghiệp vụ |

Quy tắc phụ thuộc: mũi tên chỉ đi **xuống**. `engine/` không biết `web/` hay `server/`
tồn tại. `sources/` không biết `engine/` tồn tại. Chỉ `apps/` nhìn thấy tất cả.

### Vì sao engine bị cấm mã màu

Trước đây `generate_signal()` trả về `("LONG", "#00c853", "MUA / GIỮ", 5, [...])` —
mã hex nằm giữa logic giao dịch. Muốn đổi tông xanh phải sửa file tính tín hiệu.
Giờ engine chỉ trả `"LONG"`, còn `web/filters.py` map `LONG → class="v-long"` và
`styles.css` quyết định `v-long` màu gì.

Ranh giới này có test canh, không phải quy ước suông:

```python
# tests/test_context.py
def test_context_khong_chua_html_hay_ma_mau(ctx):
    blob = json.dumps(ctx, default=str)
    for banned in ("<div", "<span", "#00c853", "#d50000", "#ffa000"):
        assert banned not in blob
```

---

## Từng module

### `btcreport/config.py`
Đường dẫn, secret, mọi hằng số. Đọc `.env` bằng `os.environ.setdefault` nên biến môi
trường thật luôn thắng file. Tự tạo `data/` và `output/` lúc import.

Module khác **không được** tự định nghĩa lại hằng số — `MAX_SCORE` chỉ tồn tại ở đây.

### `btcreport/sources/`

| File | Việc |
|---|---|
| `http.py` | `get_json()` — cửa duy nhất ra internet. Retry 4 lần, backoff `2^n + jitter`, tôn trọng header `Retry-After`. |
| `binance.py` | Nến và ticker. `parse_klines()` đổi mảng thô thành dict có tên. |
| `feargreed.py` | Chỉ số tâm lý. Nuốt lỗi, trả `(None, "N/A")`. |

`http.py` phân biệt hai loại lỗi: **429 và 5xx thì retry** (tạm thời), **4xx khác
raise ngay** (sai symbol thì thử lại 4 lần cũng vô ích, chỉ tổ chậm).

`feargreed` nuốt lỗi còn `binance` thì không — vì thiếu chỉ số tâm lý báo cáo vẫn
dùng được, thiếu nến thì không.

### `btcreport/engine/`

| File | Việc |
|---|---|
| `indicators.py` | SMA, EMA, RSI, MACD, Bollinger, ATR. Series trả về luôn cùng độ dài input, phần chưa đủ dữ liệu điền `None`. |
| `signals.py` | `generate_signal()` chấm điểm ±7, `confluence()` gộp 4 khung. |
| `levels.py` | Pivot hỗ trợ/kháng cự và SL/TP theo ATR. |
| `analysis.py` | `build_context()` — gom tất cả thành context dict. |

`build_context()` **không fetch gì cả**. Nó nhận nến đã có sẵn. Nhờ vậy test nạp
fixtures vào là chạy được, không cần mạng, không phụ thuộc giá thị trường lúc chạy.

`confluence()` là **bản duy nhất**. Trước refactor logic này bị copy ba chỗ:
trong `build_html`, trong `main()`, và trong `signal_monitor._confluence()` — sửa
một chỗ quên hai chỗ kia là chuyện sớm muộn.

`generate_signal()` đổi chữ ký: cũ nhận `(candles, rsi_vals, macd_val, sig_full)`,
bắt mỗi caller tự tính trước và truyền đúng thứ tự. Giờ chỉ nhận `candles`.

### `btcreport/notify/`

| File | Việc |
|---|---|
| `telegram.py` | Gửi tin, retry 3 lần. Chưa cấu hình token thì trả `False`, không raise. |
| `messages.py` | Soạn text. Emoji, xuống dòng, canh cột nằm ở đây. |

`messages.py` chính là "frontend của kênh Telegram" — vai trò y hệt `web/` nhưng cho
một môi trường hiển thị khác.

### `btcreport/web/`

| File | Việc |
|---|---|
| `renderer.py` | `render_report(ctx) -> str`. Dựng Jinja env, inline CSS/JS, làm tròn series chart. |
| `filters.py` | Filter định dạng: `usd`, `pct`, `verdict_class`, `rsi_class`… Bảng màu nằm ở đây. |
| `templates/report.html` | Markup. |
| `static/styles.css` | Kiểu dáng. |
| `static/charts.js` | Cấu hình Chart.js. Đọc dữ liệu từ `window.REPORT_DATA`. |

Ba điểm đáng chú ý:

**`StrictUndefined`.** Template dùng biến không có trong context là nổ ngay lúc render,
không âm thầm in ra chuỗi rỗng. Thiếu dữ liệu thì phải biết sớm.

**`autoescape=True`.** Mọi chuỗi từ context được escape. An toàn hơn f-string cũ, và
đúng đắn hơn — `reasons` chứa ký tự `&`, `<` là được xử lý tự động.

**Vẫn xuất một file tự chứa.** `renderer.py` đọc `styles.css` + `charts.js` rồi nhét
vào lúc render, nên `output/btc_report.html` double-click là mở được. Tách file chỉ để
lập trình cho dễ, không đổi cách người dùng dùng.

Dữ liệu chart đi qua **một** biến `window.REPORT_DATA` thay cho 21 placeholder rời
trước đây (`{label_str}`, `{close_str}`, `{ma7_str}`…). Series được làm tròn 2 chữ số
trước khi serialize — biểu đồ không đổi một pixel mà file nhỏ đi đáng kể.

### `btcreport/service/`

Tầng orchestration, sinh ra khi thêm web server: server và `apps/monitor.py` cần
**cùng một** logic quét, không được copy.

| File | Việc |
|---|---|
| `report.py` | `build_report()` — fetch → `build_context` → render. Trả `(html, message, ctx)`. |
| `watch.py` | `scan_symbols()` — quét 3 mã, chạy debounce, trả **danh sách alert cần gửi**. |

Điểm mấu chốt: `scan_symbols()` **không gửi Telegram**. Nó chỉ quyết định *gửi gì*,
người gọi tự lo *gửi thế nào* — monitor thì gửi Telegram, server thì vừa gửi Telegram
vừa đẩy SSE. Nhờ tách vậy mà test được toàn bộ debounce không cần mock Telegram, và
có hẳn một test nổ nếu ai đó lỡ gọi `send_telegram` từ trong đó.

### `btcreport/server/`

| File | Việc |
|---|---|
| `app.py` | FastAPI: route, middleware gác cửa, SSE, luồng xin quyền. |
| `state.py` | Cache RAM + kênh phát SSE. Mở trang không kích hoạt fetch. |
| `scheduler.py` | Ba nhịp nền: giá 30 giây, quét 15 phút, báo cáo 4 tiếng. |
| `access.py` | Phiên, yêu cầu truy cập, duyệt/từ chối/thu hồi, chống spam. |
| `bot.py` | Long-poll Telegram: nút Duyệt/Từ chối + lệnh điều khiển. |
| `keepalive.py` | Giữ máy không ngủ trong lúc server chạy. |
| `tunnel.py` | Mở server ra internet. `TUNNEL_PROVIDER=tailscale` (URL cố định) hoặc `cloudflare` (URL đổi mỗi lần chạy). |

### `apps/`

| File | Việc |
|---|---|
| `server.py` | Bật keepalive → tunnel → scheduler → bot → uvicorn. Tắt thì ngược lại. |
| `report.py` | Gọi `service/report`, ghi file, Telegram, mở browser. |
| `monitor.py` | Vòng lặp 15 phút gọi `service/watch`, gửi alert. |

---

## Luồng dữ liệu

### Report (4 tiếng/lần)

```
get_thu_range()                    xác định khoảng thứ 5 → thứ 5
  ↓
fetch_klines × 4 + range tuần      1W(26) 1D(120) 4H(100) 1H(100)
fetch_ticker + fetch_fear_greed
  ↓
build_context(...)                 → context dict
  ↓
  ├─ render_report(ctx)            → output/btc_report.html
  └─ format_report_message(ctx)    → send_telegram()
```

### Monitor (15 phút/lần)

```
với mỗi mã trong SYMBOLS:
  get_snapshot(symbol)             fetch 4 khung + ticker
    ↓ lỗi → consec_fails += 1; chạm 4 lần thì cảnh báo; GIỮ state cũ
    ↓ ok
  confluence hiện tại == state đã confirm?
    ↓ có   → xoá pending, xong
    ↓ khác → pending_count += 1
             chưa đủ CONFIRM_SCANS → chỉ ghi pending, không báo
             đủ rồi                → send_telegram(alert), confirm state mới
  ↓
save_state()                       ghi atomic qua os.replace
```

### Server (một process, ba nhịp)

```
apps/server.py
  ↓
keepalive.hold()            giữ máy thức — không thì 5 phút nữa web sập
tunnel.start()              → https://ten-may.tailXXXX.ts.net   (cố định)
scheduler.start()           3 task asyncio, mọi call chặn đẩy qua threadpool
bot.poll_loop()             long-poll getUpdates
uvicorn.serve()
  ↓
     30 giây → fetch_ticker × 3      → STATE.publish("price")
     15 phút → service.watch.scan    → Telegram + STATE.publish("signal")
     4 tiếng → service.report.build  → file + Telegram + STATE.publish("report")
```

Trình duyệt nối `/events` (SSE) và nhận đẩy, không polling. Mất kết nối thì tự nối
lại sau 5 giây.

---

## Quyền truy cập

Web công khai ra internet, nên đây là ranh giới an ninh thật, không phải trang trí.

```
Khách mở URL
  ↓ không có cookie hợp lệ
Trang xin quyền: TÊN + LỜI NHẮN (≥ 10 ký tự)
  ↓ POST /access/request        ← chặn spam TẠI ĐÂY, trước khi bot nhắn
Telegram cho chủ nhà + 2 nút [Duyệt] [Từ chối]
  ↓ khách poll /access/status mỗi 3 giây
Chủ nhà bấm nút → callback_query
  ↓ access.is_owner(chat_id)?   ← chốt chặn
Duyệt → cookie 7 ngày, trang khách tự vào dashboard
```

### Bốn chốt chặn

**`is_owner(chat_id)` gác mọi hành động đặc quyền.** Bot công khai, ai cũng nhắn
được. Không kiểm thì người lạ chỉ cần gửi đúng callback data là tự duyệt cho chính
mình. Duyệt, từ chối, thu hồi, `/stop` — tất cả đi qua đúng một hàm này.

**Chống spam chặn trước khi gửi Telegram.** 3 yêu cầu / IP / giờ, 20 / giờ toàn cục.
Nếu chặn sau khi gửi thì bất kỳ ai cũng làm ngập điện thoại chủ nhà. Có test canh
đúng thứ tự này.

**Nhận diện chủ nhà có hai lớp.** Tunnel nào cũng proxy vào server, nên request từ
internet có thể mang danh nghĩa loopback — chỉ nhìn địa chỉ thì **mọi khách trên
internet đều thành chủ nhà**. Nên `_is_owner_request()` loại bỏ ngay mọi request
mang header proxy (`cf-connecting-ip`, `x-forwarded-for`, …) *rồi* mới xét loopback.

Đo thật từ ngoài internet (12/08/2026), không đọc doc rồi tin:

| Provider | `client.host` thấy được | Header proxy | Lớp nào đỡ |
|---|---|---|---|
| Tailscale Funnel | `100.x.y.z` — interface tailscale | `x-forwarded-for` | **cả hai** |
| Cloudflare tunnel | `127.0.0.1` | `cf-connecting-ip` | chỉ lớp header |

Cloudflare là trường hợp nguy hiểm hơn: mất lớp header là thủng sạch. Lớp header fail
an toàn đúng chiều — khách tự khai `x-forwarded-for` chỉ tự loại mình khỏi quyền, không
bao giờ được thêm quyền.

Funnel còn bơm `tailscale-user-login` / `-name` / `-profile-pic` vào **mọi** request kể
cả từ người lạ. Đó không phải danh tính đã xác thực; code không đọc chúng và có test
canh để không ai lỡ dùng chúng cấp quyền.

**Đổi provider tunnel là phải đo lại bảng trên**, đừng suy từ provider cũ.

**`STATE.public()` không được chứa secret.** Có test dò `OWNER_KEY`, bot token và
chuỗi `token` trong toàn bộ dữ liệu trả ra web.

---

## Ba quyết định thiết kế

### Debounce hai lần quét

Score dao động quanh ngưỡng ±3 ở khung 1H rất hay lật qua lật lại. Không có debounce
thì mỗi lần lật là một tin Telegram, đọc vài hôm là bắt đầu bỏ qua hết — cảnh báo mất
hết giá trị. Confluence mới phải giữ được **hai lần quét liên tiếp** (30 phút) mới báo.

Có test mô phỏng cú lật giả `NEUTRAL → LONG → NEUTRAL`: kết quả 0 alert.

### Fetch lỗi không phải là "không đổi"

Bản cũ nuốt exception rồi trả verdict rỗng, monitor hiểu nhầm thành "signal không đổi"
và im lặng. Mạng chập chờn cả tiếng mà vẫn tưởng thị trường yên ắng.

Giờ `get_snapshot()` trả `(ok, snapshot)`. `ok=False` thì đếm `consec_fails` và giữ
nguyên state cũ; chạm 4 lần liên tiếp (~1 tiếng) thì bắn cảnh báo riêng.

### PID file thay vì kill theo tên

`taskkill /im pythonw.exe` giết mọi tiến trình Python trên máy. Server và monitor ghi
PID vào `data/*.pid` (dọn bằng `atexit` + signal handler), script stop đọc file đó và
kill đúng một tiến trình. Mất pid file thì fallback sang quét command line.

Lưu ý khi tự viết lệnh dò tiến trình: câu lệnh PowerShell chứa chuỗi tìm kiếm sẽ
**tự khớp chính nó**. Phải lọc theo tên tiến trình (`python*`) và loại trừ `$PID`,
không thì tưởng có process ma đang hồi sinh liên tục.

### Giữ máy thức bằng API thay vì sửa power plan

Máy dùng S0 Modern Standby, ngủ sau 5 phút. `SetThreadExecutionState` chỉ giữ thức
đúng lúc server chạy, không cần admin, tắt server là về nếp cũ ngay. So với
`powercfg /change standby-timeout-ac 0`: không đụng cấu hình máy, gỡ project đi không
để lại dấu vết.

---

## Bộ test

203 test chạy trên fixtures đóng băng — không mạng, không phụ thuộc giá.

| File | Kiểm |
|---|---|
| `test_indicators.py` | Công thức đúng trên chuỗi tính tay + khớp golden trên dữ liệu thật |
| `test_signals.py` | Từng thành phần điểm, ranh giới verdict, 9 nhánh confluence |
| `test_levels.py` | Pivot, hướng SL/TP, NEUTRAL không đề xuất entry |
| `test_context.py` | Context khớp golden + **không rò rỉ HTML/màu** |
| `test_messages.py` | Text Telegram khớp golden **byte-for-byte** |
| `test_render.py` | Render đủ thành phần, không sót cú pháp Jinja |
| `test_watch.py` | Debounce (lật giả → 0 alert), đếm lỗi fetch, và **scan không tự gửi Telegram** |
| `test_access.py` | Hết hạn, thu hồi, chống spam, và **chat_id lạ không duyệt được** |
| `test_api.py` | 401 khi chưa có quyền, không rò rỉ secret, **không giả mạo được chủ nhà** |

`tests/fixtures/` giữ phản hồi Binance thật đã đóng băng. `tests/golden/` giữ kết quả
mốc. Sinh lại bằng `capture_fixtures.py` và `capture_golden.py` — chỉ chạy khi cố ý
thay đổi model, xem lý do trong [README](../README.md#test).
