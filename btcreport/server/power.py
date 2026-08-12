"""Bật / tắt dịch vụ mà KHÔNG giết tiến trình.

Vì sao phải có tầng này: bot Telegram sống bên trong server. Giết tiến trình là giết
luôn tai nghe, không còn ai đọc `/on` để bật lại. Nên `/off` chỉ đưa server vào nghỉ —
đóng đường ra internet, dừng các nhịp nền — nhưng uvicorn vẫn chạy và bot vẫn poll.

Ba mức tắt, đừng lẫn:

    /pause /resume   chỉ dừng quét, web và link công khai vẫn sống
    /off   /on       nghỉ hẳn: đóng tunnel + dừng scheduler.  ← file này
    /stop            thoát tiến trình, chỉ bật lại được từ chính máy

Mặc định `/off` KHÔNG nhả keep-alive. Máy vẫn thức, vẫn tốn điện — đổi lại một bảo đảm
cứng: đã tắt được từ điện thoại thì luôn bật lại được từ điện thoại. Nhả keep-alive là
máy ngủ, bot câm, ông gõ /on vào khoảng không rồi phải mò về mở laptop. Một lệnh tắt mà
không chắc bật lại được thì tệ hơn là không có lệnh tắt. Ai muốn đổi ngược: --sleep-on-off
"""
import asyncio
from datetime import datetime

from .. import config          # đọc config.X tại thời điểm gọi, KHÔNG import giá trị:
                               # cờ --sleep-on-off gán sau lúc import, bind cứng là hỏng
from . import keepalive, scheduler, tunnel
from .state import STATE

# Cùng MỘT khoá cho cả hai chiều. Không có nó thì /on bấm 3 lần đẻ ra 3 bộ scheduler,
# mỗi bộ một vòng quét riêng, ghi đè last_signals.json của nhau.
_lock = asyncio.Lock()


def status():
    return {
        "standby": STATE.standby,
        "since":   STATE.standby_since.isoformat(timespec="seconds")
                   if STATE.standby_since else None,
    }


async def standby(port=None):
    """Đưa server vào nghỉ. Trả dict mô tả việc đã làm.

    Thứ tự có chủ đích: đóng đường ra ngoài TRƯỚC, dừng việc SAU. Ngược lại thì có
    một khoảng khách vẫn vào được trang mà dữ liệu đã ngừng cập nhật.
    """
    async with _lock:
        if STATE.standby:
            return {"changed": False, "standby": True}

        await asyncio.get_running_loop().run_in_executor(None, tunnel.stop)
        await scheduler.stop()

        released = False
        if config.SLEEP_ON_OFF:
            keepalive.release()
            released = True

        STATE.standby       = True
        STATE.standby_since = datetime.now()
        STATE.tunnel_url    = None
        STATE.publish("power", status())

        return {"changed": True, "standby": True, "keepalive_released": released}


async def wake(port=None):
    """Bật lại. Trả dict kèm URL công khai mới và có đổi so với cũ không."""
    async with _lock:
        if not STATE.standby:
            return {"changed": False, "standby": False, "url": STATE.tunnel_url}

        old_url = STATE.last_tunnel_url

        # Ngược thứ tự lúc nghỉ: dựng nền trước, mở đường ra ngoài sau.
        keepalive.hold()
        await scheduler.start()

        url = await asyncio.get_running_loop().run_in_executor(
            None, tunnel.start, port or config.SERVER_PORT)

        STATE.tunnel_url      = url
        STATE.last_tunnel_url = url or old_url
        STATE.standby         = False
        STATE.standby_since   = None
        STATE.publish("power", status())

        return {
            "changed":     True,
            "standby":     False,
            "url":         url,
            # Tailscale neo URL vào tên máy nên bật lại vẫn đúng địa chỉ cũ.
            # Cloudflare quick tunnel thì đổi — khách đã duyệt sẽ bấm vào link chết.
            "url_changed": bool(old_url and url and old_url != url),
            "provider":    config.TUNNEL_PROVIDER,
        }
