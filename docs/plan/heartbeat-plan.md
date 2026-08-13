# Phân biệt "không có tín hiệu" với "hệ thống đã chết"

**Trạng thái: BRAINSTORM. Chưa chốt, chưa code.** Cuối file có 5 câu cần quyết.

Nhánh `feat/heartbeat`.

## Vấn đề

Điện thoại im lặng hôm nay nghĩa là gì?

- Thị trường không có gì đáng báo → **bình thường**
- Laptop đã gập, đã ngủ, mất wifi, Binance chặn IP, tiến trình chết lúc 3h sáng → **hỏng**

**Hai thứ này hiện trông y hệt nhau.** Đó là lỗi thiết kế nguy hiểm nhất của cả hệ thống,
vì nó hỏng đúng lúc ông tin tưởng nhất — ông đang chờ tín hiệu, và im lặng được diễn giải
thành "chưa có gì".

Tệ hơn: **web vẫn hiện số liệu cũ trông như số liệu sống.** Thẻ giá vẫn đó, con số vẫn
đẹp, không có gì nói rằng chúng là của tuần trước.

## Nghịch lý cốt lõi

> Thứ chạy trên máy không thể báo cho ông biết khi máy tắt.

Mọi giải pháp nội bộ đều vấp phải điều này. Nên phải chia làm hai tầng, và tầng ngoài
mới là tầng thật sự giải quyết vấn đề.

---

## Ba lớp, từ rẻ tới chắc

### Lớp 1 — Băng cảnh báo dữ liệu cũ (trong máy)

Dashboard so `last_scan_at` với hiện tại. Quá `N × SCAN_INTERVAL` thì hiện băng đỏ:
*"Số liệu từ 3 giờ trước, vòng quét đã dừng."*

Rẻ, làm trong một buổi. Nhưng **chỉ cứu người đang mở trang** — không cứu ông lúc đang
chờ tin nhắn.

Cùng lớp này: nếu một task nền chết âm thầm (`scan_loop` bị huỷ mà không ai biết), tự
phát hiện và bật lại. Hiện `scheduler.stop()` xoá `_tasks`, nhưng task chết vì lý do
khác thì **không ai kiểm tra**.

### Lớp 2 — Tin nhắn nhịp tim hằng ngày (trong máy)

Bot nhắn một tin tóm tắt vào giờ cố định: giá 3 mã, confluence hiện tại, số tín hiệu
trong ngày, uptime.

Giá trị **không nằm ở nội dung tin nhắn** — mà ở chỗ **thiếu nó**. 8h sáng không thấy
tin là biết có chuyện, không cần đọc gì cả.

Vẫn dính nghịch lý ở trên: máy chết thì tin không gửi được. Nhưng đúng khi đó sự vắng
mặt lại là tín hiệu. Yếu điểm thật: **ông phải nhớ rằng mình đáng lẽ nhận được tin** —
dựa vào trí nhớ con người, không đáng tin bằng lớp 3.

### Lớp 3 — Người canh từ bên ngoài ⭐

Thứ duy nhất thật sự đóng được lỗ hổng: một cái gì đó **không nằm trên máy này** định kỳ
gọi `/healthz`, im lặng quá lâu thì la lên.

Điểm hay: **`GET /healthz` đã sẵn sàng cho việc này rồi.** Nó nằm trong `PUBLIC_PATHS`
nên không cần đăng nhập, và đã có test canh nó không lộ dữ liệu gì
(`test_healthz_khong_lo_gi_nhay_cam`). Không phải mở thêm cửa nào.

Ba lựa chọn cho người canh:

| | Ưu | Nhược |
|---|---|---|
| **GitHub Actions theo lịch** | Không tài khoản mới, dùng luôn repo sẵn có | Ăn vào quota Actions của repo private — phải tính (xem bên dưới) |
| Dịch vụ ping miễn phí | Đúng nghề, có app báo | Thêm một tài khoản, thêm một bên biết URL của ông |
| Một máy khác của ông | Toàn quyền | Phải có máy chạy 24/7 — quay lại đúng bài toán ban đầu |

**Tính quota GitHub Actions** (repo private, gói free 2000 phút/tháng): mỗi lần chạy chỉ
mất vài giây nhưng **bị làm tròn lên 1 phút**.

```
30 phút/lần → 48 lần/ngày → ~1.440 phút/tháng   ← ăn 72% quota, rủi ro
60 phút/lần → 24 lần/ngày →   ~720 phút/tháng   ← an toàn
```

Nghiêng về **60 phút/lần**. Phát hiện chậm nhất một tiếng, chấp nhận được cho việc này.

**Báo cho ai, bằng đường nào?** Máy đã chết thì bot trên máy không nhắn được, nên người
canh phải có kênh riêng:

- **Mở issue trên GitHub** — không cần secret nào, ông nhận email tự động. Đơn giản nhất.
- **Nhắn Telegram thẳng từ Actions** — báo ngay lên điện thoại, nhưng phải cất bot token
  thành repo secret. Thêm một nơi giữ secret là thêm một chỗ để rò.

Nghiêng về **mở issue**: chậm hơn vài phút nhưng không phải nhân bản token đi đâu cả.

---

## Rủi ro và cạm bẫy

**Báo động giả làm hỏng mọi thứ.** Wifi chập một nhịp mà đã la làng thì vài hôm ông tắt
thông báo, và lúc đó hệ thống cảnh báo thành vô dụng — tệ hơn là không có, vì ông tưởng
mình đang được canh. Bắt buộc: **phải hỏng liên tiếp N lần mới báo**, và **chỉ báo một
lần** cho tới khi sống lại. Đúng tinh thần debounce của vòng quét tín hiệu.

**Phải báo cả lúc hồi phục.** Chỉ báo lúc chết là ông không biết khi nào yên tâm lại được.

**`/off` không được tính là chết.** Ông chủ động cho server nghỉ thì người canh phải im.
Nhưng `/off` vẫn giữ uvicorn chạy nên `/healthz` vẫn trả lời — cần trả thêm trạng thái
nghỉ để bên ngoài phân biệt được, mà **vẫn không lộ dữ liệu gì**. Có test canh chuyện
không lộ, phải giữ nó xanh.

**Đừng để chính hệ thống cảnh báo thành thứ cần được cảnh báo.** Giữ lớp 3 càng ngu càng
tốt: gọi HTTP, so kết quả, hết. Không logic, không trạng thái, không phụ thuộc.

---

## Cần quyết trước khi viết spec

1. **Làm cả ba lớp, hay chỉ lớp 1 + 3?** Lớp 2 (tin hằng ngày) có thể thừa nếu đã có lớp 3.
2. **Người canh bên ngoài: GitHub Actions, dịch vụ ping, hay chưa làm?**
3. **Nếu Actions: mở issue hay nhắn Telegram** (phải cất token thành secret)?
4. **Bao nhiêu lần hỏng liên tiếp thì báo?** (đề xuất 2–3, tức 2–3 tiếng nếu ping mỗi giờ)
5. **Tin hằng ngày gửi lúc mấy giờ**, và có gửi cả những ngày không có tín hiệu nào không?
   (Có — đó mới là ngày cần biết hệ thống còn sống.)

## Ngoài phạm vi

Không đụng `engine/`, không đổi logic tín hiệu. Không làm watchdog khởi động lại server
sau khi crash — đó là **ưu tiên 3** riêng, giải bài toán khác (tự hồi phục, chứ không
phải tự báo). Hai việc bổ trợ nhau nhưng đừng gộp: cái này lo *biết*, cái kia lo *chữa*.
