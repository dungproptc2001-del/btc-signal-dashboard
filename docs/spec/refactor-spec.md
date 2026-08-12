# Spec — Refactor bitcoin-report

> Bản hợp đồng kỹ thuật cho đợt refactor tách engine / frontend.
> Plan tương ứng: [../plan/refactor-plan.md](../plan/refactor-plan.md)

## 0. Nguyên tắc bất di bất dịch

1. **Giữ nguyên hành vi.** Cùng một bộ nến đầu vào phải cho ra cùng verdict, cùng score, cùng SL/TP, cùng text Telegram như code trước refactor. Công thức chỉ báo, ngưỡng tín hiệu, chu kỳ quét: không đụng.
2. **Engine không biết HTML.** `btcreport/engine/` không được chứa thẻ HTML, mã màu hex, hay emoji. Chỉ số và chuỗi định danh.
3. **Engine không đụng mạng.** `btcreport/engine/` không được `import requests`. Nhận nến, trả kết quả.
4. **Renderer không tính toán.** `btcreport/web/` chỉ định dạng và sắp xếp cái context đã có. Không gọi indicator, không so sánh ngưỡng.
5. **Output là một file HTML tự chứa.** CSS và JS được inline lúc render. Double-click mở được, không cần server.

---

## 1. Quy ước dữ liệu

### Candle
```python
{"ts": int,      # epoch milliseconds
 "open": float, "high": float, "low": float, "close": float, "volume": float}
```
Danh sách nến luôn sắp xếp cũ → mới. `candles[-1]` là nến gần nhất.

### Series
Chỉ báo trả về list cùng độ dài với input, phần chưa đủ dữ liệu điền `None`.

### Verdict
Chuỗi thuộc `{"LONG", "SHORT", "NEUTRAL"}`. Riêng khung thiếu dữ liệu dùng `"N/A"`.

### Confluence verdict
Chuỗi thuộc `{"STRONG LONG", "LONG BIAS", "NEUTRAL", "SHORT BIAS", "STRONG SHORT"}`.

---

## 2. API từng module

### `btcreport/config.py`

```python
BASE_DIR: Path          # gốc project
DATA_DIR: Path          # BASE_DIR/data   — state, pid, log
OUTPUT_DIR: Path        # BASE_DIR/output — btc_report.html

TELEGRAM_BOT_TOKEN: str
TELEGRAM_CHAT_ID: str

BINANCE_URL   = "https://api.binance.com/api/v3"
SYMBOL        = "BTCUSDT"                    # mã của báo cáo
SYMBOLS       = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "XAU": "PAXGUSDT"}

HTTP_RETRIES      = 4
HTTP_BACKOFF_SEC  = 2.0
MAX_SCORE         = 7
SIGNAL_THRESHOLD  = 3
ATR_MULT_SL       = 1.5
ATR_MULT_TP       = 3.0
SCAN_INTERVAL     = 900      # giây
CONFIRM_SCANS     = 2
MAX_CONSEC_FAILS  = 4

def load_dotenv(path: Path | None = None) -> None
```
`load_dotenv()` chạy lúc import module. Dùng `os.environ.setdefault` — biến môi trường thật luôn thắng file `.env`.
`DATA_DIR` và `OUTPUT_DIR` được `mkdir(parents=True, exist_ok=True)` lúc import.

### `btcreport/sources/http.py`

```python
def get_json(url: str, params: dict | None = None,
             timeout: int = 15, retries: int = HTTP_RETRIES) -> Any
```
Retry với lỗi mạng, timeout, HTTP 429 và 5xx. HTTP 4xx khác **raise ngay**, không retry.
Backoff `HTTP_BACKOFF_SEC * 2**attempt + jitter(0..1)`; nếu response có header `Retry-After` thì header thắng.
Hết lượt thì raise exception cuối cùng.

### `btcreport/sources/binance.py`

```python
def parse_klines(raw: list) -> list[Candle]
def fetch_klines(symbol: str, interval: str, limit: int) -> list[Candle]
def fetch_klines_range(symbol: str, interval: str,
                       start: datetime, end: datetime) -> list[Candle]
def fetch_ticker(symbol: str) -> dict
```

### `btcreport/sources/feargreed.py`

```python
def fetch_fear_greed() -> tuple[int | None, str]     # (27, "Fear") | (None, "N/A")
```
Nuốt lỗi và trả `(None, "N/A")` — chỉ số phụ, không được làm chết cả báo cáo.

### `btcreport/engine/indicators.py`

```python
def last_valid(series: list, default=None)           # thay cho next(reversed(...))
def sma(closes, n)                -> list[float | None]
def ema(closes, n)                -> list[float | None]
def rsi(closes, period=14)        -> list[float | None]
def macd_line(closes, fast=12, slow=26, signal=9) -> tuple[list, list, list]  # macd, signal, hist
def bollinger(closes, n=20, k=2)  -> tuple[list, list, list]                  # upper, mid, lower
def atr(candles, period=14)       -> float
```
Thứ tự trả về của `macd_line` và `bollinger` **giữ y như hiện tại** (`bollinger` → upper, mid, lower).

### `btcreport/engine/signals.py`

```python
def generate_signal(candles: list[Candle]) -> dict
# {"verdict": str, "action": str, "score": int,
#  "max_score": MAX_SCORE, "reasons": list[str]}

def confluence(verdicts: list[str]) -> dict
# {"verdict": str, "agree": int}
```

**Đổi chữ ký:** `generate_signal` cũ nhận `(candles, rsi_vals, macd_val, sig_full)` — caller phải tự tính đúng thứ tự. Bản mới chỉ nhận `candles`, tự tính RSI/MACD bên trong. **Không trả mã màu nữa.**

Thang điểm giữ nguyên, tổng biên độ ±7:

| Thành phần | Điểm |
|---|---|
| RSI < 35 | +2 |
| RSI > 70 | −2 |
| RSI 55–70 | +1 |
| MACD trên/dưới Signal | ±1 |
| MA7 trên/dưới MA25 | ±1 |
| Giá trên/dưới EMA50 | ±1 |
| Volume > 1.5× TB20 trên nến tăng/giảm | ±1 |
| 3 nến tăng/giảm liên tiếp | ±1 |

`score >= 3` → LONG (`action` = "MUA / GIỮ"); `score <= -3` → SHORT ("BÁN / SHORT"); còn lại NEUTRAL ("CHỜ XÁC NHẬN").

`confluence` đếm trên 4 khung: ≥3 LONG → STRONG LONG; ==2 LONG → LONG BIAS; ≥3 SHORT → STRONG SHORT; ==2 SHORT → SHORT BIAS; còn lại NEUTRAL. `agree = max(long_count, short_count)`.

Đây là **bản duy nhất** — ba chỗ đang copy logic này bị xoá.

### `btcreport/engine/levels.py`

```python
def support_resistance(candles, lookback=20) -> dict
# {"pivot":…, "R1":…, "R2":…, "S1":…, "S2":…}

def risk_levels(candles, verdict,
                atr_mult_sl=ATR_MULT_SL, atr_mult_tp=ATR_MULT_TP) -> dict
# {"entry":…, "sl":…, "tp":…, "atr":…, "rr":…}
```
`verdict == "NEUTRAL"` hoặc `atr == 0` → `sl`, `tp`, `rr` là `None`. Mọi chỗ tiêu thụ phải kiểm `if risk["sl"]`.

### `btcreport/engine/analysis.py`

```python
def get_thu_range() -> tuple[datetime, datetime]     # thứ 5 tuần trước → thứ 5 tuần này (UTC)

def analyze_timeframe(label: str, candles: list[Candle] | None) -> dict
# {"label": "4H", "verdict": …, "score": int, "rsi": float,
#  "macd": float, "macd_signal": float, "macd_bull": bool}
# candles rỗng/None -> verdict "N/A", score 0, rsi 50, macd_bull False

def build_context(*, symbol, now, daily, weekly, h4, h1,
                  ticker, fear_greed, week_candles,
                  week_start, week_end) -> dict
```

`build_context` **không fetch gì cả** — nhận dữ liệu thô, trả context. Đây là hàm được test bằng fixtures.

### Schema context

```python
{
  "symbol": "BTCUSDT",
  "generated_at": datetime,
  "price":       {"last", "change_24h", "high_24h", "low_24h", "volume_24h"},
  "fear_greed":  {"value": int|None, "label": str},
  "week":        {"start": datetime, "end": datetime,
                  "open", "close", "high", "low", "change_pct"},
  "signal":      {"verdict", "action", "score", "max_score",
                  "confidence": int, "reasons": [str]},
  "timeframes":  [ {analyze_timeframe(...)} × 4 ],      # thứ tự 1W, 1D, 4H, 1H
  "confluence":  {"verdict", "agree"},
  "levels":      {"pivot", "R1", "R2", "S1", "S2"},     # từ nến ngày
  "levels_4h":   {…},                                    # từ nến 4H, dùng cho Telegram
  "risk":        {"entry", "sl", "tp", "atr", "rr"},
  "chart": {
    "daily": {"labels": [str], "open": [], "high": [], "low": [], "close": [],
              "volume": [], "ma7": [], "ma25": [], "ma99": [],
              "rsi": [], "macd": [], "macd_signal": [], "macd_hist": [],
              "bb_upper": [], "bb_mid": [], "bb_lower": []},
    "h4":    {"labels": [], "close": [], "ma7": [], "ma25": []},
    "h1":    {"labels": [], "close": [], "ma7": [], "ma25": []}
  },
  "week_table": [ {"date": str, "open","high","low","close","volume","change_pct"} ]
}
```
`confidence = min(round(abs(score) / MAX_SCORE * 90) + 10, 100)`.
Context phải JSON-dump được (datetime serialize bằng `isoformat` trong test golden).

### `btcreport/notify/telegram.py`

```python
def send_telegram(text: str, retries: int = 3) -> bool
```
Chưa cấu hình token → in cảnh báo, trả `False`, **không raise**.

### `btcreport/notify/messages.py`

```python
def format_report_message(ctx: dict) -> str
def format_monitor_alert(name: str, prev: str, snap: dict, now: str) -> str
def format_monitor_startup(symbols, interval_min, confirm_scans) -> str
def format_fetch_failure(name: str, fails: int, interval_min: int) -> str
```
Emoji và icon nằm ở đây, không nằm trong engine. Text sinh ra phải **khớp byte-for-byte** với bản hiện tại (test golden giữ).

### `btcreport/web/filters.py`

| Filter | Vào | Ra |
|---|---|---|
| `usd` | `63739.24` | `$63,739` |
| `usd2` | `63739.24` | `$63,739.24` |
| `pct` | `-1.82` | `-1.82%` |
| `signed` | `-3` | `-3` / `+3` |
| `verdict_class` | `"LONG"` | `pill-green` |
| `verdict_icon` | `"LONG"` | `🟢` |
| `num` | `1234.5` | `1,235` |

### `btcreport/web/renderer.py`

```python
def render_report(ctx: dict) -> str
```
`Environment(loader=FileSystemLoader(templates/), autoescape=True)`, nạp filter từ `filters.py`.
Đọc `static/styles.css` và `static/charts.js`, truyền vào template dưới dạng biến `inline_css` / `inline_js` và render bằng `|safe`.
Dữ liệu chart truyền một lần: `{{ chart | tojson }}` — thay cho 21 placeholder rời hiện tại.

### `apps/report.py`

```python
python -m apps.report [--no-browser]
```
Luồng: `get_thu_range` → fetch (1w/1d/4h/1h + range tuần + ticker + F&G) → `build_context` → `render_report` → ghi `output/btc_report.html` → `format_report_message` → `send_telegram` → mở browser nếu không có `--no-browser`.
Bọc `try/except` toàn cục: lỗi thì gửi Telegram `❌ BTC Report lỗi` rồi re-raise.

### `apps/monitor.py`

```python
python -m apps.monitor
```
Giữ nguyên toàn bộ hành vi hiện có: pid file, atexit + signal handler, ghi state atomic bằng `os.replace`, debounce `CONFIRM_SCANS`, đếm `consec_fails` và cảnh báo khi chạm `MAX_CONSEC_FAILS`, `try/except` quanh mỗi vòng scan.
Đường dẫn đổi sang `DATA_DIR`: `data/last_signals.json`, `data/monitor.pid`.

**Cấu trúc state file giữ nguyên** để không mất trạng thái:
```json
{"BTCUSDT": {"confluence": str, "timestamp": str,
             "pending": str, "pending_count": int, "consec_fails": int}}
```

---

## 3. Frontend

`web/templates/report.html` — markup thuần Jinja2, không còn escape `{{ }}` nào cho CSS/JS.
`web/static/styles.css` — 41 dòng CSS hiện tại, bỏ escape, thêm class thay cho style inline của `_tf_card_html` và `risk_html`.
`web/static/charts.js` — 177 dòng Chart.js hiện tại, đọc dữ liệu từ một biến toàn cục `REPORT_DATA` do template chèn.

Ba khối đang build chuỗi HTML trong Python chuyển thành vòng lặp Jinja:
- `_tf_card_html` → `{% for tf in timeframes %}` + macro `tf_card`
- `risk_html` → `{% if risk.sl %}…{% else %}…{% endif %}`
- `reasons_html` → `{% for r in signal.reasons %}`

Sửa luôn `&#₿;` (entity không hợp lệ) thành `&#8383;`.

---

## 4. Test

`requirements.txt`: `requests`, `jinja2`. `requirements-dev.txt`: `pytest`.

```
tests/
├─ capture_fixtures.py       # chạy tay một lần, gọi Binance, lưu fixtures
├─ conftest.py               # fixture nạp JSON
├─ fixtures/                 # klines_1w/1d/4h/1h.json, ticker.json, feargreed.json, week.json
├─ golden/                   # context.json, telegram.txt
├─ test_indicators.py
├─ test_signals.py
├─ test_levels.py
├─ test_context.py
├─ test_messages.py
└─ test_render.py
```

| Test | Điều kiện đạt |
|---|---|
| `test_indicators` | sma/ema/rsi/macd/bollinger/atr đúng trên chuỗi tính tay; độ dài output == input; prefix `None` đúng vị trí |
| `test_signals` | Từng thành phần điểm cộng/trừ đúng; biên score 2/3 và −2/−3 ra đúng verdict; 5 nhánh confluence |
| `test_levels` | `support_resistance` đúng công thức pivot; LONG có `sl < entry < tp`, SHORT ngược lại; NEUTRAL trả `sl=None` |
| `test_context` | `build_context` từ fixtures khớp `golden/context.json` (float so với `rel=1e-9`) |
| `test_messages` | `format_report_message` khớp `golden/telegram.txt` byte-for-byte |
| `test_render` | Render không raise; HTML chứa `<canvas id="priceChart">`, khối ATR, 4 thẻ khung; **không còn** `&#₿;`, không sót `{{` hay `{%` |

---

## 5. Nghiệm thu cuối

```powershell
cd E:\bitcoin-report
python -m pytest tests -q                       # tất cả xanh
python -m apps.report --no-browser              # output/btc_report.html sinh mới
python -m apps.monitor                          # 1 vòng quét đủ BTC/ETH/XAU, Ctrl+C
powershell -ExecutionPolicy Bypass -File .\scripts\setup_tasks.ps1
schtasks /run /tn "BTC Report 4H"
schtasks /run /tn "BTC Signal Monitor"
Get-ScheduledTaskInfo -TaskName 'BTC Report 4H','BTC Signal Monitor' |
    Select-Object TaskName, LastTaskResult      # cả hai = 0
```

Điều kiện đạt cuối cùng: `data/last_signals.json` vẫn giữ đúng confluence của 3 mã như trước refactor (BTC `SHORT BIAS`, ETH `NEUTRAL`, PAXG `STRONG LONG`) và **không** có alert "Trạng thái ban đầu" nào bị bắn lại.
