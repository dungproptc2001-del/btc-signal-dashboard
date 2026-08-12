# Deploy bitcoin-report lên web: server tự host + duyệt truy cập qua Telegram

## Context

Hiện tại báo cáo là file HTML tĩnh sinh 4 tiếng/lần, muốn xem phải mở file trên đúng
máy này. Monitor chạy riêng, chỉ đẩy tín hiệu qua Telegram. Mục tiêu: **một địa chỉ web
cố định, tín hiệu tự cập nhật, xem được từ điện thoại hay bất kỳ đâu**, và người lạ muốn
xem thì phải xin phép — kiểu request access của Google Docs.

Đã chốt: gộp hết vào một process · FastAPI + uvicorn · server tự giữ máy thức nhưng có
chỗ bật/tắt do ông kiểm soát · công khai qua Cloudflare quick tunnel, bot tự báo URL ·
khách được duyệt có quyền 7 ngày, thu hồi được.

### Ba ràng buộc thật của máy này (đã đo, không phải phỏng đoán)

| Phát hiện | Hệ quả |
|---|---|
| `S0 Modern Standby`, ngủ sau 300s (AC) / 180s (DC) | Task Scheduler **không** giữ máy thức được. Ngủ là Windows treo tiến trình desktop → web sập. Server phải tự giữ máy thức bằng `SetThreadExecutionState`. |
| Wi-Fi `10.61.181.249` cấp qua DHCP | Không dùng IP làm địa chỉ cố định được. |
| `cloudflared` chưa cài, chưa có domain | Quick tunnel cho URL `*.trycloudflare.com` **đổi mỗi lần khởi động** → bot phải tự nhắn URL mới. |

Bot `btcreportdung_bot` chưa đặt webhook nên `getUpdates` long-polling dùng được ngay —
không cần Telegram gọi ngược vào máy, tunnel sập thì luồng duyệt vẫn sống.

---

## Kiến trúc

Thêm **một tầng orchestration** giữa engine và apps, để server và các entrypoint cũ dùng
chung logic thay vì copy — đúng bài học từ vụ `confluence()` bị copy 3 bản.

```
btcreport/
├─ service/                  ← MỚI: orchestration dùng chung
│  ├─ watch.py               scan 3 mã + debounce → trả về danh sách alert cần gửi
│  └─ report.py              fetch → build_context → render (rút từ apps/report.py)
├─ server/                   ← MỚI: tầng web
│  ├─ app.py                 FastAPI: route + middleware auth
│  ├─ state.py               cache trong RAM: snapshot, context, URL tunnel, mốc thời gian
│  ├─ scheduler.py           2 vòng nền: giá 30 giây · quét tín hiệu 15 phút · báo cáo 4 tiếng
│  ├─ access.py              session, pending request, hết hạn, thu hồi
│  ├─ bot.py                 long-poll getUpdates, inline button, lệnh điều khiển
│  ├─ keepalive.py           SetThreadExecutionState
│  ├─ tunnel.py              spawn cloudflared, bắt URL từ stdout
│  ├─ templates/             dashboard.html · request_access.html · pending.html
│  └─ static/                dashboard.css · dashboard.js
└─ (engine/ sources/ notify/ web/ giữ nguyên, không sửa)

apps/server.py               python -m apps.server
```

`apps/report.py` và `apps/monitor.py` **giữ lại** để chạy tay, nhưng rút ruột thành lớp
mỏng gọi `service/`.

### Ranh giới giữ nguyên như cũ

`server/` được phép gọi `service/`, `engine/`, `notify/`, `web/`. `engine/` vẫn không biết
web tồn tại. Bổ sung luật vào script kiểm AST: `engine/` và `sources/` cấm import `server`.

---

## Luồng xin quyền truy cập

```
Khách mở URL
  ↓ không có cookie hợp lệ
Trang "Yêu cầu truy cập": nhập TÊN + LỜI NHẮN (bắt buộc, tối thiểu 10 ký tự)
  ↓ POST /access/request
Server tạo pending request → gửi Telegram cho ông:

    🔐 Yêu cầu truy cập
    Tên: Nguyễn Văn A
    Lời nhắn: "em là bạn ở nhóm crypto, muốn xem tín hiệu"
    IP: 1.2.3.4 · Trình duyệt: Chrome/Android
    ⏰ 12/08/2026 16:20
    [ ✅ Duyệt 7 ngày ]  [ ❌ Từ chối ]

  ↓ khách ở trang chờ, poll GET /access/status?id=... mỗi 3 giây
Ông bấm nút → callback_query về bot
  ↓ server KIỂM chat_id có đúng của ông không
Duyệt  → cấp cookie phiên 7 ngày, trang khách tự chuyển vào dashboard
Từ chối → khách thấy thông báo, không cấp gì
```

### Điểm an toàn không được sai

**Callback phải kiểm `chat_id == TELEGRAM_CHAT_ID`.** Bot công khai, ai cũng nhắn được.
Không kiểm thì người lạ chỉ cần gửi đúng callback data là tự duyệt cho chính mình. Mọi
lệnh điều khiển (`/stop`, `/revoke`, `/guests`) cũng chịu cùng một cửa kiểm.

**Chống spam Telegram:** tối đa 3 yêu cầu / IP / giờ và 20 yêu cầu / giờ toàn cục. Vượt
thì trả lỗi cho khách, không gửi Telegram. Không có cái này thì bất kỳ ai cũng làm ngập
điện thoại ông.

**Bot token không bao giờ xuống client.** Chỉ server giữ.

**Cookie**: `HttpOnly`, `SameSite=Lax`, `Secure` khi truy cập qua tunnel HTTPS.
Token 32 byte sinh bằng `secrets.token_urlsafe`.

**Ông luôn vào được**: request từ `127.0.0.1` được coi là chủ nhà; ngoài ra `OWNER_KEY`
trong `.env`, mở `?key=...` một lần để nhận cookie chủ. Không phụ thuộc Telegram khi cần
vào gấp.

Lưu ở `data/access.json`: danh sách phiên còn hạn + lịch sử duyệt/từ chối. Ghi atomic
bằng `os.replace` như `last_signals.json`.

---

## Web hiển thị gì

| Route | Auth | Nội dung |
|---|---|---|
| `GET /` | có | Dashboard: 3 mã, giá sống, 4 khung mỗi mã, confluence, đếm ngược lần quét tới |
| `GET /report` | có | Báo cáo BTC đầy đủ, render từ cache — dùng lại `web/renderer.py` nguyên vẹn |
| `GET /api/signals` | có | JSON snapshot 3 mã |
| `GET /api/report` | có | JSON context đầy đủ — để Crypto Research Agent gọi lại sau này |
| `GET /events` | có | SSE đẩy cập nhật, dashboard không cần reload |
| `POST /access/request` | không | Gửi yêu cầu |
| `GET /access/status` | không | Khách poll trạng thái yêu cầu của mình |
| `GET /healthz` | không | Kiểm server sống, không lộ dữ liệu |
| `GET /docs` | có | FastAPI tự sinh |

**Hai nhịp cập nhật** — đây là thứ làm trang "sống" thật:

- **30 giây**: chỉ gọi ticker 24h của 3 mã (rẻ), đẩy giá qua SSE. Giá nhảy liên tục.
- **15 phút**: quét đủ 4 khung, tính lại tín hiệu, chạy debounce, gửi Telegram nếu đổi.
- **4 tiếng**: dựng lại báo cáo BTC đầy đủ, ghi `output/btc_report.html`, gửi Telegram.

Cache trong RAM nên mở trang không kích hoạt fetch — 100 lượt xem cũng không thêm một
request nào tới Binance.

---

## Giữ máy thức và chỗ để ông kiểm soát

`keepalive.py` gọi `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` lúc
khởi động, nhả bằng `ES_CONTINUOUS` lúc tắt (kèm `atexit` + signal handler như monitor
đang làm). **Không xin `ES_DISPLAY_REQUIRED`** nên màn hình vẫn tắt bình thường.
Không sửa power plan — gỡ server là máy về nếp cũ ngay.

Bảng điều khiển, tất cả đều trong tay ông:

| Cách | Việc |
|---|---|
| `scripts/server_start.bat` | Bật server |
| `scripts/server_stop.bat` | Tắt, nhả keep-alive, dọn pid |
| `scripts/server_status.bat` | Đang chạy không, URL nào, quét lần cuối lúc nào |
| Task "BTC Web Server" | Tự bật lúc đăng nhập — disable trong Task Scheduler là xong |
| `--allow-sleep` | Chạy server mà không giữ máy thức |
| `--no-tunnel` | Chỉ chạy LAN, không mở ra internet |
| Telegram `/status` | Trạng thái + URL hiện tại |
| Telegram `/url` | Lấy lại link tunnel |
| Telegram `/pause` `/resume` | Dừng/chạy lại vòng quét, web vẫn sống |
| Telegram `/stop` | Tắt hẳn server từ điện thoại |
| Telegram `/guests` `/revoke <id>` | Xem ai đang có quyền, cắt quyền |

Mỗi lần server bật, bot nhắn: URL tunnel mới + `OWNER_KEY` link để ông vào thẳng.

---

## Việc phải làm, theo thứ tự

| # | Bước | Xong khi |
|---|---|---|
| 1 | Cài `fastapi`, `uvicorn[standard]`, `httpx`; cài `cloudflared` bằng winget | `python -c "import fastapi, uvicorn"` chạy được |
| 2 | Rút `service/report.py` + `service/watch.py` từ `apps/`, viết test cho debounce | `pytest` xanh, `apps/report.py` và `apps/monitor.py` vẫn chạy y hệt |
| 3 | `server/state.py` + `server/scheduler.py` — 3 nhịp, cache RAM | Chạy 2 phút thấy giá đổi, quét đủ 3 mã |
| 4 | `server/access.py` + test — phiên, hết hạn, thu hồi, **chặn chat_id lạ** | `pytest tests/test_access.py` xanh |
| 5 | `server/bot.py` — long-poll, inline button, lệnh điều khiển | Bấm nút trên Telegram thật thấy server nhận |
| 6 | `server/app.py` + template dashboard + SSE | Mở `localhost:8000` thấy giá nhảy |
| 7 | `keepalive.py` + `tunnel.py` | `powercfg /requests` thấy request đang giữ; bot nhắn URL |
| 8 | `scripts/` + Task Scheduler: nghỉ 2 task cũ, dựng task "BTC Web Server" | Task `LastTaskResult` hợp lệ, server tự lên sau đăng nhập |
| 9 | Cập nhật `README.md`, `docs/ARCHITECTURE.md`, `docs/structure.html`; ghi plan + spec vào `docs/` | Sơ đồ khớp code, script kiểm AST vẫn 0 vi phạm |

Bước 8 nghỉ `BTC Report 4H` và `BTC Signal Monitor` — công việc của chúng chuyển vào
scheduler của server. **Giữ nguyên `data/last_signals.json`**, mất là monitor bắn lại
alert "Trạng thái ban đầu" cho cả 3 mã.

---

## Nghiệm thu

```powershell
cd E:\bitcoin-report
python -m pytest tests -q                    # test cũ + test_watch/test_access/test_api

# Chạy tay, chưa mở tunnel
python -m apps.server --no-tunnel
#   → localhost:8000 vào thẳng (chủ nhà), giá đổi sau ~30 giây

# Keep-alive có thật không
powercfg /requests                           # phải thấy SYSTEM request của python.exe

# Luồng xin quyền — thử bằng trình duyệt ẩn danh qua URL tunnel
#   1. Mở URL → hiện trang xin quyền
#   2. Nhập tên + lời nhắn → Telegram ông nhận được kèm 2 nút
#   3. Bấm Duyệt → trang khách tự vào dashboard
#   4. /guests thấy khách đó → /revoke → khách bị đá ra ngay

# Kiểm chốt chặn an toàn
#   - Nhắn callback từ tài khoản Telegram khác → server phải từ chối
#   - Gửi 4 yêu cầu liên tiếp cùng IP → cái thứ 4 bị chặn, KHÔNG gửi Telegram
#   - GET /api/signals không cookie → 401

# Task Scheduler
powershell -ExecutionPolicy Bypass -File .\scripts\setup_tasks.ps1
schtasks /run /tn "BTC Web Server"
Get-Content data\server.log -Encoding utf8 -Tail 20
```

Chốt cuối: đóng laptop 10 phút rồi mở URL từ điện thoại (4G, không dùng Wi-Fi nhà) —
trang phải vẫn lên, và `data/last_signals.json` giữ đúng confluence của 3 mã.

---

## Rủi ro đã biết

**Máy thức 24/7 tốn điện và nóng hơn.** Đây là cái giá của việc tự host trên laptop.
`/pause` và `--allow-sleep` có sẵn để ông tắt khi không cần.

**URL đổi mỗi lần khởi động server.** Quick tunnel không có URL cố định. Bot tự nhắn URL
mới nên ông luôn biết, nhưng khách đã được duyệt sẽ phải xin link lại. Mua domain rồi thì
chuyển sang named tunnel, chỉ đổi `tunnel.py` và file config — phần còn lại giữ nguyên.

**Công khai internet nghĩa là bot của ông lộ diện.** Ai biết `btcreportdung_bot` đều nhắn
được. Chốt chặn `chat_id` là thứ duy nhất ngăn người lạ điều khiển server, nên nó phải
đúng ngay từ đầu và có test canh.

**Server chết là mất cả web lẫn alert.** Trước đây hỏng monitor thì báo cáo vẫn chạy.
Bù lại bằng Task Scheduler restart mỗi 5 phút (đã dùng cho monitor) và `/healthz`.

---

## Ngoài phạm vi

Không đụng `engine/`, `sources/`, `notify/`, `web/` — bốn tầng này giữ nguyên, chỉ thêm
người gọi mới. Không đổi công thức chỉ báo, ngưỡng tín hiệu hay chu kỳ quét. Không đụng
`E:\btc_strategy\`. Chưa làm: lịch sử tín hiệu dạng biểu đồ theo thời gian, nhiều người
dùng có phân quyền khác nhau, backtest.
