"""Sinh lại mốc golden từ fixtures hiện có.

    python tests/capture_golden.py

Chỉ chạy khi ĐÃ CỐ Ý đổi công thức chỉ báo / ngưỡng tín hiệu / format tin nhắn.
Chạy bừa là mất tác dụng bảo vệ: golden sẽ hợp thức hoá luôn cả bug vừa tạo ra.

Quy trình đúng khi đổi model:
  1. Đổi code
  2. `pytest` → xem test golden fail ở đâu, đối chiếu số cũ/mới bằng mắt
  3. Nếu số mới đúng như ý → chạy file này để chốt mốc mới
"""
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent))

from btcreport.engine.analysis import build_context                # noqa: E402
from btcreport.engine.indicators import (                          # noqa: E402
    atr, bollinger, ema, macd_line, rsi, sma,
)
from btcreport.engine.levels import risk_levels                    # noqa: E402
from btcreport.notify.messages import format_report_message        # noqa: E402
from btcreport.sources.binance import parse_klines                 # noqa: E402

FIXTURES = BASE / "fixtures"
GOLDEN   = BASE / "golden"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def main():
    GOLDEN.mkdir(exist_ok=True)
    meta = load("meta.json")

    candles = {k: parse_klines(load(f"klines_{k}.json"))
               for k in ("1w", "1d", "4h", "1h", "week")}
    ticker  = load("ticker.json")
    fg      = load("feargreed.json")

    ctx = build_context(
        symbol=meta["symbol"],
        now=datetime.fromisoformat(meta["now"]),
        daily=candles["1d"], weekly=candles["1w"],
        h4=candles["4h"], h1=candles["1h"],
        ticker=ticker, fear_greed=(fg["value"], fg["label"]),
        week_candles=candles["week"],
        week_start=datetime.fromisoformat(meta["week_start"]),
        week_end=datetime.fromisoformat(meta["week_end"]),
    )

    closes = [c["close"] for c in candles["1d"]]
    macd_v, sig_v, hist_v = macd_line(closes)
    bbu, bbm, bbl = bollinger(closes)

    numbers = {
        "signal": {k: ctx["signal"][k]
                   for k in ("verdict", "action", "score", "reasons", "confidence")},
        "timeframes": {
            tf["label"]: {"verdict": tf["verdict"], "action": tf["action"],
                          "score": tf["score"], "rsi": tf["rsi"],
                          "macd": tf["macd"], "macd_signal": tf["macd_signal"],
                          "macd_bull": tf["macd_bull"]}
            for tf in ctx["timeframes"]
        },
        "confluence": ctx["confluence"],
        "levels":     ctx["levels"],
        "levels_4h":  ctx["levels_4h"],
        "risk":       ctx["risk"],
        "risk_4h":    risk_levels(candles["4h"], ctx["timeframes"][2]["verdict"]),
        "atr_daily":  atr(candles["1d"]),
        "indicators": {
            "sma7":  sma(closes, 7),   "sma25": sma(closes, 25),
            "sma99": sma(closes, 99),  "ema50": ema(closes, 50),
            "rsi":   rsi(closes),
            "macd":  macd_v, "macd_signal": sig_v, "macd_hist": hist_v,
            "bb_upper": bbu, "bb_mid": bbm, "bb_lower": bbl,
        },
        "counts": {k: len(v) for k, v in candles.items()},
    }
    # Khớp tên khoá cũ để test không phải đổi
    numbers["counts"] = {"weekly": len(candles["1w"]), "daily": len(candles["1d"]),
                         "h4": len(candles["4h"]), "h1": len(candles["1h"]),
                         "week": len(candles["week"])}

    (GOLDEN / "numbers.json").write_text(
        json.dumps(numbers, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  numbers.json   verdict={ctx['signal']['verdict']} "
          f"score={ctx['signal']['score']} confluence={ctx['confluence']['verdict']}")

    msg = format_report_message(ctx)
    (GOLDEN / "telegram.txt").write_text(msg, encoding="utf-8")
    print(f"  telegram.txt   {len(msg)} ky tu")


if __name__ == "__main__":
    sys.exit(main())
