"""Chỉ số Fear & Greed từ alternative.me."""
from ..config import FEARGREED_URL
from .http import get_json


def fetch_fear_greed():
    """Trả (value, label). Lỗi thì trả (None, "N/A") – chỉ số phụ, không được
    làm chết cả báo cáo."""
    try:
        d = get_json(FEARGREED_URL, timeout=10, retries=2)["data"][0]
        return int(d["value"]), d["value_classification"]
    except Exception as e:
        print(f"  [Fear&Greed] Không lấy được: {e}")
        return None, "N/A"
