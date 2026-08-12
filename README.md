# btc-signal-dashboard

Web dashboard theo dõi tín hiệu BTC / ETH / vàng theo thời gian thực, tự host trên
máy cá nhân, cảnh báo qua Telegram. Người lạ muốn xem phải xin phép — duyệt bằng nút
bấm ngay trong Telegram, kiểu request access của Google Docs.

Một process lo cả ba việc:

| Nhịp | Chu kỳ | Việc |
|---|---|---|
| **Giá** | 30 giây | Đẩy giá 3 mã xuống trang qua SSE, không cần reload |
| **Tín hiệu** | 15 phút | Quét 4 khung, chỉ báo khi confluence **đổi** và giữ được 2 lần quét |
| **Báo cáo** | 4 tiếng | Dựng file HTML đầy đủ biểu đồ + gửi tin tổng hợp đa khung |

---

## Cài đặt

```powershell
cd E:\bitcoin-report
pip install -r requirements.txt          # requests, jinja2, fastapi, uvicorn
copy .env.example .env                   # rồi điền token vào .env
winget install tailscale.tailscale       # chỉ cần nếu muốn mở ra internet
tailscale up                             # đăng nhập, rồi bật Funnel (xem bên dưới)
```

`.env` cần hai giá trị (token lấy từ [@BotFather](https://t.me/BotFather),
chat id từ [@userinfobot](https://t.me/userinfobot)):

```ini
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Không có token thì mọi thứ vẫn chạy, chỉ là không gửi được Telegram — báo cáo HTML
vẫn sinh bình thường.

---

## Chạy web server

```powershell
python -m apps.server                    # mở cả ra internet qua Cloudflare Tunnel
python -m apps.server --no-tunnel        # chỉ chạy trong máy / LAN
python -m apps.server --allow-sleep      # không giữ máy thức
```

Mở `http://localhost:8000`. Từ chính máy này thì vào thẳng, không cần đăng nhập.
Bot sẽ nhắn URL công khai và link vào thẳng ngay khi server bật.

Ngoài desktop có sẵn 5 shortcut: **Bật · Tắt · Trạng thái · Dashboard · Link công khai**.

### Chạy tự động lúc đăng nhập

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_tasks.ps1
```

Dựng đúng **một** scheduled task `BTC Web Server` (chạy lại bao nhiêu lần cũng được),
đồng thời gỡ hai task đời trước — để cả hai cùng chạy sẽ tranh ghi
`data/last_signals.json` của nhau.

Task bật `AllowStartIfOnBatteries`. Đây không phải tuỳ chọn cho vui: `schtasks.exe`
mặc định **chỉ chạy khi cắm điện**, máy dùng pin là task fail lặng lẽ với mã
`0x800710E0`. Chỉ `Register-ScheduledTask` của PowerShell mới tắt được cờ đó.

### Bật, tắt, xem trạng thái

| Cách | Việc |
|---|---|
| `scripts\server_start.bat` | Bật |
| `scripts\server_stop.bat` | Tắt, nhả keep-alive, đóng tunnel |
| `scripts\server_status.bat` | Đang chạy không, sống bao lâu, có tạm dừng không |
| `scripts\server_link.bat` | Hỏi server link công khai đang sống, chép vào clipboard |
| Telegram `/status` `/url` `/scan` `/guests` `/revoke` | Điều khiển từ điện thoại |

### Ba mức tắt, đừng lẫn

| Lệnh | Dừng quét | Đóng link công khai | Máy được ngủ | Bot còn nghe |
|---|---|---|---|---|
| `/pause` `/resume` | ✓ | | | ✓ |
| `/off` `/on` | ✓ | ✓ | chỉ khi `--sleep-on-off` | **✓ luôn luôn** |
| `/stop` (hỏi lại bằng nút) | ✓ | ✓ | ✓ | ✗ |

`/off` **không giết tiến trình** — nó đóng tunnel và dừng ba nhịp nền, nhưng uvicorn vẫn
chạy và bot vẫn nghe. Đó là điểm mấu chốt: bot sống *bên trong* server, giết tiến trình
là giết luôn tai nghe, không còn ai đọc `/on` để bật lại.

Mặc định `/off` **không nhả keep-alive**. Máy vẫn thức, vẫn tốn điện — đổi lại một bảo
đảm cứng: **đã tắt được từ điện thoại thì luôn bật lại được từ điện thoại**. Nhả
keep-alive là máy ngủ, bot câm, ông gõ `/on` vào khoảng không rồi phải mò về mở laptop.
Muốn đánh đổi ngược lại thì chạy server với `--sleep-on-off`.

`/stop` là lệnh duy nhất không hoàn tác được từ xa, nên nó hỏi lại bằng nút bấm. Nút xác
nhận đi qua đúng cửa kiểm `is_owner` như nút duyệt khách — không thì người lạ chỉ cần
gửi đúng callback data là tắt được server của ông.

Với Tailscale, link công khai **giữ nguyên** qua chu kỳ `/off` → `/on`, khách đã duyệt
không phải xin lại. Với `TUNNEL_PROVIDER=cloudflare` thì URL đổi và bot sẽ cảnh báo ngay
trong tin nhắn `/on`.

> `schtasks /end` **không** đủ để dừng server — nó chỉ giết `cmd.exe` bọc ngoài,
> tiến trình Python vẫn sống tiếp thành orphan. Dùng `server_stop.bat`, nó đọc
> `data/server.pid` và kill đúng tiến trình.

### Máy ngủ thì web sập — nên server tự giữ máy thức

Máy này dùng **S0 Modern Standby**, mặc định ngủ sau 5 phút khi cắm điện. Ngủ là
Windows treo tiến trình desktop → web sập. Task Scheduler không giữ thức được, nó chỉ
*đánh thức* máy đúng giờ đã hẹn.

Server tự gọi `SetThreadExecutionState` để khai báo "đang cần hệ thống thức". Chỉ giữ
thức **đúng lúc server chạy**, tắt server là máy về nếp cũ ngay. Không sửa power plan,
không cần quyền admin, gỡ project đi không để lại dấu vết. Màn hình vẫn tự tắt.

Muốn kiểm chứng (cần PowerShell quyền Admin):

```powershell
powercfg /requests        # phải thấy python.exe trong mục SYSTEM
```

---

## Chia sẻ cho người khác xem

Server mở ra internet qua **Tailscale Funnel** — không cần mở port router, không cần
domain, và **URL cố định**, không đổi qua các lần khởi động lại:

```
https://<ten-may>.<tailnet>.ts.net
```

Bật lần đầu: `tailscale up` để đăng nhập, rồi chạy `tailscale funnel --bg 8000`. Lần đầu
nó sẽ báo Funnel chưa được bật cho tailnet kèm một link admin console — mở link đó bấm
bật, xong là vĩnh viễn. Cấu hình funnel do `tailscaled` giữ nên sống qua cả reboot.

Muốn quay về quick tunnel của Cloudflare (không cần tài khoản, đổi lại URL đổi mỗi lần
khởi động) thì đặt `TUNNEL_PROVIDER=cloudflare` trong `.env`. Cả hai đường đều nằm gọn
trong [btcreport/server/tunnel.py](btcreport/server/tunnel.py), phần còn lại không đổi.

Luồng xin quyền:

1. Khách mở link → thấy trang yêu cầu truy cập, phải nhập **tên** và **lời nhắn**
   (tối thiểu 10 ký tự)
2. Ông nhận Telegram kèm tên, lời nhắn, IP, trình duyệt và hai nút **Duyệt / Từ chối**
3. Bấm Duyệt → trang của khách tự chuyển vào dashboard, không cần tải lại
4. Quyền tự hết sau **7 ngày**. `/guests` xem ai đang có quyền, `/revoke <id>` cắt ngay

Chống spam: tối đa 3 yêu cầu / IP / giờ và 20 yêu cầu / giờ toàn cục. Vượt ngưỡng là
chặn **trước khi** gửi Telegram — nếu không, bất kỳ ai cũng làm ngập điện thoại ông.

Cửa sau cho chủ nhà, dùng khi Telegram hỏng hoặc vào từ máy khác:
`<url>/login?key=<OWNER_KEY>`. Đặt `OWNER_KEY` cố định trong `.env`, không thì mỗi lần
khởi động sinh khoá mới (bot vẫn nhắn link).

### Vì sao mọi tunnel đều là một cái bẫy quyền

Tunnel nào cũng proxy vào server, nên request từ internet **có thể mang danh nghĩa
localhost** — mà localhost thì code coi là chủ nhà. Sai chỗ này là mọi người lạ vào
thẳng dashboard. `_is_owner_request()` vì thế chặn hai lớp: thấy bất kỳ header proxy nào
là loại ngay, sau đó mới xét địa chỉ có phải loopback thật không.

Đo thật từ ngoài internet (12/08/2026), không suy đoán:

| Provider | `client.host` | Header proxy | Lớp nào đỡ |
|---|---|---|---|
| Tailscale Funnel | `100.x.y.z` (interface tailscale) | `x-forwarded-for` | **cả hai** |
| Cloudflare tunnel | `127.0.0.1` | `cf-connecting-ip` | chỉ lớp header |

Lớp header fail an toàn đúng chiều: khách tự khai thêm `x-forwarded-for` chỉ tự loại
mình khỏi quyền chủ nhà, không bao giờ được thêm quyền.

Funnel còn bơm vào `tailscale-user-login` / `-name` / `-profile-pic`. **Đừng tin.** Với
traffic công khai chúng không phải danh tính đã xác thực. Có test canh để không ai lỡ
dùng chúng cấp quyền.

**Đổi provider tunnel là phải đo lại từ đầu**, đừng đọc doc rồi tin.

---

## Chạy tay từng phần

```powershell
python -m apps.report --no-browser       # chỉ sinh báo cáo HTML + Telegram
python -m apps.monitor                   # chỉ vòng quét tín hiệu
```

Đừng chạy chúng lúc server đang chạy — hai bên sẽ ghi đè `data/last_signals.json`
của nhau. Kết quả báo cáo: `output/btc_report.html`, file tự chứa, double-click mở được.

---

## Cấu trúc

```
btcreport/          thư viện — không có entrypoint
  config.py         env, đường dẫn, hằng số
  sources/          lấy dữ liệu (Binance, Fear & Greed) + retry/backoff
  engine/           tính toán thuần: chỉ báo, tín hiệu, mức giá — không I/O, không HTML
  notify/           gửi Telegram + soạn text
  web/              render báo cáo HTML: template Jinja2 + CSS + JS rời
  service/          orchestration dùng chung cho apps và server
  server/           FastAPI, dashboard, SSE, quyền truy cập, bot, keepalive, tunnel
apps/               entrypoint: server.py, report.py, monitor.py
scripts/            .bat + setup_tasks.ps1
tests/              pytest + fixtures đóng băng
data/               runtime: state, pid, log, access.json, signals.jsonl
output/             btc_report.html
docs/               ARCHITECTURE.md, structure.html, plan/, spec/
```

Chi tiết ranh giới từng tầng: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Sơ đồ trực quan: [docs/structure.html](docs/structure.html) (mở bằng browser).

---

## Nhật ký tín hiệu

Mỗi tín hiệu mua/bán bắn xuống Telegram đều được ghi lại vào `data/signals.jsonl` và
hiện lên **trang chủ**, mục *Nhật ký tín hiệu*. Bấm vào một dòng để giãn ra xem đúng
nội dung đã nhận trên Telegram.

Chỉ ghi **tín hiệu mua/bán thật** — lỗi fetch không vào nhật ký. Chốt lọc nằm trong
`journal.append()` chứ không ở người gọi, để sau này thêm loại alert mới không lỡ lọt vào.

Định dạng JSONL: mỗi dòng một object JSON, mở bằng notepad đọc được. Chọn nó thay vì một
mảng JSON vì ghi chỉ là nối thêm một dòng — mảng JSON thì mỗi lần bắn phải đọc rồi ghi
đè cả file, kill giữa chừng là **mất sạch lịch sử** chứ không phải mất một dòng.

Hai trường đáng chú ý:

- **`price`** — giá lúc bắn. Không có nó thì sau này không cách nào chấm điểm tín hiệu
  đúng hay sai. Thêm sau là lịch sử cũ vĩnh viễn không có.
- **`first_seen_at`** — lúc thị trường *thật sự* đổi. Debounce giữ 2 lượt quét mới báo
  nên `at` (lúc bắn) trễ hơn khoảng một chu kỳ quét. Có cả hai mới biết độ trễ thật.

Thời gian ghi kèm offset `+07:00` — khách xem từ múi giờ khác không đọc nhầm.

Khách đã được duyệt xem được **toàn bộ** lịch sử, như chủ nhà. Khác với `/api/link` —
cái đó chỉ chủ nhà.

> Nhật ký bắt đầu từ lúc bật tính năng, **không có lịch sử cũ** — trước đó dữ liệu chưa
> từng được lưu. Và với những mã đang dở một chu kỳ chờ lúc nâng cấp, bản ghi đầu tiên sẽ
> có `first_seen_at` bằng `at`; từ chu kỳ sau là đúng.

---

## Tín hiệu hoạt động thế nào

Mỗi khung thời gian được chấm điểm trong khoảng **±7**:

| Thành phần | Điểm |
|---|---|
| RSI < 35 (oversold) | +2 |
| RSI > 70 (overbought) | −2 |
| RSI 55–70 | +1 |
| MACD trên / dưới Signal | ±1 |
| MA7 trên / dưới MA25 | ±1 |
| Giá trên / dưới EMA50 | ±1 |
| Volume > 1.5× TB20 trên nến tăng / giảm | ±1 |
| 3 nến tăng / giảm liên tiếp | ±1 |

`score ≥ 3` → LONG · `score ≤ −3` → SHORT · còn lại NEUTRAL.

Bốn khung (1W · 1D · 4H · 1H) gộp lại thành **confluence**: từ 3 khung đồng thuận trở lên
là STRONG, đúng 2 khung là BIAS.

SL/TP tính theo ATR(14): SL cách entry 1.5×ATR, TP cách 3×ATR — tỷ lệ R:R 1:2.
NEUTRAL thì không đề xuất entry.

### Hai đặc tính cần biết trước khi chỉnh tham số

**Downtrend thuần không ra SHORT được.** RSI < 35 cộng +2 (thành phần mean-reversion)
triệt tiêu các thành phần giảm. SHORT chỉ xuất hiện khi RSI ở vùng giữa. LONG không
vướng chuyện này vì RSI 55–70 còn được cộng thêm. Đây là hành vi cố ý, có test canh —
xem `test_rsi_oversold_bu_lai_downtrend`.

**Report và monitor có thể cho confluence khác nhau trên cùng một mã.** Report lấy
26 nến tuần, monitor lấy 52, nên verdict khung 1W lệch nhau. Hành vi có sẵn từ trước
refactor, chưa thống nhất.

---

## Test

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -q                # 259 test
```

Test chạy trên **fixtures đóng băng** trong `tests/fixtures/` — không gọi mạng, không
phụ thuộc giá thị trường. `tests/golden/` giữ kết quả mốc: số liệu engine và text
Telegram phải khớp tuyệt đối.

Khi **cố ý** đổi công thức chỉ báo hoặc ngưỡng tín hiệu:

```powershell
python -m pytest tests -q                # xem test golden fail ở đâu, đối chiếu số
python tests/capture_golden.py           # số mới đúng ý thì chốt mốc mới
python tests/capture_fixtures.py         # (hiếm) làm mới dữ liệu Binance
```

Đừng chạy `capture_golden.py` theo phản xạ khi test đỏ — làm vậy là hợp thức hoá luôn
cả bug vừa tạo ra.

---

## Lưu ý

- `data/` và `output/` là runtime, đã nằm trong `.gitignore` cùng với `.env`.
- Xoá `data/last_signals.json` sẽ khiến vòng quét coi như chạy lần đầu và bắn lại
  alert "Trạng thái ban đầu" cho cả ba mã.
- **Bot công khai ra internet nghĩa là ai cũng nhắn được nó.** Thứ duy nhất ngăn
  người lạ điều khiển server là chốt kiểm `chat_id` trong `server/access.py`.
  Người lạ nhắn bot chỉ nhận đúng một câu trả lời trung tính.
- Giữ máy thức 24/7 thì tốn điện và nóng hơn. `/pause` hoặc `--allow-sleep` để tắt
  khi không cần.
- Báo cáo chỉ mang tính tham khảo. Đây là công cụ phân tích kỹ thuật, không phải
  lời khuyên đầu tư.
