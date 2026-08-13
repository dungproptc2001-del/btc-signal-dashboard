# Chấm điểm tín hiệu — hệ thống tự biết mình đúng hay sai

**Trạng thái: BRAINSTORM. Chưa chốt, chưa code.** Cuối file có 7 câu cần quyết.

Nhánh `feat/signal-outcome`.

## Vấn đề

Hệ thống bắn tín hiệu từ đầu đến giờ và **chưa bao giờ tự chấm điểm**. Câu cơ bản nhất
vẫn không trả lời được:

> Tín hiệu STRONG LONG của BTC đúng bao nhiêu phần trăm?

Hệ quả nặng hơn là **mọi tham số đang được chỉnh bằng cảm giác**. Ngưỡng `|score| >= 3`,
`CONFIRM_SCANS = 2`, R:R 1:2 — không có gì nói chúng tốt hay tệ. Không đo thì mỗi lần
"cải tiến" chỉ là đổi một linh cảm này lấy một linh cảm khác.

## Nguyên liệu đã có sẵn

Nhật ký `data/signals.jsonl` từ đợt trước đã ghi đủ:

```json
{"at": "...", "price": 64128.0,
 "risk": {"entry": 64128.0, "sl": 63200.0, "tp": 66000.0, "atr": 620.0, "rr": 2.0}}
```

Chỉ thiếu bước đối chiếu: lấy nến sau `at`, xem giá chạm `tp` trước hay `sl` trước.

---

## 🔴 Hai chỗ phải làm rõ TRƯỚC khi viết một dòng code

### 1. Hướng của SL/TP không theo tín hiệu được báo

`watch.py` gọi:

```python
"risk": risk_levels(h4, tfs[2]["verdict"])     # tfs[2] = khung 4H
```

Nghĩa là **SL/TP tính theo verdict khung 4H**, trong khi tín hiệu bắn ra Telegram và
hiện trên web là **confluence của cả 4 khung**. Hai cái này lệch nhau được:

| Confluence (cái được báo) | Verdict 4H (cái quyết định SL/TP) | Hậu quả |
|---|---|---|
| STRONG LONG | NEUTRAL | `sl = tp = None` → **không chấm điểm được** |
| NEUTRAL | LONG | Có SL/TP nhưng tín hiệu báo là "đứng ngoài" |
| STRONG LONG | SHORT | SL/TP **ngược hướng** tín hiệu |

Chấm điểm mà không giải quyết chỗ này thì con số ra được **không có nghĩa** — không biết
đang đo cái gì. Đây không phải chi tiết kỹ thuật, nó là câu hỏi "tín hiệu của hệ thống
này thực sự là gì".

Ba đường:

- **A.** Chấm theo confluence, tính lại SL/TP theo hướng confluence. Đúng với thứ người
  dùng nhận được. Phải sửa `risk_levels` hoặc cách gọi nó.
- **B.** Chấm theo verdict 4H. Trung thành với SL/TP đang có, nhưng đo một thứ khác với
  thứ được báo.
- **C.** Chấm cả hai, so sánh. Tốn hơn nhưng trả lời luôn câu "nên báo theo cái nào".

Nghiêng về **A**, vì đó là thứ ông thật sự hành động theo. Nhưng nó **đổi hành vi
hiện tại**, phải cân nhắc riêng.

### 2. Nến không nói thứ tự trong lòng nó

Nếu một cây nến có `high >= tp` **và** `low <= sl`, dữ liệu kline không cho biết cái nào
xảy ra trước. Đây là giới hạn của dữ liệu, không phải của code.

Quy ước phải chọn và **ghi rõ**:

- **Bi quan** — coi là thua. Không bao giờ thổi phồng thành tích.
- Lạc quan — coi là thắng. Tự lừa mình.
- Bỏ qua — vứt mẫu đi, làm méo thống kê.

Nghiêng về **bi quan**, và dùng nến nhỏ (1H hoặc 15m) để trường hợp này hiếm đi.

---

## Thiết kế

### Bản ghi thiếu định danh

Nhật ký hiện **không có `id`**. Muốn gắn kết quả vào từng tín hiệu thì phải có khoá.
Bản ghi cũ vẫn định danh được bằng cặp `(at, symbol)` — đủ duy nhất vì một mã không thể
bắn hai tín hiệu cùng một giây. Bản ghi mới nên có `id` hẳn hoi.

### Lưu kết quả ở đâu

JSONL là **append-only** — đó là ưu điểm, đừng phá. Nên kết quả đi ra file riêng:

```
data/signals.jsonl     bất biến, ghi xong không sửa
data/outcomes.jsonl    kết quả, khoá theo id (hoặc at+symbol)
```

Ghép hai bên lúc đọc. Chấm lại theo quy tắc mới thì chỉ cần xoá `outcomes.jsonl` —
**dữ liệu gốc không bao giờ mất**.

### Chấm lúc nào

Thêm một nhịp nền (mỗi 30–60 phút): quét các tín hiệu chưa có kết quả, lấy nến từ `at`
tới giờ, phân loại:

```
win       chạm TP trước SL
loss      chạm SL trước TP
open      chưa chạm cái nào, chưa hết hạn
expired   hết hạn mà chưa chạm gì
skipped   không có SL/TP (xem mục 🔴 1)
```

**`expired` phải được đếm.** Vứt nó đi là thổi phồng win rate — đây là cách phổ biến
nhất khiến loại thống kê này nói dối.

### Hiển thị

Cạnh nhật ký trên trang chủ: win rate theo mã, theo STRONG vs BIAS, R trung bình, và
**số mẫu luôn hiển thị cạnh mọi tỷ lệ**.

---

## ⚠️ Cạm bẫy lớn nhất: tự lừa mình bằng số

3 mã, confluence đổi vài lần mỗi ngày → khoảng **10–30 tín hiệu/tháng**. Win rate trên
n = 12 là **nhiễu**, không phải kết luận. Tháng đầu chắc chắn sẽ ra một con số trông rất
thuyết phục và hoàn toàn vô nghĩa.

Ba việc bắt buộc, không phải tuỳ chọn:

1. **Luôn hiện số mẫu ngay cạnh mọi tỷ lệ.** "62%" là vô nghĩa, "62% (n=13)" thì trung thực.
2. **Ẩn hẳn tỷ lệ khi n dưới ngưỡng** (đề xuất 20), chỉ hiện số đếm thô.
3. **Nói rõ đây không phải backtest.** Nó đo tiến về phía trước từ hôm nay, trên đúng
   những tín hiệu đã thật sự bắn ra. Không hồi tố được, và đó là điểm mạnh — không có
   chỗ cho việc chỉnh tham số cho khớp quá khứ.

---

## Cần quyết trước khi viết spec

1. **Chấm theo confluence hay theo verdict 4H?** (mục 🔴 1 — quan trọng nhất)
2. **Nến trùng chạm cả TP lẫn SL: bi quan, lạc quan, hay bỏ?**
3. **Hạn của một tín hiệu là bao lâu?** ATR lấy từ khung 4H, nên 3–7 ngày là hợp lý.
   Quá ngắn thì toàn `expired`, quá dài thì tín hiệu cũ nhiễu vào tín hiệu mới.
4. **Dùng nến nào để dò?** 1H rẻ và đủ mịn; 15m chính xác hơn nhưng nặng gấp 4.
5. **Ngưỡng n tối thiểu để dám hiện tỷ lệ?**
6. **Tín hiệu chồng lấn**: BTC đang mở lệnh LONG thì bắn tiếp SHORT — đóng cái cũ theo
   giá hiện tại, hay để cả hai chạy song song?
7. **Khách đã duyệt có được xem thống kê không**, hay chỉ chủ nhà?

## Ngoài phạm vi

Không đụng công thức chỉ báo, ngưỡng tín hiệu, chu kỳ quét. **Chưa chỉnh tham số gì cả** —
mục đích của đợt này là có thước đo trước đã. Chỉnh khi chưa có số liệu là đúng cái sai
mà đợt này muốn chấm dứt.
