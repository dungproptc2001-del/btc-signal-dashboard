"""Cache trong RAM + kênh phát SSE.

Mở trang không kích hoạt fetch: mọi thứ web cần đã nằm sẵn ở đây, do scheduler
cập nhật theo nhịp. 100 lượt xem cũng không thêm một request nào tới Binance.
"""
import asyncio
import threading
from datetime import datetime

from ..config import PRICE_INTERVAL, SCAN_INTERVAL, SYMBOLS


class ServerState:
    def __init__(self):
        self._lock       = threading.RLock()
        self.started_at  = datetime.now()
        self.prices      = {}      # symbol -> {last, change_24h, at}
        self.snapshots   = {}      # symbol -> snapshot của watch
        self.signal_state = {}     # state debounce, đồng bộ với data/last_signals.json
        self.report_ctx  = None
        self.report_html = None
        self.tunnel_url  = None
        self.paused      = False
        self.last_price_at  = None
        self.last_scan_at   = None
        self.last_report_at = None
        self.scan_errors    = 0
        self._subscribers   = set()

    # ── SSE ───────────────────────────────────────────────────────────────────
    def subscribe(self):
        q = asyncio.Queue(maxsize=32)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event, data):
        """Đẩy sự kiện tới mọi tab đang mở.

        Client chậm (hàng đợi đầy) thì bỏ qua chứ không chặn scheduler – thà mất
        một khung cập nhật còn hơn treo cả vòng quét.
        """
        with self._lock:
            queues = list(self._subscribers)
        payload = {"event": event, "data": data}
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    @property
    def viewers(self):
        with self._lock:
            return len(self._subscribers)

    # ── CẬP NHẬT ──────────────────────────────────────────────────────────────
    def update_prices(self, prices):
        with self._lock:
            self.prices.update(prices)
            self.last_price_at = datetime.now()

    def update_snapshot(self, symbol, snapshot):
        with self._lock:
            self.snapshots[symbol] = snapshot
            if snapshot:
                self.prices[symbol] = {
                    "last":       snapshot["price"],
                    "change_24h": snapshot["change_24h"],
                    "at":         datetime.now().isoformat(timespec="seconds"),
                }

    def update_report(self, html, ctx):
        with self._lock:
            self.report_html    = html
            self.report_ctx     = ctx
            self.last_report_at = datetime.now()

    # ── ĐỌC RA WEB ────────────────────────────────────────────────────────────
    def public(self):
        """Dữ liệu an toàn để trả ra web.

        KHÔNG được chứa OWNER_KEY, token phiên hay bot token. Có test canh việc này.
        """
        with self._lock:
            symbols = []
            for name, symbol in SYMBOLS.items():
                snap  = self.snapshots.get(symbol)
                price = self.prices.get(symbol, {})
                symbols.append({
                    "name":       name,
                    "symbol":     symbol,
                    "price":      price.get("last"),
                    "change_24h": price.get("change_24h"),
                    "confluence": (snap or {}).get("confluence"),
                    "timeframes": [
                        {k: tf[k] for k in ("label", "verdict", "score", "rsi", "macd_bull")}
                        for tf in (snap or {}).get("timeframes", [])
                    ],
                    "levels": (snap or {}).get("levels"),
                    "risk":   (snap or {}).get("risk"),
                })

            return {
                "symbols": symbols,
                "status": {
                    "paused":          self.paused,
                    "viewers":         len(self._subscribers),
                    "started_at":      _iso(self.started_at),
                    "uptime_seconds":  int((datetime.now() - self.started_at).total_seconds()),
                    "last_price_at":   _iso(self.last_price_at),
                    "last_scan_at":    _iso(self.last_scan_at),
                    "last_report_at":  _iso(self.last_report_at),
                    "scan_interval":   SCAN_INTERVAL,
                    "price_interval":  PRICE_INTERVAL,
                    "has_report":      self.report_html is not None,
                },
            }


def _iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


STATE = ServerState()
