# Spec: bật / tắt server từ Telegram

Thực thi [plan](../plan/telegram-power-plan.md). Nhánh `feat/telegram-power-control`.

---

## `btcreport/server/power.py` (mới)

Tầng `server`. Được phép gọi `scheduler`, `tunnel`, `keepalive`, `state`.
**Không** được `bot` import ngược vào đây thành vòng — `bot` gọi `power`, không ngược lại.

```python
async def standby(reason="lệnh /off") -> dict
async def wake() -> dict
def status() -> dict          # {"standby": bool, "since": iso|None}
```

### `standby()`

Theo thứ tự — đóng đường ra ngoài trước, dừng việc sau:

1. `tunnel.stop()` — khách ngoài mất đường vào ngay lập tức
2. `scheduler.stop()` — huỷ 3 task nền
3. `keepalive.release()` **chỉ khi** `SLEEP_ON_OFF` bật
4. `STATE.standby = True`, `STATE.standby_since = now`
5. `STATE.publish("power", {...})` để tab đang mở đổi giao diện ngay

Uvicorn **vẫn chạy**. Bot **vẫn poll**. Đó là điểm mấu chốt của cả thiết kế: tiến trình
không chết thì luôn còn tai nghe để bật lại.

### `wake()`

Ngược thứ tự — dựng nền trước, mở đường ra ngoài sau:

1. `keepalive.hold()` (idempotent)
2. `scheduler.start()` — chạy ngay một lượt mỗi nhịp, không đợi hết chu kỳ
3. `tunnel.start(port)` — chạy trong threadpool, có thể mất vài giây
4. `STATE.standby = False`
5. Trả `{"url": ..., "url_changed": bool}` để bot biết có phải cảnh báo đổi link không

### Khoá chống gọi chồng

```python
_lock = asyncio.Lock()
```

Cả `standby()` và `wake()` cùng một khoá. Gọi `wake()` khi đang `wake()` thì cái thứ hai
chờ, thấy `STATE.standby is False` rồi trả về ngay — **không** gọi `scheduler.start()`
lần nữa. Không có khoá này thì `/on` bấm 3 lần đẻ ra 9 task nền, mỗi task một vòng quét
riêng, ghi đè `last_signals.json` của nhau.

`scheduler.start()` cũng tự bảo vệ: `if _tasks: return` trước khi tạo task mới.

---

## `btcreport/server/state.py`

```python
self.standby       = False
self.standby_since = None
```

Vào `public()["status"]`: `"standby"`, `"standby_since"`. Không phải secret — test
`test_public_state_khong_chua_secret` vẫn phải xanh.

---

## `btcreport/server/keepalive.py`

`hold()` thành idempotent:

```python
if _held:
    return True          # đã giữ rồi, không đăng ký atexit lần nữa
```

Hiện tại mỗi lần `hold()` là một lần `atexit.register(release)`. Gọi n lần thì n lần
đăng ký. Vô hại vì `release()` có chốt `_held`, nhưng `/on` `/off` lặp lại sẽ chất đống.

---

## `btcreport/server/bot.py`

### Lệnh mới

| Lệnh | Việc |
|---|---|
| `/off` | `power.standby()` → báo "đã nghỉ, link công khai đã đóng, /on để bật lại" |
| `/on` | `power.wake()` → báo link công khai; **cảnh báo nếu URL đổi** |

`HELP` cập nhật, nhóm lại theo mức: quét (`/pause` `/resume`) · dịch vụ (`/off` `/on`) ·
tiến trình (`/stop`).

### `/stop` phải xác nhận

Đây là lệnh duy nhất **không hoàn tác được từ điện thoại**. Bấm nhầm là phải mò về máy.

```
/stop → tin nhắn + 2 nút
        [ 🛑 Tắt hẳn ]  [ Huỷ ]
        callback_data: "halt:yes" / "halt:no"
```

Callback đi qua **đúng cửa kiểm `access.is_owner(chat_id)`** như nút duyệt khách. Không
kiểm là người lạ gửi đúng callback data để tắt server của ông.

`_handle_callback` hiện chỉ hiểu `approve:` / `deny:`; thêm nhánh `halt:` vào **sau**
cửa kiểm, không phải trước.

---

## `apps/server.py`

Cờ mới:

```
--sleep-on-off    /off nhả keep-alive luôn, máy được ngủ.
                  Đổi lại có lúc gõ /on không ai trả lời.
```

Đặt vào `config.SLEEP_ON_OFF` (mặc định `False`) để `power.py` đọc mà không phải truyền
tay qua nhiều tầng.

---

## Dashboard

Băng báo khi standby, đọc từ `STATE.public()["status"]["standby"]`, và cập nhật realtime
qua sự kiện SSE `power`. Không cần reload trang.

---

## Test

| File | Canh gì |
|---|---|
| `test_power.py` (mới) | `standby()` rồi `wake()` trả đúng trạng thái · `wake()` gọi 3 lần chỉ start scheduler 1 lần · `standby()` mặc định KHÔNG nhả keepalive · có `SLEEP_ON_OFF` thì có nhả · thứ tự: tunnel đóng trước scheduler |
| `test_api.py` | `public()` có `standby` và vẫn không chứa secret |
| `test_bot.py` (mới) | `/off` `/on` từ chat_id lạ bị chặn · callback `halt:yes` từ chat_id lạ bị chặn · `/stop` không tắt ngay mà hiện nút |

Test dùng monkeypatch cho `tunnel` / `scheduler` / `keepalive` — **không** mở tunnel
thật, không gọi mạng.

---

## Nghiệm thu trên server thật

```powershell
# 1. Standby
#    Telegram: /off
powercfg /requests                    # VẪN thấy python (mặc định giữ thức)
curl https://<link-cong-khai>/        # phải chết
curl http://localhost:8000/healthz    # vẫn sống

# 2. Bật lại
#    Telegram: /on   → link công khai phải Y HỆT URL cũ

# 3. Gọi chồng
#    Telegram: /on /on /on
#    → log chỉ được có MỘT dòng "Scheduler chạy"

# 4. Chu kỳ ngủ (đo, không đoán)
#    Cho máy ngủ 10 phút, đánh thức, gõ /status
```
