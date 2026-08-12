"""Web server: dashboard trực tiếp + duyệt truy cập qua Telegram.

    python -m apps.server [--port 8000] [--host 0.0.0.0]
                          [--no-tunnel] [--allow-sleep]

Gộp cả ba việc vào một process: phục vụ web, quét tín hiệu 15 phút, dựng báo cáo
4 tiếng. Chạy cái này thì không cần chạy apps.monitor nữa — hai bên sẽ ghi đè state
của nhau.

Tắt server: scripts\\server_stop.bat, hoặc gõ /stop trong Telegram, hoặc Ctrl+C.
"""
import argparse
import asyncio
import atexit
import os
import signal
import sys

import uvicorn

from btcreport.config import OWNER_KEY, SERVER_HOST, SERVER_PID_FILE, SERVER_PORT
from btcreport.server import bot, keepalive, scheduler, tunnel
from btcreport.server.app import app
from btcreport.server.state import STATE

_stop_event = None


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="apps.server", description=__doc__)
    p.add_argument("--port", type=int, default=SERVER_PORT)
    p.add_argument("--host", default=SERVER_HOST)
    p.add_argument("--no-tunnel", action="store_true",
                   help="Không mở ra internet, chỉ chạy nội bộ / LAN")
    p.add_argument("--allow-sleep", action="store_true",
                   help="Không giữ máy thức (web sẽ sập khi máy ngủ)")
    return p.parse_args(argv)


# ── PID ───────────────────────────────────────────────────────────────────────
def write_pid():
    SERVER_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(remove_pid)


def remove_pid():
    try:
        SERVER_PID_FILE.unlink()
    except OSError:
        pass


def shutdown_all():
    """Dọn theo thứ tự ngược lúc bật. Gọi nhiều lần cũng không sao."""
    tunnel.stop()
    keepalive.release()
    remove_pid()


async def serve(args):
    global _stop_event
    _stop_event = asyncio.Event()

    # 1. Giữ máy thức — nếu không, máy ngủ sau 5 phút là web sập
    if args.allow_sleep:
        print("  [keepalive] Bỏ qua theo yêu cầu (--allow-sleep).")
    else:
        keepalive.hold()

    # 2. Mở tunnel ra internet
    if not args.no_tunnel:
        STATE.tunnel_url = await asyncio.get_running_loop().run_in_executor(
            None, tunnel.start, args.port)
    else:
        print("  [tunnel] Bỏ qua theo yêu cầu (--no-tunnel).")

    # 3. Nhịp nền + bot
    await scheduler.start()
    bot_task = asyncio.create_task(bot.poll_loop(_stop_event))

    # 4. Uvicorn
    config = uvicorn.Config(app, host=args.host, port=args.port,
                            log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    print()
    print("=" * 60)
    print("  BTC Web Server")
    print(f"  Trong máy : http://localhost:{args.port}")
    if STATE.tunnel_url:
        print(f"  Công khai : {STATE.tunnel_url}")
        print(f"  Vào thẳng : {STATE.tunnel_url}/login?key={OWNER_KEY}")
    print(f"  PID       : {os.getpid()}")
    print("=" * 60)
    print()

    await asyncio.get_running_loop().run_in_executor(
        None, bot.notify_startup, STATE.tunnel_url, args.port)

    # Chờ tới khi ai đó bấm dừng (Ctrl+C, /stop, hoặc taskkill)
    stop_task = asyncio.create_task(_stop_event.wait())
    done, _ = await asyncio.wait([server_task, stop_task],
                                return_when=asyncio.FIRST_COMPLETED)

    print("\nĐang tắt server...")
    server.should_exit = True
    bot_task.cancel()
    await scheduler.stop()
    for t in (server_task, bot_task, stop_task):
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    shutdown_all()
    print("Đã tắt sạch.")


def main(argv=None):
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    write_pid()

    def on_signal(signum, frame):
        print(f"\nNhận signal {signum} – dừng.")
        if _stop_event and not _stop_event.is_set():
            _stop_event._loop.call_soon_threadsafe(_stop_event.set)
        else:
            shutdown_all()
            sys.exit(0)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, on_signal)
        except (ValueError, OSError):
            pass

    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        print("\nCtrl+C – dừng.")
    finally:
        shutdown_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
