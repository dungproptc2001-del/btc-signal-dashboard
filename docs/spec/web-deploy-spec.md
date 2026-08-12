# Spec — Deploy lên web: server tự host + duyệt truy cập qua Telegram

> Plan tương ứng: [../plan/web-deploy-plan.md](../plan/web-deploy-plan.md)

## 0. Nguyên tắc bất di bất dịch

1. **Không đụng 4 tầng cũ.** `engine/`, `sources/`, `notify/`, `web/` giữ nguyên. Chỉ
   thêm người gọi mới. Công thức chỉ báo, ngưỡng tín hiệu, chu kỳ quét: không đổi.
2. **Không copy logic.** Server và `apps/monitor.py` dùng chung `service/watch.py`.
   Bài học từ vụ `confluence()` bị copy 3 bản.
3. **Mọi lệnh điều khiển phải kiểm `chat_id`.** Bot công khai; không kiểm là người lạ
   điều khiển được server.
4. **Cache trong RAM.** Mở trang không kích hoạt fetch. 100 lượt xem = 0 request tới Binance.
5. **Ông luôn vào được** kể cả khi Telegram hỏng: localhost là chủ nhà, `OWNER_KEY` là
   cửa sau.

---

## 1. Tầng service — orchestration dùng chung

### `btcreport/service/report.py`

```python
def build_report() -> tuple[str, str, dict]
# (html, telegram_message, context) – fetch + build_context + render
```
Rút nguyên từ `apps/report.py` hiện tại. `apps/report.py` thành lớp mỏng gọi hàm này.

### `btcreport/service/watch.py`

```python
def get_snapshot(symbol: str) -> tuple[bool, dict | None]
# (ok, snapshot). ok=False nghĩa là fetch lỗi – KHÔNG phải "signal không đổi".

def scan_symbols(state: dict, symbols: dict) -> tuple[dict, list[Alert]]
# Trả state mới + danh sách alert CẦN GỬI. Bản thân hàm KHÔNG gửi Telegram.
```

Tách "quyết định gửi gì" khỏi "gửi" là điểm mấu chốt: test được toàn bộ logic debounce
mà không cần mock Telegram, và server có thể vừa gửi Telegram vừa đẩy SSE từ cùng một
kết quả.

`Alert` là dict: `{"kind": "signal"|"fetch_failure", "name", "symbol", "text", "snapshot"}`.

Logic debounce giữ nguyên hành vi hiện có:
- confluence == state đã confirm → xoá pending
- khác → `pending_count += 1`; chưa đủ `CONFIRM_SCANS` thì im lặng; đủ thì phát alert
- lần đầu (chưa có `confluence` trong state) → phát alert ngay
- fetch lỗi → `consec_fails += 1`, giữ nguyên state cũ; chạm `MAX_CONSEC_FAILS` phát
  alert `fetch_failure`

State file `data/last_signals.json` **giữ nguyên cấu trúc**:
```json
{"BTCUSDT": {"confluence", "timestamp", "pending", "pending_count", "consec_fails"}}
```

---

## 2. Tầng server

### `btcreport/server/state.py`

Cache trong RAM, có khoá đọc/ghi:

```python
class ServerState:
    prices:      dict[str, dict]      # symbol -> {last, change_24h, at}
    snapshots:   dict[str, dict]      # symbol -> snapshot của watch
    signal_state: dict                # state debounce (đồng bộ với file)
    report_ctx:  dict | None          # context báo cáo BTC gần nhất
    report_html: str | None
    tunnel_url:  str | None
    started_at:  datetime
    last_price_at / last_scan_at / last_report_at: datetime | None
    paused:      bool
    subscribers: set                  # hàng đợi SSE
```

```python
def publish(event: str, data: dict) -> None    # đẩy tới mọi subscriber SSE
def snapshot_public() -> dict                  # dữ liệu an toàn để trả ra web
```

`snapshot_public()` **không được** chứa `OWNER_KEY`, token phiên, hay bot token.

### `btcreport/server/scheduler.py`

Ba nhịp chạy nền, mỗi nhịp một task asyncio, mọi call chặn đẩy qua threadpool:

| Nhịp | Chu kỳ | Việc |
|---|---|---|
| `price_loop` | 30 giây | `fetch_ticker` cho 3 mã → cập nhật `prices` → `publish("price", …)` |
| `scan_loop` | `SCAN_INTERVAL` (15 phút) | `scan_symbols()` → gửi alert Telegram + `publish("signal", …)` → lưu state |
| `report_loop` | 4 tiếng | `build_report()` → ghi `output/btc_report.html` → Telegram → `publish("report", …)` |

`paused = True` thì `scan_loop` và `report_loop` bỏ lượt, `price_loop` vẫn chạy (web
vẫn sống). Mỗi vòng bọc `try/except` — một lỗi không được giết cả nhịp.

Lần khởi động đầu chạy ngay một lượt cả ba, không đợi hết chu kỳ.

### `btcreport/server/access.py`

```python
GUEST_TTL_DAYS   = 7
MAX_REQ_PER_IP   = 3     # mỗi giờ
MAX_REQ_GLOBAL   = 20    # mỗi giờ
MIN_MESSAGE_LEN  = 10

def create_request(name, message, ip, user_agent) -> dict   # raise RateLimited
def approve(request_id, by_chat_id) -> dict | None          # trả session
def deny(request_id, by_chat_id) -> bool
def check_session(token) -> dict | None                     # None nếu hết hạn/thu hồi
def list_guests() -> list[dict]
def revoke(session_id) -> bool
def purge_expired() -> int
```

`approve`/`deny`/`revoke` **bắt buộc** nhận `by_chat_id` và so với `TELEGRAM_CHAT_ID`;
sai thì trả `None`/`False` và ghi log cảnh báo. Đây là chốt chặn duy nhất giữa người lạ
và quyền điều khiển.

Token phiên: `secrets.token_urlsafe(32)`. Lưu `data/access.json`, ghi atomic bằng
`os.replace`. Cấu trúc:

```json
{
  "sessions": [{"id", "token", "name", "message", "ip", "ua",
                "granted_at", "expires_at", "revoked": false}],
  "pending":  [{"id", "name", "message", "ip", "ua", "created_at", "status"}],
  "history":  [{"id", "name", "action", "at"}]
}
```

### `btcreport/server/bot.py`

Long-poll `getUpdates` (offset lưu lại) trong task nền. Không dùng webhook: tunnel sập
thì luồng duyệt vẫn sống.

Xử lý `callback_query` với data dạng `approve:<id>` / `deny:<id>`, và các lệnh:

| Lệnh | Việc |
|---|---|
| `/status` | Server sống bao lâu, URL, mốc quét/báo cáo gần nhất, số khách |
| `/url` | Link tunnel hiện tại + link chủ nhà kèm `OWNER_KEY` |
| `/pause` `/resume` | Bật/tắt nhịp quét, web vẫn sống |
| `/stop` | Tắt server |
| `/guests` | Ai đang có quyền, còn bao lâu |
| `/revoke <id>` | Cắt quyền ngay |
| `/scan` | Ép quét ngay, không đợi chu kỳ |

**Mọi lệnh và callback đều đi qua một hàm gác duy nhất** kiểm `chat_id == TELEGRAM_CHAT_ID`.
Người lạ nhắn bot chỉ nhận được một câu trả lời trung tính, không lộ gì.

### `btcreport/server/keepalive.py`

```python
def hold()    -> bool   # SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
def release() -> None   # SetThreadExecutionState(ES_CONTINUOUS)
```
Không xin `ES_DISPLAY_REQUIRED` → màn hình vẫn tắt. Gọi `release()` qua `atexit` + signal
handler. Không phải Windows thì thành no-op, trả `False`.

### `btcreport/server/tunnel.py`

```python
def start(port: int, timeout=30) -> str | None   # spawn cloudflared, bắt URL từ stderr
def stop() -> None
```
Regex bắt `https://<random>.trycloudflare.com` trong output. Không có `cloudflared` hoặc
quá `timeout` → trả `None`, server vẫn chạy LAN bình thường (không được sập vì thiếu tunnel).

### `btcreport/server/app.py`

FastAPI. Middleware auth chạy trước mọi route trừ danh sách miễn trừ.

| Route | Auth | Trả về |
|---|---|---|
| `GET /` | có | Dashboard |
| `GET /report` | có | HTML báo cáo từ cache |
| `GET /api/signals` | có | JSON: prices + snapshots + mốc thời gian |
| `GET /api/report` | có | JSON context đầy đủ |
| `GET /events` | có | SSE |
| `GET /login?key=` | không | Đặt cookie chủ nhà nếu `key == OWNER_KEY` |
| `POST /access/request` | không | `{request_id}` hoặc 429 |
| `GET /access/status` | không | `{status: pending\|approved\|denied}`, kèm `Set-Cookie` khi approved |
| `GET /healthz` | không | `{ok, uptime}` – không lộ dữ liệu |

Chưa có phiên → `GET /` trả trang xin quyền (200, không phải 401 cho đẹp mắt), còn
`/api/*` trả **401 JSON**.

Cookie `btcr_session`: `HttpOnly`, `SameSite=Lax`, `Secure` khi request đến qua HTTPS,
`max_age = 7 ngày`.

Chủ nhà: `request.client.host in ("127.0.0.1", "::1")` → luôn qua.

### `apps/server.py`

```
python -m apps.server [--port 8000] [--no-tunnel] [--allow-sleep] [--host 0.0.0.0]
```
Thứ tự: keepalive → tunnel → scheduler → bot → uvicorn. Tắt thì ngược lại.
Ghi `data/server.pid`, dọn bằng `atexit` + signal handler.
Khởi động xong nhắn Telegram: URL tunnel + link chủ nhà.

---

## 3. Frontend

`dashboard.html` — dark theme khớp báo cáo BTC (`#0a0e1a` / `#0f172a` / `#f59e0b`):

- Ba thẻ mã: giá lớn, đổi 24h, confluence, 4 khung mini (1W/1D/4H/1H)
- Thanh trạng thái: quét lần cuối, đếm ngược lần tới, chấm xanh khi SSE còn kết nối
- Nút mở báo cáo BTC đầy đủ
- SSE: `price` cập nhật số, `signal` vẽ lại thẻ, `report` bật badge "có báo cáo mới"
- SSE đứt → tự nối lại sau 5 giây, chấm chuyển đỏ

`request_access.html` — form Tên + Lời nhắn (đếm ký tự, tối thiểu 10), gửi xong chuyển
sang trạng thái chờ, poll `/access/status` mỗi 3 giây, được duyệt thì tự vào dashboard.

Tất cả CSS/JS inline như `web/renderer.py` đang làm — không phụ thuộc CDN ngoài trừ
Chart.js của trang báo cáo (giữ nguyên).

---

## 4. Test

Thêm `tests/test_watch.py`, `tests/test_access.py`, `tests/test_api.py`.
Thêm `httpx` + `pytest-asyncio` vào `requirements-dev.txt`.

| Test | Điều kiện đạt |
|---|---|
| `test_watch` | Debounce: lật giả `NEUTRAL→LONG→NEUTRAL` cho **0 alert**; đủ 2 lần mới alert; lần đầu alert ngay; fetch lỗi không đổi state và đếm đúng; chạm ngưỡng phát `fetch_failure` |
| `test_access` | Phiên hết hạn sau 7 ngày; `revoke` cắt ngay; **`approve` với `chat_id` lạ trả `None`**; quá 3 request/IP/giờ raise `RateLimited`; lời nhắn < 10 ký tự bị từ chối; token đủ dài và không trùng |
| `test_api` | `/api/*` không cookie → 401; `/healthz` không cần auth và không lộ dữ liệu; `/` không phiên → trang xin quyền; cookie hợp lệ → dashboard; `/login?key=sai` → không cấp cookie; `snapshot_public()` không chứa token nào |

Script kiểm AST bổ sung luật: `engine/` và `sources/` cấm import `server` hoặc `service`.

---

## 5. Nghiệm thu

```powershell
cd E:\bitcoin-report
python -m pytest tests -q

python -m apps.server --no-tunnel
#   localhost:8000 vào thẳng; sau ~30 giây giá phải đổi
powercfg /requests                     # phải thấy SYSTEM request của python.exe

# Luồng xin quyền (trình duyệt ẩn danh qua URL tunnel)
#   1. Mở URL → trang xin quyền
#   2. Điền tên + lời nhắn → Telegram nhận được kèm 2 nút
#   3. Bấm Duyệt → trang khách tự vào dashboard
#   4. /guests thấy khách → /revoke → khách bị đá ra

# Chốt chặn an toàn
#   - callback từ tài khoản Telegram khác → bị từ chối
#   - 4 request liên tiếp cùng IP → cái thứ 4 bị chặn, KHÔNG gửi Telegram
#   - curl /api/signals không cookie → 401

powershell -ExecutionPolicy Bypass -File .\scripts\setup_tasks.ps1
schtasks /run /tn "BTC Web Server"
```

Chốt cuối: đóng laptop 10 phút, mở URL từ điện thoại qua 4G — trang vẫn lên, và
`data/last_signals.json` giữ đúng confluence 3 mã, không có alert "Trạng thái ban đầu"
nào bị bắn lại.
