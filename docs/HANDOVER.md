# Bàn giao — trạng thái dự án

Cập nhật 12/08/2026. Đọc file này trước khi làm tiếp.

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
| Test | 233, chạy offline trên fixture đóng băng |
| Ranh giới 6 tầng | 0 vi phạm (quét AST) |

Nhánh:

```
main                          4035785   ← Tailscale funnel
feat/telegram-power-control   0bb12f3   ← /off /on, ĐÃ push, CHƯA gộp vào main
```

---

## Ba đợt đã làm

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
| Gộp `feat/telegram-power-control` vào `main` | Đã push, chưa gộp |
| Chưa đo chu kỳ ngủ/thức thật của Windows | Long-poll có sống sót không. Chỉ ảnh hưởng cờ `--sleep-on-off`, không ảnh hưởng mặc định |
| Task cũ `BTC 4H Report` | Cần quyền admin để dọn: `schtasks /delete /tn "BTC 4H Report" /f`. Nó trỏ vào file đã xoá nên chỉ fail vô hại |
| `OWNER_KEY` chưa cố định trong `.env` | Đặt cố định thì có bookmark vĩnh viễn tự đăng nhập. Đổi lại là mật khẩu nằm trong URL |
| Report và monitor cho confluence khác nhau | Report lấy 26 nến tuần, monitor lấy 52 → verdict khung 1W lệch. Có từ trước refactor, chưa thống nhất |

**Đợt tới:** [Feed tín hiệu lên web](plan/signal-feed-plan.md) — mới ở mức brainstorm,
chưa chốt, chưa code.

---

## Quy ước làm việc

- **Đang ở `main` thì tách nhánh trước khi commit**, không chờ được nhắc
- **Hỏi trước khi push**, kể cả khi test đã xanh
- Plan → chủ dự án duyệt → viết spec → thực thi
- Đo thật rồi mới kết luận. Không đọc doc của bên thứ ba rồi tin, nhất là ở ranh giới quyền
- Trao đổi bằng tiếng Việt
