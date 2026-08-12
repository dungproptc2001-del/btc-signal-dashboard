"""Mở Cloudflare quick tunnel để xem được từ ngoài internet.

Quick tunnel không cần tài khoản, nhưng URL đổi mỗi lần khởi động. Bot sẽ nhắn URL
mới vào Telegram nên chủ nhà luôn biết link hiện tại.

Có domain riêng rồi thì chuyển sang named tunnel: chỉ sửa file này, phần còn lại của
server không đổi.

Tunnel hỏng KHÔNG được làm sập server — trả None rồi chạy tiếp ở LAN.
"""
import os
import re
import shutil
import subprocess
import threading
import time

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# winget cài vào Program Files, thường chưa có trong PATH của session hiện tại
CANDIDATES = [
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\Program Files\cloudflared\cloudflared.exe",
]

_proc = None


def find_binary():
    exe = shutil.which("cloudflared")
    if exe:
        return exe
    return next((p for p in CANDIDATES if os.path.exists(p)), None)


def start(port, timeout=40):
    """Mở tunnel, trả URL công khai. None nếu không mở được."""
    global _proc

    exe = find_binary()
    if not exe:
        print("  [tunnel] Chưa cài cloudflared – chỉ chạy LAN. "
              "Cài: winget install Cloudflare.cloudflared")
        return None

    try:
        _proc = subprocess.Popen(
            [exe, "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except Exception as e:
        print(f"  [tunnel] Không chạy được cloudflared: {e}")
        return None

    url = {}

    def reader():
        for line in _proc.stdout:
            if "url" not in url:
                m = URL_RE.search(line)
                if m:
                    url["url"] = m.group(0)

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    deadline = time.time() + timeout
    while time.time() < deadline:
        if "url" in url:
            print(f"  [tunnel] {url['url']}")
            return url["url"]
        if _proc.poll() is not None:
            print("  [tunnel] cloudflared thoát sớm – chỉ chạy LAN.")
            return None
        time.sleep(0.4)

    print(f"  [tunnel] Quá {timeout}s chưa lấy được URL – chỉ chạy LAN.")
    return None


def stop():
    global _proc
    if _proc and _proc.poll() is None:
        try:
            _proc.terminate()
            _proc.wait(timeout=5)
        except Exception:
            try:
                _proc.kill()
            except Exception:
                pass
        print("  [tunnel] Đã đóng.")
    _proc = None


def is_running():
    return _proc is not None and _proc.poll() is None
