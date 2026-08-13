# Spec — Phân biệt "không có tín hiệu" với "hệ thống đã chết"

Chốt từ [plan](../plan/heartbeat-plan.md). Nhánh `feat/heartbeat`.

## Bảy quyết định

| # | Câu | Chốt |
|---|---|---|
| 1 | Làm mấy lớp | **Lớp 1 + lớp 3. Bỏ lớp 2** (tin nhịp tim hằng ngày) |
| 2 | Người canh bên ngoài | **GitHub Actions theo lịch**, mỗi 60 phút |
| 3 | Báo bằng đường nào | **Mở issue trên GitHub**, không mang bot token đi đâu |
| 4 | Ngưỡng báo động | **3 lần hỏng liên tiếp** (~3 tiếng) |
| 5 | `/off` phân biệt thế nào | **Thêm trường trạng thái vào `/healthz`**, không đổi mã HTTP |
| 6 | Băng cảnh báo tính ở đâu | **Server quyết định ngưỡng**, client chỉ đếm tiếp |
| 7 | Task nền chết âm thầm | **Tự hồi sinh + báo Telegram**, không im lặng |

### Vì sao bỏ lớp 2

Tin nhịp tim hằng ngày có giá trị **không nằm ở nội dung mà ở chỗ thiếu nó** — 8h sáng
không thấy tin là biết có chuyện. Nhưng cơ chế phát hiện là **trí nhớ con người**, và
lớp 3 đã canh hộ việc đó bằng máy, mỗi giờ, không quên. Thêm lớp 2 chỉ tăng số tin nhắn
mỗi ngày; mà tin nhắn thừa chính là thứ làm người ta ngừng đọc tin nhắn.

Bỏ được thì bỏ. Cần thì thêm sau, nó không phụ thuộc gì hai lớp kia.

---

## Lớp 1a — `/healthz` nói được ba trạng thái

Hiện tại `/healthz` trả:

```json
{"ok": true, "uptime_seconds": 12345, "paused": false}
```

Không phân biệt được **"đang chạy"** với **"uvicorn sống nhưng vòng quét đã chết"** —
mà đó đúng là kiểu hỏng câm nguy hiểm nhất: web vẫn 200, thẻ giá vẫn đó, số liệu là của
tuần trước.

Trả thêm:

| Trường | Nghĩa |
|---|---|
| `standby` | Ông chủ động `/off`. **Người canh phải im.** |
| `stale` | Vòng quét quá hạn. Server sống mà không quét nữa → **phải báo động** |
| `scan_age_seconds` | Bao lâu rồi kể từ lượt quét cuối. `null` khi chưa quét lần nào |
| `stale_after` | Ngưỡng đang dùng, giây. Có nó thì bên ngoài không phải đoán |
| `last_scan_at` | Mốc quét cuối, giờ địa phương |

### Ngưỡng

```
STALE_AFTER = 3 × SCAN_INTERVAL = 45 phút
```

Ba nhịp quét. Một nhịp lỡ là chuyện thường (Binance nghẽn, wifi chập); ba nhịp liên tiếp
không quét được thì có chuyện thật.

### `stale` KHÔNG bật khi `paused` hoặc `standby`

Hai cái đó là ông chủ động cho nghỉ. Bật `stale` lúc đó là tự tạo báo động giả cho chính
mình — mà báo động giả là thứ giết cả hệ thống cảnh báo.

### Không được lộ thêm gì

`test_healthz_khong_lo_gi_nhay_cam` kiểm chuỗi `"token"`, `"symbols"`, `"price"` không
xuất hiện trong body. **Đây là lý do không thêm `last_price_at`** — tên trường chứa chữ
`price`, thêm vào là test đỏ. Mà test đỏ ở đây là đúng: `/healthz` công khai, mỗi trường
thêm vào là một thứ người lạ đọc được.

Mốc thời gian quét thì cho ra được: nó nói *hệ thống còn sống không*, không nói *thị
trường đang thế nào*.

---

## Lớp 1b — Task nền chết âm thầm thì tự hồi sinh

`scheduler.start()` tạo 4 task rồi thả. `stop()` xoá `_tasks`. **Task chết vì lý do khác
thì không ai kiểm tra.** Mỗi vòng đã bọc `try/except` bên trong nên phần lớn lỗi không
giết được nó — nhưng `MemoryError`, `KeyboardInterrupt` trong threadpool, hay một lỗi
ngay tại `asyncio.sleep` thì vẫn thoát ra được, và lúc đó nhịp đó chết vĩnh viễn trong
khi web vẫn phục vụ bình thường.

Thêm nhịp thứ năm, **`watch_loop`**, mỗi 60 giây:

1. Duyệt các task đang giữ. Task nào `done()` mà không phải do bị huỷ → **lỗi thật**.
2. Ghi log kèm traceback, tạo lại task đó, tăng `STATE.task_restarts`.
3. **Gửi Telegram một tin** cho mỗi lần hồi sinh: nhịp nào, lỗi gì.

Báo Telegram ở đây không phải cảnh báo thừa: một nhịp chết là chuyện chưa từng xảy ra
trong đời dự án này. Nếu nó xảy ra thật thì đó là thông tin đắt, không phải nhiễu.

**Giới hạn tự biết:** `watch_loop` không tự hồi sinh được chính nó. Thân vòng bọc
`try/except` để không bao giờ thoát; nhưng nếu nó chết thì lớp 3 mới là thứ bắt được —
vì `stale` sẽ bật khi `scan_loop` chết mà không ai dựng lại. Hai lớp đỡ nhau đúng chỗ này.

---

## Lớp 1c — Băng cảnh báo trên dashboard

Băng đỏ trên đầu trang khi `stale`:

> ⚠️ **Số liệu đã cũ** — vòng quét dừng từ 1 giờ 12 phút trước. Những con số dưới đây
> không còn là hiện tại.

Đã có sẵn `standby-banner` (vàng, "đang nghỉ") — băng mới là **đỏ** và ưu tiên cao hơn,
vì standby là chủ động còn stale là hỏng.

### Server giữ luật, client chỉ đếm tiếp

`public()["status"]` trả `stale`, `scan_age_seconds`, `stale_after`. Client **không tự
đặt ngưỡng** — nó lấy `stale_after` của server. Cùng lý do đã ghi ở chỗ ẩn tỷ lệ thắng:
luật nằm trong giao diện thì nó biến mất lần đầu ai đó sửa giao diện.

### Client phải đếm bằng số giây, KHÔNG parse mốc tuyệt đối

`last_scan_at` là `datetime.now().isoformat()` — giờ địa phương, **không kèm offset**.
`new Date("2026-08-13T11:05:13")` trong trình duyệt hiểu là giờ *của người xem*. Khách
xem từ múi giờ khác sẽ thấy băng đỏ vĩnh viễn dù hệ thống hoàn toàn khoẻ.

Nên client làm thế này:

```
lúc nhận payload:  t0 = Date.now(),  age0 = payload.scan_age_seconds
mỗi giây:          age = age0 + (Date.now() - t0)/1000
                   stale khi age > payload.stale_after
```

Không parse mốc tuyệt đối một lần nào → không có múi giờ nào để sai.

**Sửa kèm:** `st-next` (đếm ngược tới lượt quét sau) đang dính đúng lỗi này —
`new Date(s.last_scan_at)`. Khách nước ngoài thấy đếm ngược sai hàng tiếng. Chuyển sang
`scan_interval - age` theo cùng cách trên. Hai dòng, cùng một lỗi, sửa luôn.

### Mất kết nối là chuyện khác, đã có sẵn

Server chết hẳn thì SSE đứt, `setLive(false)` đổi chấm sang "mất kết nối". Cái đó **đã
có** và không đụng tới. Băng stale lo trường hợp ngược lại: kết nối còn tốt, chỉ dữ liệu
là chết.

---

## Lớp 3 — Người canh từ bên ngoài

`.github/workflows/watchdog.yml`, chạy trên GitHub chứ không trên máy này. Đây là lớp
duy nhất còn nói được khi laptop đã tắt.

### Lịch và quota

```
cron '17 * * * *'   → mỗi giờ, lệch 17 phút để tránh giờ cao điểm của GitHub
24 lần/ngày × 30 = 720 lần/tháng
mỗi lần vài giây nhưng BỊ LÀM TRÒN LÊN 1 PHÚT → ~720 phút/tháng
```

Gói free repo private có 2000 phút. Ăn 36%, an toàn. Ping 30 phút/lần sẽ là ~1440 phút
(72%) — quá sát, không làm.

Mỗi lần chạy **phải ở dưới 1 phút**. Đó là lý do không thử lại nhiều lần trong cùng một
lượt: thử 2 lần cách nhau 10 giây để lọc chập nhất thời, hết.

### Sống hay chết, quyết thế nào

| Kết quả gọi `/healthz` | Kết luận |
|---|---|
| HTTP 200, `ok:true`, `stale:false` | **Sống** |
| HTTP 200, `standby:true` | **Sống** — ông chủ động cho nghỉ, im lặng |
| HTTP 200, `stale:true` | **HỎNG** — server sống mà vòng quét đã chết |
| Không nối được / timeout / mã khác 200 | **HỎNG** |

Dòng thứ ba là dòng đắt nhất của cả spec: đó là kiểu hỏng mà mọi dịch vụ ping thương mại
đều báo "khoẻ".

### Đếm 3 lần liên tiếp mà không cần lưu trạng thái

Không có chỗ nào để nhớ bộ đếm giữa các lượt chạy — Actions cache thì hết hạn, ghi file
vào repo thì bẩn lịch sử. Nên **dùng chính kết luận của các lượt chạy trước làm trạng
thái**:

```
ping hỏng → step thoát mã 1 → conclusion của lượt này = failure
   ↓ step `if: failure()`
   hỏi API: 2 lượt chạy hoàn tất gần nhất của workflow này có failure cả không?
      có  → đây là lần thứ 3 → MỞ ISSUE (nếu chưa có issue nào đang mở)
      chưa → im, để lần sau
```

Không thêm file, không thêm secret, không thêm phụ thuộc. Đúng tinh thần "giữ lớp 3
càng ngu càng tốt".

### Báo một lần, và báo cả lúc sống lại

- Trước khi mở issue: tìm issue đang mở có nhãn `watchdog`. Có rồi thì **không mở thêm**.
  Không có luật này thì hỏng qua đêm là sáng ra 8 cái issue.
- Ping thành công mà đang có issue `watchdog` mở → **bình luận mốc sống lại rồi đóng
  issue**. Chỉ báo lúc chết là không bao giờ biết khi nào yên tâm lại được.

### Quyền và bí mật

```yaml
permissions:
  issues: write
  contents: read
```

`GITHUB_TOKEN` tự có sẵn. **Không cần secret nào.** Đó là toàn bộ lý do chọn issue thay
vì Telegram: bot token vẫn nằm đúng một chỗ là máy này.

URL công khai cất trong **repo variable `HEALTH_URL`** (không phải secret — nó không bí
mật, chỉ là không nên nằm trong lịch sử git nếu repo có ngày mở ra).

---

## Việc phải làm

| # | Bước | Xong khi |
|---|---|---|
| 1 | `config.py`: `STALE_AFTER_SCANS`, `TASK_WATCH_INTERVAL` | — |
| 2 | `state.py`: `stale`, `scan_age_seconds`, `stale_after`, `task_restarts` vào `public()` | Test: paused/standby thì `stale` tắt |
| 3 | `app.py`: `/healthz` trả thêm 5 trường | Test cũ `khong_lo_gi_nhay_cam` vẫn xanh |
| 4 | `scheduler.py`: `watch_loop` hồi sinh task chết + báo Telegram | Test: giết task, 1 nhịp sau nó sống lại |
| 5 | `dashboard.*`: băng đỏ + sửa đếm ngược theo `scan_age_seconds` | Không còn chỗ nào `new Date(last_scan_at)` |
| 6 | `.github/workflows/watchdog.yml` | Chạy tay bằng `workflow_dispatch` thấy xanh |
| 7 | Đặt `HEALTH_URL`, chạy thử cả nhánh hỏng lẫn nhánh sống lại | — |
| 8 | README · ARCHITECTURE · structure.html · HANDOVER | Sơ đồ khớp code, quét AST 0 vi phạm |

## Nghiệm thu

```powershell
python -m pytest tests -q                       # 321 test cũ + test mới, tất cả xanh

# /healthz nói đủ ba trạng thái
curl -s localhost:8000/healthz                  # stale:false, standby:false
#   /off từ Telegram  → standby:true
#   sửa tay STATE.last_scan_at lùi 1 tiếng → stale:true

# Người canh
gh workflow run watchdog.yml                    # chạy tay, phải xanh
#   đổi HEALTH_URL sang cổng chết → chạy 3 lần → lượt 3 mở issue, lượt 1-2 im
#   trả HEALTH_URL về → lượt sau đóng issue kèm bình luận

# Băng cảnh báo
#   dừng scan_loop bằng tay → sau 45 phút băng đỏ hiện, đếm đúng số phút
```

## Rủi ro đã biết

**GitHub tự tắt workflow theo lịch nếu repo im lặng 60 ngày.** Đây chính là cái bẫy
"hệ thống cảnh báo thành thứ cần được cảnh báo" — nó tắt lặng lẽ, không báo ai. Repo này
đang được commit đều nên chưa chạm ngưỡng, nhưng phải biết mà canh.

**Lịch của GitHub Actions không đúng giờ.** Lúc cao điểm có thể trễ 5–20 phút. Ảnh hưởng
thời điểm phát hiện, không ảnh hưởng đúng/sai.

**Chạy tay `workflow_dispatch` lẫn vào bộ đếm** 3 lượt liên tiếp. Chạy tay lúc server
đang hỏng sẽ đẩy bộ đếm nhanh hơn thật. Chấp nhận được — nó chỉ làm báo sớm hơn.

**Ping mỗi giờ nghĩa là biết chậm nhất 3 tiếng.** Đây là cái giá đã chọn để đổi lấy quota
an toàn và không báo động giả. Muốn nhanh hơn thì trả bằng một trong hai thứ đó.

## Ngoài phạm vi

Không đụng `engine/`, `sources/`, `notify/`, `web/`. Không đổi công thức tín hiệu hay
chu kỳ quét. **Không làm watchdog tự khởi động lại server sau khi crash** — đó là ưu tiên
3, bài toán *chữa*, còn cái này lo *biết*.
