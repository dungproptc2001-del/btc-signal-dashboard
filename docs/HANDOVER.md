# Bàn giao — trạng thái dự án

Cập nhật 13/08/2026. Đọc file này trước khi làm tiếp.

Tài liệu sống: [README](../README.md) · [ARCHITECTURE](ARCHITECTURE.md) ·
[structure.html](structure.html). Còn `plan/` và `spec/` là **hồ sơ theo từng đợt**,
ghi lại lúc đó đã quyết gì và vì sao — không sửa lại cho khớp hiện tại.

---

## Đang có gì

Một process `python -m apps.server` lo cả ba việc: phục vụ web, quét tín hiệu 15 phút,
dựng báo cáo 4 tiếng. Tự host trên laptop, mở ra internet, người lạ phải xin quyền.

| | |
|---|---|
| Repo | `dungproptc2001-del/btc-signal-dashboard` — **private** |
| Link công khai | `https://laptop-28esvi13.tail5ac7f7.ts.net` — **cố định** |
| Trong máy | `http://localhost:8000` — vào thẳng, không cần đăng nhập |
| Tự bật | Task Scheduler `BTC Web Server`, trigger AtLogOn |
| Desktop | 5 shortcut: Bật · Tắt · Trạng thái · Dashboard · Link công khai |
| Test | 340, chạy offline trên fixture đóng băng |
| Ranh giới 6 tầng | 0 vi phạm (quét AST) |
| Người canh | GitHub Actions gọi `/healthz` mỗi giờ, hỏng 3 lượt thì mở issue |

Nhánh:

```
main             eb723c1   ← đã có chấm điểm tín hiệu
feat/heartbeat             ← biết khi hệ thống chết
```

---

## Sáu đợt đã làm

### 1. Refactor — tách tầng

Từ một file `btc_report.py` thành `sources → engine → service → {web, notify, server} → apps`.
`engine/` thuần tính toán: không I/O, không HTML, không biết web tồn tại. Ranh giới được
kiểm **bằng máy** (quét AST), không bằng lời hứa.

Đúng đắn được bảo chứng bằng **golden file**: đóng băng response Binance vào
`tests/fixtures/`, chạy code cũ lưu kết quả vào `tests/golden/`, refactor xong phải khớp
số liệu ở `rel=1e-9` và text Telegram byte-for-byte.

Hồ sơ: [plan](plan/refactor-plan.md) · [spec](spec/refactor-spec.md)

### 2. Deploy web + duyệt truy cập qua Telegram

Người lạ mở link → để lại tên + lời nhắn → chủ nhà nhận Telegram kèm hai nút → bấm Duyệt
→ khách vào thẳng. Quyền 7 ngày, thu hồi bất kỳ lúc nào.

Hồ sơ: [plan](plan/web-deploy-plan.md) · [spec](spec/web-deploy-spec.md)

### 3. Link cố định + bật/tắt từ Telegram

Đổi từ Cloudflare quick tunnel (URL đổi mỗi lần chạy) sang Tailscale Funnel (URL cố định).
Thêm `/off` `/on` không giết tiến trình.

Hồ sơ: [plan](plan/telegram-power-plan.md) · [spec](spec/telegram-power-spec.md)

---

## Bốn thứ phải biết trước khi sửa

**Mọi tunnel đều là bẫy quyền.** Tunnel proxy vào server nên request từ internet có thể
mang danh nghĩa loopback — mà loopback thì code coi là chủ nhà. `_is_owner_request()`
chặn hai lớp: thấy header proxy là loại ngay, *rồi* mới xét loopback. Đã đo thật:
Tailscale cho `client.host = 100.x.y.z` + `x-forwarded-for` (cả hai lớp đỡ), Cloudflare
cho `127.0.0.1` + `cf-connecting-ip` (chỉ lớp header đỡ). **Đổi provider là phải đo lại.**

**Funnel bơm `tailscale-user-login` vào mọi request kể cả người lạ.** Trông y như danh
tính đã xác thực. Không phải. Có test canh để không ai lỡ dùng nó cấp quyền.

**Downtrend thuần không ra SHORT được.** RSI < 35 cộng +2 (thành phần mean-reversion)
triệt tiêu các thành phần giảm. Đây là hành vi cố ý, có test canh
(`test_rsi_oversold_bu_lai_downtrend`). Đừng "sửa" nó nếu chưa hiểu vì sao.

**Đừng chạy `apps.monitor` lúc server đang chạy.** Hai bên ghi đè `data/last_signals.json`
của nhau. Xoá file đó là vòng quét coi như chạy lần đầu, bắn lại alert "Trạng thái ban
đầu" cho cả ba mã.

---

## Việc còn treo

| Việc | Ghi chú |
|---|---|
| Ưu tiên 3: watchdog tự khởi động lại sau crash | Chưa có plan. Bài toán *chữa*, khác với đợt 5 lo *biết* |
| Chưa đo chu kỳ ngủ/thức thật của Windows | Long-poll có sống sót không. Chỉ ảnh hưởng cờ `--sleep-on-off`, không ảnh hưởng mặc định |
| Task cũ `BTC 4H Report` | Cần quyền admin để dọn: `schtasks /delete /tn "BTC 4H Report" /f`. Nó trỏ vào file đã xoá nên chỉ fail vô hại |
| `OWNER_KEY` chưa cố định trong `.env` | Đặt cố định thì có bookmark vĩnh viễn tự đăng nhập. Đổi lại là mật khẩu nằm trong URL |
| Report và monitor cho confluence khác nhau | Report lấy 26 nến tuần, monitor lấy 52 → verdict khung 1W lệch. Có từ trước refactor, chưa thống nhất |

### 4. Nhật ký tín hiệu lên web

Tín hiệu mua/bán bắn xuống Telegram giờ cũng được ghi vào `data/signals.jsonl` và hiện
trên trang chủ, kèm giá lúc bắn và mốc thị trường thật sự đổi.

Hồ sơ: [plan](plan/signal-feed-plan.md) · [spec](spec/signal-feed-spec.md)

### 5. Chấm điểm tín hiệu

Hệ thống bắn tín hiệu từ đầu mà chưa bao giờ tự chấm điểm. Giờ mỗi tín hiệu được đối
chiếu với giá thật: chạm TP trước hay SL trước, quy ra R. Kèm một đổi hành vi thật —
**SL/TP tính theo hướng confluence** thay vì verdict khung 4H, vì hai cái đã lệch nhau
thật và tín hiệu `BIAS` từng đi Telegram mà không kèm mức nào.

Hồ sơ: [plan](plan/signal-outcome-plan.md) · [spec](spec/signal-outcome-spec.md)

### 6. Biết khi hệ thống chết

Trước đợt này, "thị trường im" và "laptop đã gập" trông y hệt nhau. Giờ `/healthz` nói
được ba trạng thái, dashboard hiện băng đỏ khi số liệu quá 45 phút, nhịp nền chết âm thầm
thì tự dựng lại — và **GitHub Actions gọi từ bên ngoài mỗi giờ**, vì thứ chạy trên máy
không thể báo cho ông biết khi máy tắt.

Hồ sơ: [plan](plan/heartbeat-plan.md) · [spec](spec/heartbeat-spec.md)

---

## Quy ước làm việc

- **Đang ở `main` thì tách nhánh trước khi commit**, không chờ được nhắc
- **Hỏi trước khi push**, kể cả khi test đã xanh
- Plan → chủ dự án duyệt → viết spec → thực thi
- Đo thật rồi mới kết luận. Không đọc doc của bên thứ ba rồi tin, nhất là ở ranh giới quyền
- Trao đổi bằng tiếng Việt
