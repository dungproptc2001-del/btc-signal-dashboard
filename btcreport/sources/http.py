"""HTTP GET có retry + backoff. Mọi call ra ngoài đều đi qua đây."""
import random
import time

import requests

from ..config import HTTP_BACKOFF_SEC, HTTP_RETRIES


def get_json(url, params=None, timeout=15, retries=HTTP_RETRIES):
    """GET + retry với exponential backoff. Raise exception cuối nếu hết lượt.

    Retry với lỗi mạng/timeout, HTTP 429 (rate limit) và 5xx.
    Lỗi 4xx khác (sai symbol, sai param) fail ngay – retry vô nghĩa.
    """
    last_exc = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            last_exc = e
            resp = getattr(e, "response", None)
            if resp is not None and resp.status_code < 500 and resp.status_code != 429:
                raise
        except (requests.RequestException, ValueError) as e:
            last_exc = e

        if attempt < retries - 1:
            # Binance trả Retry-After khi rate-limit → tôn trọng nó nếu có
            resp   = getattr(last_exc, "response", None)
            hinted = float(resp.headers.get("Retry-After", 0)) if resp is not None else 0
            wait   = hinted or HTTP_BACKOFF_SEC * (2 ** attempt) + random.uniform(0, 1)
            print(f"    [retry {attempt + 1}/{retries - 1}] {last_exc} – chờ {wait:.1f}s")
            time.sleep(wait)

    raise last_exc
