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
| `scheduler.py` | Bốn nhịp nền: giá 30 giây, quét 15 phút, chấm điểm 30 phút, báo cáo 4 tiếng — cộng nhịp **canh** 60 giây dựng lại nhịp nào chết âm thầm. |
| `access.py` | Phiên, yêu cầu truy cập, duyệt/từ chối/thu hồi, chống spam. |
| `bot.py` | Long-poll Telegram: nút Duyệt/Từ chối + lệnh điều khiển. |
| `keepalive.py` | Giữ máy không ngủ trong lúc server chạy. |
| `tunnel.py` | Mở server ra internet. `TUNNEL_PROVIDER=tailscale` (URL cố định) hoặc `cloudflare` (URL đổi mỗi lần chạy). |
| `power.py` | `/off` `/on`: nghỉ và bật lại mà **không** giết tiến trình. Khoá chống gọi chồng. |

Tầng `service/` có thêm:

| File | Việc |
|---|---|
| `journal.py` | Nhật ký tín hiệu mua/bán ra `data/signals.jsonl`. Ở `service/` chứ không `server/` vì `apps/monitor.py` cũng quét — để ở `server/` thì chạy monitor tay là lịch sử thủng lỗ chỗ mà không ai biết. |
| `outcome.py` | Chấm điểm tín hiệu: lấy nến 1H sau lúc bắn, xem chạm TP trước hay SL trước. Kết quả ra `data/outcomes.jsonl` **riêng**, để `signals.jsonl` giữ được lời hứa bất biến. |

### `apps/`

| File | Việc |
|---|---|
| `server.py` | Bật keepalive → tunnel → scheduler → bot → uvicorn. Tắt thì ngược lại. |
| `report.py` | Gọi `service/report`, ghi file, Telegram, mở browser. |
| `monitor.py` | Vòng lặp 15 phút gọi `service/watch`, gửi alert. |
| `score.py` | Chấm điểm tay. `--kho` để xem trước mà không ghi gì. |

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

### Server (một process, bốn nhịp + một người canh)

```
apps/server.py
  ↓
keepalive.hold()            giữ máy thức — không thì 5 phút nữa web sập
tunnel.start()              → https://ten-may.tailXXXX.ts.net   (cố định)
scheduler.start()           5 task asyncio, mọi call chặn đẩy qua threadpool
bot.poll_loop()             long-poll getUpdates
uvicorn.serve()
  ↓
     30 giây → fetch_ticker × 3      → STATE.publish("price")
     15 phút → service.watch.scan    → Telegram + STATE.publish("signal")
     30 phút → service.outcome.eval  → outcomes.jsonl + STATE.publish("outcome")
     4 tiếng → service.report.build  → file + Telegram + STATE.publish("report")
     60 giây → revive_dead()         → dựng lại nhịp chết + Telegram
```

Trình duyệt nối `/events` (SSE) và nhận đẩy, không polling. Mất kết nối thì tự nối
lại sau 5 giây.

---

## Chấm điểm tín hiệu

Hệ thống bắn tín hiệu từ đầu mà **chưa bao giờ tự chấm điểm**, nên mọi tham số đang
được chỉnh bằng cảm giác. Nhịp `score` đóng lỗ hổng đó. Chi tiết đầy đủ ở
[spec](spec/signal-outcome-spec.md); ba chỗ đáng nhớ:

**SL/TP theo hướng confluence, không theo khung 4H.** Trước đây `watch.py` gọi
`risk_levels(h4, tfs[2]["verdict"])` — mức tính theo verdict 4H trong khi tín hiệu bắn
ra là confluence cả 4 khung. Hai cái lệch nhau được, và đã lệch thật: 12/08/2026 PAXG
báo `LONG BIAS` lên Telegram trong khi 4H đang `NEUTRAL`, kết quả `sl = tp = None` —
tín hiệu có hướng mà không kèm mức nào. Chấm điểm mà không sửa chỗ này thì con số ra
được không biết đang đo gì.

**Nến mở trước lúc bắn bị loại.** Một tín hiệu không thể bị đóng bởi giá xảy ra trước
khi nó tồn tại. Nến chứa mốc `at` gần như luôn mở trước đó vài chục phút — không loại
là bịa ra thắng/thua từ quá khứ, mà bịa theo hướng nào thì tuỳ hôm đó thị trường đi
đâu, tức là một cái sai không có quy luật, nhìn con số không phát hiện được.

**`expired` nằm trong mẫu số của tỷ lệ thắng.** Vứt nó đi là cách phổ biến nhất khiến
loại thống kê này nói dối. Đi kèm: `win_rate` là `None` khi `n < 20`, và **server**
quyết định điều đó chứ không phải frontend — ẩn tỷ lệ lúc mẫu bé là một luật, để ở
giao diện thì nó sẽ lặng lẽ biến mất lần đầu ai đó sửa CSS.

---

## Biết khi hệ thống chết

Im lặng có hai nghĩa — *thị trường không có gì đáng báo* và *máy đã chết* — và trước đợt
này chúng trông y hệt nhau. Chi tiết ở [spec](spec/heartbeat-spec.md); bốn chỗ đáng nhớ:

**Nghịch lý quyết định cả kiến trúc:** thứ chạy trên máy không thể báo cho ông biết khi
máy tắt. Nên lớp trong máy (`/healthz` + băng cảnh báo + tự hồi sinh nhịp) chỉ lo trường
hợp *server còn sống mà đã hỏng*, còn `.github/workflows/watchdog.yml` — chạy trên hạ
tầng GitHub — mới là lớp lo trường hợp *máy tắt hẳn*. Hai lớp không thay được nhau.

**`/healthz` phải nói ba trạng thái, không phải hai.** `stale: true` nghĩa là uvicorn còn
trả 200 mà vòng quét đã chết. Đây là kiểu hỏng câm mà mọi dịch vụ ping thương mại đều báo
"khoẻ", vì chúng chỉ nhìn mã HTTP. `standby: true` (chủ nhà `/off`) thì ngược lại: phải
được coi là sống, không thì mỗi lần chủ động cho nghỉ là một báo động giả.

**Ngưỡng nằm ở server, giao diện chỉ đếm tiếp** — cùng luật với `win_rate`. Và giao diện
đếm bằng **số giây** (`scan_age_seconds`) chứ không parse `last_scan_at`: mốc đó ghi bằng
`datetime.now()`, giờ địa phương không kèm offset, nên `new Date()` ở trình duyệt múi giờ
khác lệch hàng tiếng — khách nước ngoài sẽ thấy băng đỏ vĩnh viễn dù hệ thống hoàn toàn
khoẻ. Có test tĩnh canh chuyện này (`test_js_khong_parse_moc_quet_...`).

**Báo động giả là thứ giết hệ thống cảnh báo**, nên phải hỏng 3 lượt liên tiếp mới mở
issue, và chỉ mở một cái cho tới khi sống lại. Bộ đếm không lưu ở đâu cả — kết luận của
các lượt chạy trước *chính là* trạng thái, hỏi qua API là ra. Không thêm file, không thêm
secret, không thêm thứ để hỏng.

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

## Bốn quyết định thiết kế

### `/off` không giết tiến trình

Bot Telegram sống *bên trong* server. Giết tiến trình là giết luôn tai nghe — không còn
ai đọc `/on` để bật lại. Nên `/off` chỉ đưa server vào nghỉ: đóng tunnel, dừng ba nhịp
nền, nhưng uvicorn vẫn chạy và bot vẫn poll.

Đường khác đã cân: tách bot ra một tiến trình canh gác riêng. Bỏ vì **Telegram chỉ cho
đúng một tiến trình gọi `getUpdates` trên một bot token** — hai cái cùng poll là `409
Conflict`, nên phải refactor để mọi lệnh đọc `STATE` đi qua HTTP nội bộ. Tốn gấp nhiều
lần mà chỉ mua thêm đúng một tình huống: tiến trình chết hẳn. Mà cách này không bao giờ
để nó chết hẳn.

Mặc định `/off` **không** nhả keep-alive, dù nghe ngược đời với chữ "tắt". Vì máy ngủ
thì *không gì* trên máy nhận được Telegram — không server, không canh gác. Một lệnh tắt
mà không chắc bật lại được thì tệ hơn là không có lệnh tắt, vì nó dụ người ta tin là
điều khiển được từ xa. Ai muốn đổi ngược: cờ `--sleep-on-off`.

Khoá `asyncio.Lock` dùng chung cho cả `standby()` và `wake()`, cộng chốt `if _tasks:
return` trong `scheduler.start()`. Không có hai lớp đó thì `/on` bấm ba lần đẻ ra ba bộ
scheduler, mỗi bộ một vòng quét riêng, ghi đè `last_signals.json` của nhau.

### Ba quyết định còn lại

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

340 test chạy trên fixtures đóng băng — không mạng, không phụ thuộc giá.

| File | Số | Kiểm |
|---|---|---|
| `test_api.py` | 61 | 401 khi chưa có quyền, không rò rỉ secret, **không giả mạo được chủ nhà** |
| `test_outcome.py` | 46 | Chạm TP/SL, nến trước lúc bắn bị loại, `expired` nằm trong mẫu số |
| `test_access.py` | 37 | Hết hạn, thu hồi, chống spam, và **chat_id lạ không duyệt được** |
| `test_signals.py` | 28 | Từng thành phần điểm, ranh giới verdict, 9 nhánh confluence |
| `test_watch.py` | 24 | Debounce (lật giả → 0 alert), đếm lỗi fetch, **scan không tự gửi Telegram** |
| `test_journal.py` | 21 | Ghi nối, lọc loại alert, khoá `id` suy được từ bản ghi cũ |
| `test_indicators.py` | 21 | Công thức đúng trên chuỗi tính tay + khớp golden trên dữ liệu thật |
| `test_context.py` | 19 | Context khớp golden + **không rò rỉ HTML/màu** |
| `test_heartbeat.py` | 19 | `stale` bật đúng lúc, `/off` không bị coi là chết, nhịp chết được dựng lại |
| `test_power.py` | 15 | `/off` `/on` không giết tiến trình, khoá chống gọi chồng |
| `test_bot.py` | 15 | Lệnh điều khiển qua cửa kiểm `is_owner` |
| `test_render.py` | 14 | Render đủ thành phần, không sót cú pháp Jinja |
| `test_levels.py` | 11 | Pivot, hướng SL/TP, NEUTRAL không đề xuất entry |
| `test_messages.py` | 9 | Text Telegram khớp golden **byte-for-byte** |

`tests/fixtures/` giữ phản hồi Binance thật đã đóng băng. `tests/golden/` giữ kết quả
mốc. Sinh lại bằng `capture_fixtures.py` và `capture_golden.py` — chỉ chạy khi cố ý
thay đổi model, xem lý do trong [README](../README.md#test).
