"""Quyền truy cập: yêu cầu, duyệt, phiên, thu hồi.

Luồng như request access của Google Docs: khách để lại tên + lời nhắn, chủ nhà nhận
thông báo Telegram và bấm duyệt hoặc từ chối.

CHỐT CHẶN QUAN TRỌNG NHẤT: mọi hành động đặc quyền đều phải đi qua `is_owner()`.
Bot Telegram công khai – ai cũng nhắn được. Không kiểm chat_id thì người lạ chỉ cần
gửi đúng callback data là tự duyệt cho chính mình.
"""
import json
import os
import secrets
import threading
from datetime import datetime, timedelta

from ..config import (
    ACCESS_FILE, GUEST_TTL_DAYS, MAX_REQ_GLOBAL, MAX_REQ_PER_IP,
    MIN_MESSAGE_LEN, TELEGRAM_CHAT_ID,
)

_LOCK = threading.RLock()


class RateLimited(Exception):
    """Quá nhiều yêu cầu – không gửi Telegram nữa để khỏi làm ngập điện thoại."""


class InvalidRequest(Exception):
    """Tên hoặc lời nhắn không hợp lệ."""


# ── CHỐT CHẶN ─────────────────────────────────────────────────────────────────
def is_owner(chat_id):
    """Chat này có phải chủ nhà không.

    So bằng chuỗi vì Telegram trả int còn config đọc từ .env ra str.
    """
    return chat_id is not None and str(chat_id) == str(TELEGRAM_CHAT_ID)


# ── LƯU TRỮ ───────────────────────────────────────────────────────────────────
def _empty():
    return {"sessions": [], "pending": [], "history": []}


def load(path=None):
    path = path or ACCESS_FILE
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for k in ("sessions", "pending", "history"):
                data.setdefault(k, [])
            return data
        except Exception:
            pass
    return _empty()


def save(data, path=None):
    """Ghi atomic – kill giữa chừng không làm hỏng danh sách quyền."""
    path = path or ACCESS_FILE
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _now():
    return datetime.now()


def _iso(dt):
    return dt.isoformat(timespec="seconds")


# ── YÊU CẦU TRUY CẬP ──────────────────────────────────────────────────────────
def create_request(name, message, ip="?", user_agent="?", path=None):
    """Tạo yêu cầu mới. Raise InvalidRequest / RateLimited."""
    name    = (name or "").strip()
    message = (message or "").strip()

    if not name:
        raise InvalidRequest("Cần nhập tên.")
    if len(name) > 60:
        raise InvalidRequest("Tên dài quá (tối đa 60 ký tự).")
    if len(message) < MIN_MESSAGE_LEN:
        raise InvalidRequest(f"Lời nhắn cần ít nhất {MIN_MESSAGE_LEN} ký tự "
                             f"để tôi biết bạn là ai.")
    if len(message) > 500:
        raise InvalidRequest("Lời nhắn dài quá (tối đa 500 ký tự).")

    with _LOCK:
        data  = load(path)
        limit = _now() - timedelta(hours=1)
        recent = [r for r in data["pending"] + data["history"]
                  if _parse(r.get("created_at")) and _parse(r["created_at"]) > limit]

        if len(recent) >= MAX_REQ_GLOBAL:
            raise RateLimited("Hệ thống đang nhận quá nhiều yêu cầu. Thử lại sau 1 giờ.")
        if len([r for r in recent if r.get("ip") == ip]) >= MAX_REQ_PER_IP:
            raise RateLimited("Bạn đã gửi quá nhiều yêu cầu. Thử lại sau 1 giờ.")

        req = {
            "id":         secrets.token_urlsafe(9),
            "name":       name,
            "message":    message,
            "ip":         ip,
            "ua":         (user_agent or "?")[:200],
            "created_at": _iso(_now()),
            "status":     "pending",
        }
        data["pending"].append(req)
        save(data, path)
        return req


def _parse(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def get_request(request_id, path=None):
    data = load(path)
    for r in data["pending"]:
        if r["id"] == request_id:
            return r
    for r in data["history"]:
        if r["id"] == request_id:
            return r
    return None


# ── DUYỆT / TỪ CHỐI ───────────────────────────────────────────────────────────
def approve(request_id, by_chat_id, ttl_days=GUEST_TTL_DAYS, path=None):
    """Duyệt yêu cầu, trả về session. Không phải chủ nhà thì trả None."""
    if not is_owner(by_chat_id):
        print(f"  [access] TỪ CHỐI duyệt: chat_id lạ {by_chat_id!r}")
        return None

    with _LOCK:
        data = load(path)
        req  = next((r for r in data["pending"] if r["id"] == request_id), None)
        if req is None:
            return None

        now     = _now()
        session = {
            "id":         req["id"],
            "token":      secrets.token_urlsafe(32),
            "name":       req["name"],
            "message":    req["message"],
            "ip":         req["ip"],
            "ua":         req["ua"],
            "granted_at": _iso(now),
            "expires_at": _iso(now + timedelta(days=ttl_days)),
            "revoked":    False,
        }
        data["sessions"].append(session)
        data["pending"].remove(req)
        req["status"] = "approved"
        data["history"].append(req)
        save(data, path)
        return session


def deny(request_id, by_chat_id, path=None):
    if not is_owner(by_chat_id):
        print(f"  [access] TỪ CHỐI hành động: chat_id lạ {by_chat_id!r}")
        return False

    with _LOCK:
        data = load(path)
        req  = next((r for r in data["pending"] if r["id"] == request_id), None)
        if req is None:
            return False
        data["pending"].remove(req)
        req["status"] = "denied"
        data["history"].append(req)
        save(data, path)
        return True


# ── PHIÊN ─────────────────────────────────────────────────────────────────────
def check_session(token, path=None):
    """Phiên còn hiệu lực thì trả về nó, không thì None."""
    if not token:
        return None
    now = _now()
    for s in load(path)["sessions"]:
        if secrets.compare_digest(s["token"], token):
            if s.get("revoked"):
                return None
            exp = _parse(s["expires_at"])
            if exp and exp < now:
                return None
            return s
    return None


def session_status(request_id, path=None):
    """Trạng thái yêu cầu cho khách poll: pending / approved / denied / unknown."""
    data = load(path)
    for s in data["sessions"]:
        if s["id"] == request_id and not s.get("revoked"):
            return "approved", s
    if any(r["id"] == request_id for r in data["pending"]):
        return "pending", None
    for r in data["history"]:
        if r["id"] == request_id:
            return r.get("status", "denied"), None
    return "unknown", None


def list_guests(path=None):
    """Khách còn quyền, kèm số giờ còn lại."""
    now, out = _now(), []
    for s in load(path)["sessions"]:
        if s.get("revoked"):
            continue
        exp = _parse(s["expires_at"])
        if exp and exp < now:
            continue
        out.append({**{k: s[k] for k in ("id", "name", "message", "ip", "granted_at")},
                    "hours_left": round((exp - now).total_seconds() / 3600, 1) if exp else None})
    return out


def revoke(session_id, by_chat_id, path=None):
    if not is_owner(by_chat_id):
        print(f"  [access] TỪ CHỐI thu hồi: chat_id lạ {by_chat_id!r}")
        return False

    with _LOCK:
        data = load(path)
        for s in data["sessions"]:
            if s["id"] == session_id and not s.get("revoked"):
                s["revoked"] = True
                s["revoked_at"] = _iso(_now())
                save(data, path)
                return True
        return False


def purge_expired(path=None):
    """Dọn phiên hết hạn và yêu cầu treo quá 24 giờ. Trả số bản ghi đã bỏ."""
    with _LOCK:
        data = load(path)
        now  = _now()
        before = len(data["sessions"]) + len(data["pending"])

        data["sessions"] = [
            s for s in data["sessions"]
            if not s.get("revoked") and (_parse(s["expires_at"]) or now) >= now
        ]
        stale = now - timedelta(hours=24)
        keep, expired = [], []
        for r in data["pending"]:
            created = _parse(r.get("created_at"))
            (keep if not created or created > stale else expired).append(r)
        for r in expired:
            r["status"] = "expired"
        data["pending"] = keep
        data["history"].extend(expired)
        data["history"] = data["history"][-200:]      # không để lịch sử phình vô hạn

        save(data, path)
        return before - (len(data["sessions"]) + len(data["pending"]))
