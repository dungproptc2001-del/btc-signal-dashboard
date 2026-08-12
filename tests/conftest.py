import json
from pathlib import Path

import pytest

BASE     = Path(__file__).resolve().parent
FIXTURES = BASE / "fixtures"
GOLDEN   = BASE / "golden"


def _load(directory, name):
    with open(directory / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def golden():
    return _load(GOLDEN, "numbers.json")


@pytest.fixture(scope="session")
def golden_telegram():
    with open(GOLDEN / "telegram.txt", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="session")
def raw():
    """Dữ liệu Binance thô đã đóng băng."""
    return {
        "1w":     _load(FIXTURES, "klines_1w.json"),
        "1d":     _load(FIXTURES, "klines_1d.json"),
        "4h":     _load(FIXTURES, "klines_4h.json"),
        "1h":     _load(FIXTURES, "klines_1h.json"),
        "week":   _load(FIXTURES, "klines_week.json"),
        "ticker": _load(FIXTURES, "ticker.json"),
        "fg":     _load(FIXTURES, "feargreed.json"),
        "meta":   _load(FIXTURES, "meta.json"),
    }


@pytest.fixture(scope="session")
def candles(raw):
    from btcreport.sources.binance import parse_klines
    return {k: parse_klines(raw[k]) for k in ("1w", "1d", "4h", "1h", "week")}
