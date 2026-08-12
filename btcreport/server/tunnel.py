"""Mở server ra internet. Hai nhà cung cấp, chọn bằng TUNNEL_PROVIDER trong .env.

    tailscale   URL CỐ ĐỊNH  https://<ten-may>.<tailnet>.ts.net   ← mặc định
    cloudflare  URL ĐỔI mỗi lần khởi động, không cần tài khoản

Vì sao mặc định là tailscale: quick tunnel của Cloudflare là loại ẩn danh nên
Cloudflare phát tên ngẫu nhiên rồi thu lại khi ngắt — khách được duyệt hôm nay
mai phải xin link mới. Tailscale neo URL vào tên máy trong tailnet nên link giữ
nguyên qua mọi lần khởi động lại.

CẢNH BÁO cho người sửa file này: mọi tunnel đều proxy vào server từ 127.0.0.1.
Cửa chặn chủ nhà (app.py::_is_owner_request) vì thế KHÔNG được chỉ nhìn địa chỉ.
Đổi provider là phải đo lại header mà provider mới gửi vào — xem
tests/test_api.py::test_co_header_proxy_thi_KHONG_phai_chu_nha.

Tunnel hỏng KHÔNG được làm sập server — trả None rồi chạy tiếp ở LAN.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time

from ..config import TUNNEL_PROVIDER

CF_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# winget cài vào Program Files, thường chưa có trong PATH của session hiện tại
CF_CANDIDATES = [
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\Program Files\cloudflared\cloudflared.exe",
]
TS_CANDIDATES = [
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files (x86)\Tailscale\tailscale.exe",
]

_proc = None          # tiến trình cloudflared (tailscale không cần giữ tiến trình)
_provider = None      # provider đã mở thành công, để stop() biết phải dọn gì


def _find(name, candidates):
    exe = shutil.which(name)
    if exe:
        return exe
    return next((p for p in candidates if os.path.exists(p)), None)


def find_binary(provider=None):
    provider = provider or TUNNEL_PROVIDER
    if provider == "tailscale":
        return _find("tailscale", TS_CANDIDATES)
    return _find("cloudflared", CF_CANDIDATES)


# ── TAILSCALE ────────────────────────────────────────────────────────────────
def _ts_run(exe, *args, timeout=30):
    """Gọi tailscale CLI, trả (rc, output). Không bao giờ ném ra ngoài."""
    try:
        p = subprocess.run([exe, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return -1, str(e)


def _ts_hostname(exe):
    """Tên miền cố định của máy này trong tailnet, ví dụ laptop-abc.tailXXXX.ts.net."""
    rc, out = _ts_run(exe, "status", "--json")
    if rc != 0:
        return None, f"tailscale status lỗi: {out.strip()[:200]}"
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None, "tailscale status trả về không phải JSON"

    if data.get("BackendState") != "Running":
        return None, (f"tailscale chưa đăng nhập (BackendState="
                      f"{data.get('BackendState')}). Chạy: tailscale up")

    name = (data.get("Self") or {}).get("DNSName", "").rstrip(".")
    if not name:
        return None, "tailscale chưa có MagicDNS name – bật MagicDNS trong admin console"
    return name, None


def _ts_start(port):
    exe = find_binary("tailscale")
    if not exe:
        print("  [tunnel] Chưa cài tailscale – chỉ chạy LAN. "
              "Cài: winget install tailscale.tailscale")
        return None

    host, err = _ts_hostname(exe)
    if err:
        print(f"  [tunnel] {err}")
        return None

    # --bg: funnel chạy nền và CẤU HÌNH ĐƯỢC GHI LẠI, sống qua cả reboot.
    # Gọi lại khi đã bật sẵn thì tailscale coi như no-op, không nhân đôi.
    rc, out = _ts_run(exe, "funnel", "--bg", str(port), timeout=45)
    if rc != 0:
        low = out.lower()
        if "funnel is not enabled" in low:
            link = re.search(r"https://login\.tailscale\.com/\S+", out)
            print("  [tunnel] Funnel chưa bật cho tailnet này. Bật tại:")
            print(f"           {link.group(0) if link else 'https://login.tailscale.com/admin/settings/keys'}")
        else:
            print(f"  [tunnel] Bật funnel không được: {out.strip()[:300]}")
        return None

    url = f"https://{host}"
    print(f"  [tunnel] {url}  (cố định)")
    return url


def _ts_stop():
    """Tắt funnel để khách gặp lỗi kết nối thay vì trang 502 khó hiểu."""
    exe = find_binary("tailscale")
    if not exe:
        return
    rc, out = _ts_run(exe, "funnel", "--https=443", "off", timeout=20)
    print("  [tunnel] Đã tắt funnel." if rc == 0
          else f"  [tunnel] Tắt funnel không được: {out.strip()[:200]}")


# ── CLOUDFLARE QUICK TUNNEL ──────────────────────────────────────────────────
def _cf_start(port, timeout):
    global _proc

    exe = find_binary("cloudflare")
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
                m = CF_URL_RE.search(line)
                if m:
                    url["url"] = m.group(0)

    threading.Thread(target=reader, daemon=True).start()

    deadline = time.time() + timeout
    while time.time() < deadline:
        if "url" in url:
            print(f"  [tunnel] {url['url']}  (đổi mỗi lần khởi động)")
            return url["url"]
        if _proc.poll() is not None:
            print("  [tunnel] cloudflared thoát sớm – chỉ chạy LAN.")
            return None
        time.sleep(0.4)

    print(f"  [tunnel] Quá {timeout}s chưa lấy được URL – chỉ chạy LAN.")
    return None


def _cf_stop():
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


# ── API CHUNG ────────────────────────────────────────────────────────────────
def start(port, timeout=40, provider=None):
    """Mở tunnel, trả URL công khai. None nếu không mở được."""
    global _provider
    provider = provider or TUNNEL_PROVIDER

    url = _ts_start(port) if provider == "tailscale" else _cf_start(port, timeout)
    _provider = provider if url else None
    return url


def stop():
    if _provider == "tailscale":
        _ts_stop()
    else:
        _cf_stop()


def is_running():
    if _provider == "tailscale":
        return True     # funnel do tailscaled giữ, không phải tiến trình con của ta
    return _proc is not None and _proc.poll() is None
