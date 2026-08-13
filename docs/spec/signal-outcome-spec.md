# Spec: Chấm điểm tín hiệu

Chốt từ [plan](../plan/signal-outcome-plan.md). Nhánh `feat/signal-outcome`.

## Bảy quyết định

| # | Câu | Chốt |
|---|---|---|
| 1 | Chấm theo hướng nào | **Confluence**, tính lại SL/TP theo hướng đó |
| 2 | Nến chạm cả TP lẫn SL | Log rõ chạm gì / lúc nào; ca chạm cả hai → **thua + đánh dấu `ambiguous`** |
| 3 | Hạn tín hiệu | **7 ngày** |
| 4 | Nến dò | **1H** |
| 5 | Ngưỡng hiện tỷ lệ | **n ≥ 20**, dưới đó chỉ hiện số đếm thô |
| 6 | Tín hiệu chồng lấn | Đổi hướng thì **đóng cái cũ** theo giá hiện tại |
| 7 | Khách xem thống kê | **Được** — đồng bộ với quyết định "được xem lịch sử hết" |

### Cơ sở của quyết định 1 — đo trên nhật ký thật

5 bản ghi trong `data/signals.jsonl` ngày 12–13/08/2026:

| Confluence (báo ra) | 4H (quyết SL/TP) | Có mức? |
|---|---|---|
| SHORT BIAS | SHORT | ✅ |
| **LONG BIAS** | **NEUTRAL** | ❌ `sl=tp=None` |
| STRONG SHORT | SHORT | ✅ |
| SHORT BIAS | SHORT | ✅ |
| NEUTRAL | NEUTRAL | — không phải lệnh |

**1 trong 4 tín hiệu có hướng đã rơi vào ô không chấm được.** Không phải rủi ro lý thuyết.

### Cơ sở của quyết định 2 và 4 — đo trên nến thật

Khoảng SL→TP luôn bằng `(ATR_MULT_SL + ATR_MULT_TP) × ATR(4H)` = `4.5 × ATR(4H)`.
Một nến chạm được cả hai thì biên độ của nó phải `>=` khoảng đó. Đếm trên 1000 nến
gần nhất mỗi khung, 13/08/2026:

| Mã | Khoảng SL→TP | Nến 1H vượt | Nến 15m vượt |
|---|---|---|---|
| BTCUSDT | 3,13% giá | **0 / 1000** | 0 / 1000 |
| ETHUSDT | 4,43% giá | **0 / 1000** | 0 / 1000 |
| PAXGUSDT | 3,39% giá | **0 / 1000** | 0 / 1000 |

Hiếm có tính cấu trúc chứ không phải may: **ATR tự nở ra khi thị trường biến động**,
nên khoảng SL→TP giãn theo. Thị trường càng loạn thì ngưỡng càng cao.

⇒ Nến 1H là đủ. 15m nặng gấp 4 request mà không mua thêm được gì đo đếm được.

Vẫn giữ nhánh xử lý ca mập mờ, vì `0/1000` không phải `không bao giờ`. Khi xảy ra:
tính **thua** và bật cờ `ambiguous` để nó không lẩn vào đám đông.

---

## Đổi hành vi: SL/TP theo hướng confluence

`engine/signals.py` thêm hàm thuần:

```python
def direction(confluence_verdict):
    """STRONG LONG | LONG BIAS   → LONG
       STRONG SHORT | SHORT BIAS → SHORT
       NEUTRAL | không rõ        → NEUTRAL"""
```

`service/watch.py` đổi một dòng:

```python
- "risk": risk_levels(h4, tfs[2]["verdict"])       # verdict khung 4H
+ "risk": risk_levels(h4, direction(conf["verdict"]))
```

**Đây là đổi hành vi thật, không phải refactor.** Từ nay Telegram hiện SL/TP cho cả
`LONG BIAS` / `SHORT BIAS` kể cả khi khung 4H đang NEUTRAL. Đúng hơn về mặt logic —
đã báo có hướng thì phải kèm mức — nhưng số tín hiệu kèm mức sẽ tăng.

`risk_levels()` **không sửa**. Nó vẫn nhận `LONG`/`SHORT`/`NEUTRAL`, chỉ là người gọi
đưa cho nó hướng khác. Giữ được toàn bộ test cũ của engine.

---

## Định danh bản ghi

Nhật ký cũ không có `id`. Công thức khoá suy được từ dữ liệu đã có:

```python
signal_id(entry) = entry.get("id") or f'{entry["symbol"]}@{entry["at"]}'
```

Bản ghi mới ghi hẳn `id` vào file. Bản ghi cũ tính ra **đúng cùng một khoá** —
không phải sửa file lịch sử. Một mã không thể bắn hai tín hiệu trong cùng một giây,
nên cặp `(symbol, at)` là duy nhất.

## Hai file, một chiều

```
data/signals.jsonl     BẤT BIẾN — ghi xong không bao giờ sửa
data/outcomes.jsonl    kết quả đã ngã ngũ, khoá theo id
```

Chỉ ghi kết quả **đã ngã ngũ**. Tín hiệu đang chạy (`open`) tính lại mỗi lần đọc,
không lưu — file chỉ chứa sự thật đã chốt, mỗi dòng đọc một lần là hiểu.

Chấm lại theo quy tắc khác: **xoá `outcomes.jsonl`**. Dữ liệu gốc không suy suyển.

---

## Phân loại

| Trạng thái | Nghĩa | Vào tỷ lệ thắng? | Có R? |
|---|---|---|---|
| `win` | Chạm TP trước SL | ✅ | +2.0 |
| `loss` | Chạm SL trước TP | ✅ | −1.0 |
| `expired` | Hết 7 ngày chưa chạm gì | ✅ **(bắt buộc đếm)** | R thật lúc hết hạn |
| `superseded` | Bị tín hiệu đổi hướng đóng sớm | ❌ | R thật lúc đóng |
| `skipped` | Không có hướng hoặc không có mức | ❌ | — |
| `open` | Đang chạy, chưa lưu file | ❌ | — |

**`expired` nằm trong mẫu số.** Vứt nó đi là cách phổ biến nhất khiến loại thống kê này
nói dối — tín hiệu không đi đâu cả vẫn là tín hiệu sai.

`superseded` ngoài mẫu số vì nó chưa được chạy hết đời mình, nhưng **R của nó vẫn tính
vào R trung bình** — đó là lãi/lỗ thật ông chịu. Hai mẫu số khác nhau, phải ghi rõ cả hai
trên giao diện chứ không được trộn.

### R

```
R = (exit − entry) / |entry − sl| × (+1 nếu LONG, −1 nếu SHORT)
```

`|entry − sl|` = `1.5 × ATR`, TP = `3 × ATR` ⇒ thắng đúng `+2.0`, thua đúng `−1.0`.

---

## Thuật toán chấm

Với mỗi tín hiệu chưa có kết quả trong `outcomes.jsonl`:

1. `direction(entry["to"])` — NEUTRAL ⇒ `skipped`, lý do `khong-co-huong`.
2. `risk.sl` hoặc `risk.tp` là None ⇒ `skipped`, lý do `khong-co-muc`
   (chỉ xảy ra với bản ghi cũ, trước khi đổi hướng SL/TP).
3. Cửa sổ `[at, min(at + 7 ngày, bây giờ)]`, lấy nến 1H bằng `fetch_klines_range`.
4. **Bỏ nến nào mở trước `at`.** Tín hiệu không thể bị đóng bởi giá xảy ra
   trước khi nó tồn tại. Nến chứa `at` gần như luôn mở trước `at` vài chục phút —
   không loại là bịa ra thắng/thua từ quá khứ.
5. Duyệt xuôi thời gian, nến đầu tiên chạm:

   | Hướng | Chạm TP khi | Chạm SL khi |
   |---|---|---|
   | LONG | `high >= tp` | `low <= sl` |
   | SHORT | `low <= tp` | `high >= sl` |

   Cả hai trong cùng một nến ⇒ `loss` + `ambiguous: true`.
6. Chưa chạm gì mà gặp mốc bị đóng sớm ⇒ `superseded`, exit = giá đóng nến gần mốc đó.
7. Chưa chạm gì, đã quá `at + 7 ngày` ⇒ `expired`, exit = giá đóng cuối cửa sổ.
8. Còn lại ⇒ `open`, không ghi file.

### Khi nào một tín hiệu bị đóng sớm

Tín hiệu sau **trên cùng một mã** có `direction` **khác** thì đóng tín hiệu đang mở.
Bao gồm cả đổi sang NEUTRAL — NEUTRAL nghĩa là đứng ngoài, tức là thoát.

Cùng hướng thì **không đóng**: `SHORT BIAS → STRONG SHORT` là quan điểm mạnh lên chứ
không phải đảo chiều. Hai tín hiệu chạy song song, mỗi cái tự chịu trách nhiệm cho mức
giá của chính nó.

---

## Nhịp chạy

Nhịp nền thứ tư, **30 phút**. Chọn 30 phút vì nến dò là 1H — nhanh hơn không mịn thêm
được, chậm hơn thì kết quả về trễ vô ích.

Chạy tay: `python -m apps.score`.

Gọi Binance: mỗi tín hiệu chưa ngã ngũ tốn 1 request. Tối đa vài chục tín hiệu mở cùng
lúc ⇒ vài chục request mỗi 30 phút. Không đáng kể so với nhịp giá 30 giây.

## Giao diện

| Route | Quyền | Trả |
|---|---|---|
| `GET /api/signals/stats` | khách đã duyệt trở lên | Thống kê tổng + theo mã |
| `GET /api/signals/history` | như cũ | **Thêm** `outcome` vào mỗi bản ghi |

Ba luật hiển thị, **bắt buộc**:

1. **Số mẫu luôn đứng cạnh mọi tỷ lệ.** `62%` là vô nghĩa, `62% (n=13)` là trung thực.
2. **n < 20 thì không hiện tỷ lệ**, chỉ hiện số đếm thô.
3. **Ghi rõ đây không phải backtest.** Nó đo tiến về phía trước, trên đúng những tín
   hiệu đã thật sự bắn ra. Không hồi tố được — và đó là điểm mạnh, vì không có chỗ nào
   để chỉnh tham số cho khớp quá khứ.

## Ngoài phạm vi

Không đụng công thức chỉ báo, ngưỡng `SIGNAL_THRESHOLD`, `CONFIRM_SCANS`, `ATR_MULT_*`.
**Đợt này không chỉnh một tham số nào.** Mục đích là có thước đo trước. Chỉnh tham số khi
chưa có số liệu chính là cái sai mà đợt này muốn chấm dứt.
