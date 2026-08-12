# Refactor bitcoin-report: tách engine / frontend, dựng lại cấu trúc folder

## Context

Toàn bộ project đang nằm trong 2 file phẳng: [btc_report.py](e:/bitcoin-report/btc_report.py) 1142 dòng và [signal_monitor.py](e:/bitcoin-report/signal_monitor.py) 250 dòng. Vấn đề cụ thể:

| Triệu chứng | Số đo |
|---|---|
| `build_html()` ôm cả tính toán lẫn trình bày | 639 dòng (398–1036), trong đó ~190 dòng đầu là logic |
| CSS + JS nhúng thẳng trong f-string Python | 41 dòng CSS, 177 dòng JS, không syntax-highlight được |
| Escape `{{ }}` do f-string | **272 chỗ** |
| Logic confluence bị copy 3 bản | `build_html` (464–468), `main()` (924–928), `signal_monitor._confluence()` |
| Chuỗi HTML build thủ công trong Python | `risk_html`, `reasons_html`, `_tf_card_html` |
| 21 mảng dữ liệu chart nhét vào JS bằng 21 placeholder rời | `{label_str}`, `{close_str}`, … |

Mục tiêu: engine tính toán thuần Python trả về **một context dict**, renderer nhận dict đó đổ ra HTML. Hai tầng không biết gì về nhau. Frontend về đúng đuôi file `.html/.css/.js`. Output vẫn là **một file HTML tự chứa**, double-click chạy được như hiện tại — không đổi cách dùng.

Đã chốt: static generator · Jinja2 · package + apps · pytest.

---

## Cấu trúc đích

```
bitcoin-report/
├─ btcreport/                    # thư viện — không có entrypoint
│  ├─ config.py                  # env loader, đường dẫn, hằng số, SYMBOLS
│  ├─ sources/                   # tầng I/O vào
│  │  ├─ http.py                 # _get_json: retry/backoff/Retry-After
│  │  ├─ binance.py              # _parse_klines, fetch_klines(_range), fetch_ticker
│  │  └─ feargreed.py
│  ├─ engine/                    # thuần tính toán — KHÔNG import requests
│  │  ├─ indicators.py           # sma ema rsi macd_line bollinger atr
│  │  ├─ signals.py              # generate_signal, confluence  ← gộp 3 bản trùng
│  │  ├─ levels.py               # support_resistance, risk_levels
│  │  └─ analysis.py             # analyze_timeframe, build_context, get_thu_range
│  ├─ notify/                    # tầng I/O ra
│  │  ├─ telegram.py             # send_telegram
│  │  └─ messages.py             # soạn text report + text alert
│  └─ web/                       # tầng trình bày
│     ├─ renderer.py             # render_report(context) -> str
│     ├─ filters.py              # Jinja filter: usd, pct, signed, icon
│     ├─ templates/report.html
│     └─ static/{styles.css, charts.js}
├─ apps/
│  ├─ report.py                  # entry: python -m apps.report
│  └─ monitor.py                 # entry: python -m apps.monitor
├─ scripts/                      # run_report.bat, run_monitor.bat,
│                                # stop_monitor.bat, setup_tasks.ps1
├─ data/                         # runtime: last_signals.json, monitor.pid, *.log
├─ output/                       # btc_report.html
├─ tests/                        # pytest + fixtures/
├─ .env  .env.example  .gitignore  requirements.txt  requirements-dev.txt
```

Entrypoint gọi bằng `python -m apps.report` từ thư mục gốc — không phải nghịch `sys.path` như [signal_monitor.py:10](e:/bitcoin-report/signal_monitor.py#L10) đang làm.

---

## Ranh giới hai tầng

**Engine** nhận nến, trả context dict thuần (số, chuỗi, list) — không có một ký tự HTML nào:

```python
{
  "generated_at": datetime, "symbol": "BTCUSDT",
  "price": {"last": 63739.24, "change_24h": -1.82, "high": ..., "low": ...},
  "fear_greed": {"value": 27, "label": "Fear"},
  "week": {"start": date, "end": date, "open": ..., "close": ..., "change": ...},
  "signal": {"verdict": "SHORT", "action": "BÁN / SHORT", "score": -3,
             "max_score": 7, "confidence": 49, "reasons": [str, ...]},
  "timeframes": [{"label": "1W", "verdict": ..., "score": ..., "rsi": ...,
                  "macd_bull": bool}, ...],
  "confluence": {"verdict": "SHORT BIAS", "agree": 2},
  "levels": {"pivot":…, "R1":…, "R2":…, "S1":…, "S2":…},
  "risk": {"entry":…, "sl":…, "tp":…, "atr":…, "rr":…},   # sl/tp = None nếu NEUTRAL
  "chart": {"daily": {...}, "h4": {...}, "h1": {...}},     # gộp 21 mảng thành 1 nhánh
}
```

**Màu sắc chuyển hẳn sang frontend.** Hiện `generate_signal` trả cả `"#00c853"` — mã màu là việc của CSS. Engine chỉ trả `verdict`, template map verdict → class (`.pill-green` / `.pill-red` / `.pill-yellow`). Đây là chỗ trộn tầng nặng nhất trong code hiện tại.

**Renderer** nhận context, không tính toán gì. Jinja2 bật `autoescape=True`. Số liệu định dạng bằng Jinja filter (`{{ price.last | usd }}`) chứ không f-string sẵn trong Python. 21 mảng chart gộp thành `{{ chart | tojson }}` — một dòng, thay cho 21 placeholder.

**Vẫn xuất một file tự chứa**: `renderer.py` đọc `static/styles.css` + `static/charts.js` rồi inline vào lúc render. Chart.js vẫn lấy từ CDN như hiện tại.

---

## Bảng chuyển đổi

| Hiện tại | Đích |
|---|---|
| `btc_report.py` 13–60 (config, `_load_dotenv`) | `btcreport/config.py` |
| `_get_json` (64) | `sources/http.py` |
| `_parse_klines`, `fetch_klines*`, `fetch_ticker` | `sources/binance.py` |
| `fetch_fear_greed` | `sources/feargreed.py` |
| `send_telegram` | `notify/telegram.py` |
| `sma ema rsi macd_line bollinger atr` | `engine/indicators.py` |
| `generate_signal` + 3 bản confluence | `engine/signals.py` (một hàm `confluence()`) |
| `support_resistance`, `risk_levels` | `engine/levels.py` |
| `_compute_tf`, `get_thu_range`, phần tính của `build_html` (398–590) | `engine/analysis.py` |
| `build_html` phần template (591–1036) | `web/templates/report.html` + `static/` |
| `_tf_card_html`, `risk_html`, `reasons_html` | Jinja macro / vòng lặp trong template |
| `tg_msg` trong `main()`, `build_alert()` trong monitor | `notify/messages.py` |
| `main()` của btc_report | `apps/report.py` |
| `signal_monitor.py` (state, pid, scan loop) | `apps/monitor.py` |

Ba bug sửa luôn khi đi qua:
1. `&#₿;` ở dòng 645 — entity HTML không hợp lệ, browser in ra chữ thô. Đổi thành `&#8383;`.
2. `generate_signal` nhận `rsi_vals/macd_val/sig_full` do caller tính sẵn rồi truyền vào — mỗi caller phải nhớ tính đúng thứ tự. Đổi thành nhận `candles`, tự tính bên trong.
3. Dọn import thừa (`json`, `math` trong btc_report).

---

## An toàn: chốt input trước khi động vào

Refactor kiểu này lệch một con số là không phát hiện được bằng mắt, mà giá thị trường thì thay đổi mỗi lần chạy nên không thể so trực tiếp output cũ/mới. Nên **bước đầu tiên là đóng băng input**:

1. Script `tests/capture_fixtures.py` gọi Binance một lần, lưu raw JSON vào `tests/fixtures/` (klines 1w/1d/4h/1h, ticker, fear&greed).
2. Chạy **code hiện tại** với fixtures đó → lưu `tests/golden/report.html` + `tests/golden/telegram.txt`.
3. Sau mỗi bước refactor, render lại từ fixtures và diff với golden.

HTML sẽ khác về mặt markup (đó là mục đích), nên golden dùng để so **số liệu**: một `tests/golden/context.json` dump toàn bộ context dict là thứ phải khớp tuyệt đối. Telegram text thì phải khớp byte-for-byte.

Test bằng pytest:

| File | Kiểm |
|---|---|
| `test_indicators.py` | sma/ema/rsi/macd/bollinger/atr trên chuỗi số biết trước kết quả |
| `test_signals.py` | Từng thành phần điểm; biên `\|score\| >= 3`; map confluence 4 khung |
| `test_levels.py` | support_resistance; risk_levels hướng LONG/SHORT; NEUTRAL trả `sl=None` |
| `test_context.py` | context dict từ fixtures khớp `golden/context.json` |
| `test_messages.py` | Text Telegram khớp golden |
| `test_render.py` | Render không lỗi, HTML chứa các mốc bắt buộc, không sót placeholder |

`pytest` vào `requirements-dev.txt`, tách khỏi `requirements.txt` (runtime vẫn chỉ `requests` + `jinja2`).

---

## Thứ tự thực hiện

| # | Bước | Kiểm tra xong |
|---|---|---|
| 1 | Dừng monitor đang chạy (PID hiện tại), chụp fixtures + golden | `tests/golden/` có đủ 3 file |
| 2 | Dựng khung package, chuyển `engine/` (thuần, dễ nhất, không I/O) | `pytest tests/test_indicators.py test_signals.py test_levels.py` xanh |
| 3 | Chuyển `sources/` + `notify/telegram.py` | Fetch thật ra đúng số nến |
| 4 | Viết `engine/analysis.py` → context dict, so với golden | `test_context.py` xanh |
| 5 | Tách frontend: template + CSS + JS, viết `renderer.py` | `test_render.py` xanh, mở HTML bằng mắt xem đủ chart |
| 6 | `notify/messages.py` + `apps/report.py` + `apps/monitor.py` | `python -m apps.report` chạy thật ra file |
| 7 | Chuyển state/log sang `data/`, cập nhật `scripts/`, chạy lại `setup_tasks.ps1` | Cả 2 task `LastTaskResult: 0` |
| 8 | Xoá file cũ, cập nhật `.gitignore` + `requirements*.txt` | Folder gốc chỉ còn file cấu hình |

**Giữ nguyên nội dung `last_signals.json`** khi chuyển sang `data/` — mất là monitor coi như chạy lần đầu và bắn lại alert cho cả 3 mã.

**Task Scheduler phải đăng ký lại**: action hiện trỏ `E:\bitcoin-report\run_report.bat`, sau refactor thành `E:\bitcoin-report\scripts\run_report.bat`. `setup_tasks.ps1` đã tự xoá task cũ trước khi tạo nên chạy lại là xong, nhưng phải nhớ chạy.

---

## Nghiệm thu

```powershell
# 1. Test tự động
cd E:\bitcoin-report; python -m pytest tests -q

# 2. Report chạy thật, không bung browser
python -m apps.report --no-browser
#    -> output/btc_report.html mới, Telegram nhận được tin

# 3. Mở HTML kiểm bằng mắt: 4 chart vẽ đủ, thẻ 4 khung, khối ATR,
#    không còn chuỗi "{" hay "&#₿;" lọt ra ngoài

# 4. Monitor một vòng quét
python -m apps.monitor      # Ctrl+C sau khi thấy đủ BTC/ETH/XAU

# 5. Đăng ký lại task rồi chạy thử cả hai
powershell -ExecutionPolicy Bypass -File .\scripts\setup_tasks.ps1
schtasks /run /tn "BTC Report 4H"
schtasks /run /tn "BTC Signal Monitor"
Get-ScheduledTaskInfo -TaskName 'BTC Report 4H','BTC Signal Monitor' |
    Select-Object TaskName, LastTaskResult      # phải là 0

# 6. Xác nhận monitor sống và ghi đúng chỗ mới
Get-Content data\monitor.pid
Get-Content data\last_signals.json -Encoding utf8
```

Chốt cuối: `data/last_signals.json` giữ nguyên 3 mã với confluence như trước khi refactor, không có alert "Trạng thái ban đầu" nào bị bắn lại.

---

## Ngoài phạm vi

Không đụng `E:\btc_strategy\` (task `BTC Strategy Signal` thuộc project khác). Không đổi công thức chỉ báo, ngưỡng tín hiệu, chu kỳ quét hay nội dung tin Telegram — refactor lần này **giữ nguyên hành vi**, chỉ đổi chỗ ở của code. Ngưỡng và tham số muốn chỉnh thì làm ở lần sau, khi đã có test giữ lưng.
