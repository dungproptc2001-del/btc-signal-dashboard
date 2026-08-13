"""Cache trong RAM + kênh phát SSE.

Mở trang không kích hoạt fetch: mọi thứ web cần đã nằm sẵn ở đây, do scheduler
cập nhật theo nhịp. 100 lượt xem cũng không thêm một request nào tới Binance.
"""
import asyncio
import threading
from datetime import datetime

from ..config import PRICE_INTERVAL, SCAN_INTERVAL, STALE_AFTER, SYMBOLS


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
        # Nhớ URL cũ qua chu kỳ /off → /on để biết link có đổi mà cảnh báo khách
        self.last_tunnel_url = None
        self.paused      = False
        self.standby     = False
        self.standby_since = None
        self.last_price_at  = None
        self.last_scan_at   = None
        self.last_report_at = None
        self.last_score_at  = None
        self.scan_errors    = 0
        self.task_restarts  = 0    # số lần một nhịp nền chết âm thầm và được dựng lại
        self._subscribers   = set()

    # ── SỐNG HAY ĐÃ CHẾT ──────────────────────────────────────────────────────
    def scan_age(self):
        """Bao nhiêu giây kể từ lượt quét cuối. None khi chưa quét lần nào.

        Trả về SỐ GIÂY chứ không phải mốc thời gian, và đó là chủ ý: `last_scan_at`
        ghi bằng `datetime.now()` – giờ địa phương, không kèm offset – nên bất kỳ ai
        parse nó ở múi giờ khác đều ra sai hàng tiếng. Khoảng cách thì không có múi giờ
        nào để sai.
        """
        with self._lock:
            if not self.last_scan_at:
                return None
            return int((datetime.now() - self.last_scan_at).total_seconds())

    def is_stale(self):
        """Vòng quét đã quá hạn chưa.

        `paused` và `standby` KHÔNG tính là cũ: đó là chủ nhà chủ động cho nghỉ. Báo
        động lúc đó là tự tạo báo động giả cho chính mình, mà báo động giả dùng vài
        hôm là người ta tắt thông báo – rồi tưởng mình vẫn đang được canh.

        Chưa quét lần nào cũng không tính: server vừa bật, chưa kịp chạy nhịp đầu.
        """
        with self._lock:
            if self.paused or self.standby:
                return False
        tuoi = self.scan_age()
        return tuoi is not None and tuoi > STALE_AFTER

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
                    "standby":         self.standby,
                    "standby_since":   _iso(self.standby_since),
                    "viewers":         len(self._subscribers),
                    "started_at":      _iso(self.started_at),
                    "uptime_seconds":  int((datetime.now() - self.started_at).total_seconds()),
                    "last_price_at":   _iso(self.last_price_at),
                    "last_scan_at":    _iso(self.last_scan_at),
                    "last_report_at":  _iso(self.last_report_at),
                    "last_score_at":   _iso(self.last_score_at),
                    "scan_interval":   SCAN_INTERVAL,
                    "price_interval":  PRICE_INTERVAL,
                    "has_report":      self.report_html is not None,
                    # Ngưỡng đi kèm dữ liệu, để client không phải tự đặt luật. Cùng lý
                    # do đã ghi ở chỗ ẩn tỷ lệ thắng: luật nằm trong giao diện thì nó
                    # biến mất lần đầu ai đó sửa giao diện.
                    "stale":            self.is_stale(),
                    "stale_after":      STALE_AFTER,
                    "scan_age_seconds": self.scan_age(),
                    "task_restarts":    self.task_restarts,
                },
            }


def _iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


STATE = ServerState()
