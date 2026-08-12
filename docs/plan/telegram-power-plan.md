# Bật / tắt server từ Telegram

## Nút thắt

`/stop` đã có sẵn. Cái thiếu là **bật lại** — và nó khó vì một vòng tròn: bot Telegram
sống *bên trong* server. Tắt server là tắt luôn tai nghe, không còn ai đọc `/on`.

Hai ràng buộc cứng, phải nói trước vì chúng loại bỏ phần lớn không gian thiết kế:

**Telegram chỉ cho đúng MỘT tiến trình gọi `getUpdates` trên một bot token.** Hai cái
cùng poll là Telegram trả `409 Conflict`. Nên không dựng được "tiến trình canh gác"
chạy song song cùng poll — phải chọn một trong hai.

**Máy ngủ thì không gì trên máy này nhận được Telegram.** Không server, không canh gác.
Task Scheduler chỉ đánh thức *theo giờ hẹn*, không đánh thức theo tin nhắn. Nghĩa là
không có thiết kế nào bật được server khi laptop đang ngủ.

## Ba đường

| | Cách làm | Bật lại được khi | Giá phải trả |
|---|---|---|---|
| **A. Standby trong cùng tiến trình** | `/off` không giết tiến trình, chỉ đóng funnel + dừng scheduler | máy còn thức | ~40MB RAM nằm không |
| B. Tiến trình canh gác riêng | Tách bot khỏi server, nó độc quyền poll, ra lệnh qua HTTP nội bộ | máy còn thức | Refactor lớn: mọi lệnh đọc `STATE` phải đi qua HTTP |
| C. Task Scheduler hồi sinh mỗi 5 phút | Cờ `data/server.off` để `/stop` không bị hồi sinh ngược | **không bật được từ Telegram** | Chỉ chống crash |

**Chọn A.** B tốn công gấp nhiều lần mà chỉ mua thêm đúng một tình huống — tiến trình
chết hẳn — mà A thì không bao giờ để nó chết hẳn. Cả hai đều câm như nhau khi máy ngủ.
C không giải bài toán này (để dành, làm sau nếu cần chống crash).

## Ba mức tắt

| Lệnh | Dừng quét | Đóng link công khai | Máy được ngủ | Bot còn nghe |
|---|---|---|---|---|
| `/pause` `/resume` | ✓ | | | ✓ |
| **`/off` `/on`** | ✓ | ✓ | chỉ khi `--sleep-on-off` | **✓ luôn luôn** |
| `/stop` (có nút xác nhận) | ✓ | ✓ | ✓ | ✗ |

### Vì sao `/off` mặc định KHÔNG nhả keep-alive

Đây là quyết định của chủ dự án, và nó đánh đổi có chủ đích: máy vẫn thức, vẫn tốn điện.

Đổi lại một bảo đảm cứng: **đã tắt được từ điện thoại thì luôn bật lại được từ điện
thoại.** Nếu nhả keep-alive, máy ngủ, bot câm — ông gõ `/on` vào khoảng không rồi phải
mò về mở laptop. Một lệnh tắt mà không chắc bật lại được thì tệ hơn là không có lệnh
tắt, vì nó dụ người ta tin là điều khiển được từ xa.

Ai muốn đánh đổi ngược lại thì có cờ `--sleep-on-off`.

## Việc phải làm

| # | Bước | Xong khi |
|---|---|---|
| 1 | `server/power.py` — `standby()` / `wake()`, khoá chống gọi chồng | `/on` bấm 3 lần vẫn đúng 3 task scheduler |
| 2 | `STATE.standby` vào `public()`, băng báo trên dashboard | Mở trang lúc standby thấy ngay, không phải đoán |
| 3 | `/off` `/on` trong bot + cập nhật `HELP` | Bấm từ điện thoại thật thấy đổi trạng thái |
| 4 | `/stop` hỏi lại bằng nút bấm, qua cửa kiểm `is_owner` | Bấm nhầm không tắt được ngay |
| 5 | Cờ `--sleep-on-off` trong `apps/server.py` | `/off` nhả keep-alive khi có cờ |
| 6 | Test cho `power.py` + chốt `is_owner` cho lệnh mới | 203 test cũ vẫn xanh |
| 7 | Đo chu kỳ sleep/wake thật | Biết long-poll có sống sót không |

## Nghiệm thu

```
/off  → powercfg /requests vẫn thấy python (mặc định giữ thức)
      → link công khai chết, /status báo standby
/on   → link công khai Y HỆT URL cũ, quét chạy lại trong một nhịp
/on   bấm 3 lần liên tiếp → vẫn đúng 3 task, không phải 9
/stop → hiện nút xác nhận; callback từ chat_id lạ → bị chặn
Máy ngủ 10 phút → đánh thức → /status phải trả lời được
```

## Rủi ro đã biết

**Long-poll có thể không sống sót qua giấc ngủ của Windows.** Kết nối HTTP đang treo bị
đứt khi máy ngủ. `_get_updates` có bắt exception và thử lại, nhưng chưa từng đo qua một
chu kỳ sleep/wake thật. Rủi ro này đã tụt từ "chặn cả thiết kế" xuống "để biết", vì mặc
định `/off` giữ máy thức — nó chỉ còn ảnh hưởng cờ `--sleep-on-off`.

**Link công khai giữ nguyên qua off→on chỉ đúng với Tailscale.** Tailscale neo URL vào
tên máy trong tailnet. Với `TUNNEL_PROVIDER=cloudflare` thì URL đổi mỗi lần mở lại —
tin nhắn `/on` phải cảnh báo, không thì khách đã duyệt bấm link cũ vào chỗ chết.

## Ngoài phạm vi

Không đụng `engine/`, `sources/`, `notify/`, `web/`. Không đổi công thức tín hiệu hay
chu kỳ quét. Không làm C (auto hồi sinh chống crash) — bài toán khác.
