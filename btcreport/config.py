"""Cấu hình tập trung: đường dẫn, secret, hằng số.

Mọi module khác đọc hằng số từ đây, không tự định nghĩa lại.
"""
import os
import secrets
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"


# ── ENV LOADER (không cần python-dotenv) ─────────────────────────────────────
def load_dotenv(path: Path | None = None) -> None:
    """Đọc .env vào os.environ. Không ghi đè biến môi trường đã có sẵn."""
    path = path or BASE_DIR / ".env"
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


load_dotenv()

for _d in (DATA_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ── SECRET ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── NGUỒN DỮ LIỆU ────────────────────────────────────────────────────────────
BINANCE_URL   = "https://api.binance.com/api/v3"
FEARGREED_URL = "https://api.alternative.me/fng/?limit=1"

SYMBOL  = "BTCUSDT"                       # mã của báo cáo HTML
SYMBOLS = {                               # các mã monitor theo dõi
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "XAU": "PAXGUSDT",   # PAX Gold – 1 token = 1 troy oz vàng, có trên Binance spot
}

# ── HTTP ─────────────────────────────────────────────────────────────────────
HTTP_RETRIES     = 4
HTTP_BACKOFF_SEC = 2.0     # 2s, 4s, 8s (+ jitter)

# ── SIGNAL ───────────────────────────────────────────────────────────────────
# Thang điểm: RSI(±2) + MACD(±1) + MA cross(±1) + trend EMA50(±1)
#             + volume confirm(±1) + 3 nến liên tiếp(±1)
MAX_SCORE        = 7
SIGNAL_THRESHOLD = 3       # |score| >= 3 mới ra LONG/SHORT, dưới đó NEUTRAL
ATR_MULT_SL      = 1.5
ATR_MULT_TP      = 3.0     # R:R 1:2

# ── MONITOR ──────────────────────────────────────────────────────────────────
SCAN_INTERVAL    = 15 * 60  # giây – quét mỗi 15 phút
CONFIRM_SCANS    = 2        # confluence mới phải giữ đủ N lần quét mới alert
MAX_CONSEC_FAILS = 4        # fetch lỗi liên tiếp bao nhiêu lần thì cảnh báo

# ── CHẤM ĐIỂM TÍN HIỆU ───────────────────────────────────────────────────────
SIGNAL_EXPIRY_DAYS = 7          # chưa chạm TP/SL sau ngần này ngày thì coi là hết hạn
OUTCOME_PROBE_TF   = "1h"       # nến dùng để dò TP/SL
OUTCOME_INTERVAL   = 30 * 60    # giây – nhịp chấm lại. Mịn hơn nến dò cũng vô ích.

# Dưới ngưỡng này KHÔNG hiện tỷ lệ thắng, chỉ hiện số đếm thô.
# 3 mã, ~10-30 tín hiệu/tháng: tỷ lệ trên n=12 là nhiễu chứ không phải kết luận,
# mà một con số thuyết phục sai còn tệ hơn là không có con số nào.
STATS_MIN_N = 20

# ── FILE RUNTIME ─────────────────────────────────────────────────────────────
STATE_FILE  = DATA_DIR / "last_signals.json"
OUTCOME_FILE = DATA_DIR / "outcomes.jsonl"
PID_FILE    = DATA_DIR / "monitor.pid"
REPORT_FILE = OUTPUT_DIR / "btc_report.html"

# ── SERVER ───────────────────────────────────────────────────────────────────
SERVER_HOST      = os.environ.get("SERVER_HOST", "0.0.0.0")
SERVER_PORT      = int(os.environ.get("SERVER_PORT", "8000"))

# "tailscale"  – URL cố định https://<ten-may>.<tailnet>.ts.net
# "cloudflare" – quick tunnel, URL đổi mỗi lần khởi động, không cần tài khoản
TUNNEL_PROVIDER  = os.environ.get("TUNNEL_PROVIDER", "tailscale").strip().lower()

# /off có nhả keep-alive cho máy ngủ luôn không.
# Mặc định KHÔNG: máy ngủ là bot câm, gõ /on vào khoảng không rồi phải mò về mở laptop.
# Bật bằng cờ --sleep-on-off nếu chấp nhận đánh đổi đó để tiết kiệm điện.
SLEEP_ON_OFF     = os.environ.get("SLEEP_ON_OFF", "").strip().lower() in ("1", "true", "yes")
PRICE_INTERVAL   = 30           # giây – nhịp cập nhật giá cho dashboard
REPORT_INTERVAL  = 4 * 60 * 60  # giây – nhịp dựng lại báo cáo BTC

# Khoá chủ nhà: mở /login?key=... để nhận cookie mà không cần duyệt qua Telegram.
# Chưa đặt trong .env thì sinh ngẫu nhiên mỗi lần khởi động (bot sẽ nhắn link).
OWNER_KEY = os.environ.get("OWNER_KEY") or secrets.token_urlsafe(24)

# ── ACCESS ───────────────────────────────────────────────────────────────────
GUEST_TTL_DAYS   = 7
MAX_REQ_PER_IP   = 3            # yêu cầu / IP / giờ
MAX_REQ_GLOBAL   = 20           # yêu cầu / giờ, toàn hệ thống
MIN_MESSAGE_LEN  = 10           # lời nhắn tối thiểu, chặn spam rỗng
SESSION_COOKIE   = "btcr_session"

ACCESS_FILE = DATA_DIR / "access.json"
SERVER_PID_FILE = DATA_DIR / "server.pid"
