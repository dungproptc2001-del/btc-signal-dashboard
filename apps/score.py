"""Chấm điểm tín hiệu đã bắn: chạm TP trước hay SL trước.

    python -m apps.score            chấm rồi ghi vào data/outcomes.jsonl
    python -m apps.score --kho      chỉ xem, KHÔNG ghi gì

Chạy tay. Server web có nhịp chấm 30 phút lo việc này rồi — chạy cả hai cùng lúc
không hỏng gì (kết quả đã ngã ngũ thì bỏ qua, không chấm lại), chỉ tốn request thừa.

Muốn chấm lại toàn bộ theo quy tắc khác: xoá data/outcomes.jsonl rồi chạy lại.
data/signals.jsonl là bất biến, không bao giờ mất.
"""
import sys

from btcreport.config import SIGNAL_EXPIRY_DAYS, STATS_MIN_N
from btcreport.service import journal, outcome

BIEU_TUONG = {
    outcome.WIN:        "THANG",
    outcome.LOSS:       "THUA ",
    outcome.EXPIRED:    "HET H",
    outcome.SUPERSEDED: "DOI H",
    outcome.SKIPPED:    "BO QUA",
    outcome.OPEN:       "DANG CHAY",
}


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    kho = "--kho" in sys.argv

    entries = journal.read()
    if not entries:
        print("Nhật ký trống – chưa có tín hiệu nào để chấm.")
        return 0

    da_co = outcome.read()
    print(f"Nhật ký: {len(entries)} tín hiệu · đã chấm: {len(da_co)} · "
          f"hạn {SIGNAL_EXPIRY_DAYS} ngày, dò bằng nến {outcome.OUTCOME_PROBE_TF}")

    results = outcome.evaluate(entries, existing=da_co, log=print)

    for r in results:
        r_str = f"  R={r['r']:+.2f}" if r.get("r") is not None else ""
        mo_mo = "  [nen cham ca hai - tinh la thua]" if r.get("ambiguous") else ""
        ly_do = f"  ({r['reason']})" if r.get("reason") else ""
        print(f"  {BIEU_TUONG.get(r['status'], r['status']):<10} {r['id']}{r_str}{ly_do}{mo_mo}")

    if kho:
        print("\n--kho: không ghi gì.")
    else:
        xong = outcome.save(results)
        print(f"\nGhi thêm {len(xong)} kết quả đã ngã ngũ vào {outcome.OUTCOME_FILE.name}.")

    # Thống kê tính trên TOÀN BỘ nhật ký, không chỉ phần vừa chấm.
    tat_ca, tk = outcome.load_all(entries) if not kho else (results, outcome.stats(results))
    o = tk["overall"]
    print(f"\nTổng: {o['counts']}")
    if o["win_rate"] is None:
        print(f"  Chưa hiện tỷ lệ thắng: n={o['n']}, cần >= {STATS_MIN_N}. "
              f"Tỷ lệ trên mẫu bé là nhiễu chứ không phải kết luận.")
    else:
        print(f"  Tỷ lệ thắng: {o['win_rate']}% (n={o['n']})")
    if o["avg_r"] is not None:
        print(f"  R trung bình: {o['avg_r']:+.2f} (n={o['n_r']}) · tổng {o['total_r']:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
