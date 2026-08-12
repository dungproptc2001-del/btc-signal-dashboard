"""FastAPI app: dashboard, API, SSE, luồng xin quyền truy cập."""
import asyncio
import json
import secrets
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import (
    HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse,
)
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from ..config import GUEST_TTL_DAYS, OWNER_KEY, SESSION_COOKIE
from ..service import journal
from . import access, bot
from .state import STATE

TEMPLATES = Path(__file__).resolve().parent / "templates"
STATIC    = Path(__file__).resolve().parent / "static"

# Route không cần đăng nhập
PUBLIC_PATHS = {"/healthz", "/login", "/access/request", "/access/status", "/favicon.ico"}

_env = Environment(loader=FileSystemLoader(TEMPLATES),
                   autoescape=select_autoescape(["html"]))


def _render(name, **ctx):
    """Nhúng CSS/JS vào trang.

    PHẢI bọc Markup. Autoescape đang bật cho .html, nên chuỗi thường sẽ bị escape:
    dấu nháy thành &#39;, dấu < thành &lt; — script chết ngay dòng đầu và CSS mất
    hết font-family. Đây là lỗi câm: trang vẫn trả về 200, vẫn đủ chữ, chỉ là
    không có gì chạy. Có test canh (test_render_dashboard).

    An toàn vì đây là file tĩnh của chính mình, không phải dữ liệu người dùng.
    """
    css = (STATIC / "dashboard.css").read_text(encoding="utf-8")
    js  = (STATIC / "dashboard.js").read_text(encoding="utf-8")
    return _env.get_template(name).render(
        inline_css=Markup(css), inline_js=Markup(js), **ctx)


_OWNER_SESSION_TOKEN = secrets.token_urlsafe(32)


LOCAL_HOSTS     = ("127.0.0.1", "::1", "localhost")
FORWARDED_HINTS = ("cf-connecting-ip", "x-forwarded-for", "x-real-ip",
                   "forwarded", "cf-ray")


def _is_owner_request(request):
    """Từ chính máy này thì luôn là chủ nhà – không phụ thuộc Telegram.

    Hai lớp, cố ý thừa:

    1. Bất kỳ header proxy nào xuất hiện → KHÔNG phải chủ nhà. Vì cloudflared
       kết nối vào server từ chính 127.0.0.1, nếu chỉ nhìn địa chỉ thì mọi khách
       trên internet đều thành chủ nhà.
    2. Sau đó mới xét địa chỉ thật sự là loopback.

    Thực tế uvicorn đã bật sẵn ProxyHeadersMiddleware nên `client.host` đã được
    thay bằng IP thật, và Cloudflare cũng chặn khách tự khai header. Nhưng đây là
    ranh giới quyền – không dựa vào mặc định ngầm của thư viện bên thứ ba.

    ĐÃ ĐO THẬT, không suy đoán (12/08/2026, request từ ngoài internet):

        Tailscale Funnel   client.host = 100.x.y.z (interface tailscale, KHÔNG
                           phải loopback) + có x-forwarded-for  → cả hai lớp đỡ
        Cloudflare tunnel  client.host = 127.0.0.1 + có cf-connecting-ip
                           → CHỈ lớp header đỡ

    Chú ý lớp header fail-safe đúng chiều: khách tự khai thêm x-forwarded-for chỉ
    làm mình bị loại khỏi quyền chủ nhà, không bao giờ được thêm quyền.

    Funnel còn bơm vào tailscale-user-login / -name / -profile-pic. ĐỪNG tin mấy
    header đó: với traffic công khai chúng không phải danh tính đã xác thực.

    Đổi provider tunnel là phải đo lại từ đầu.
    """
    if any(h in request.headers for h in FORWARDED_HINTS):
        return False
    host = (request.client.host if request.client else "") or ""
    return host in LOCAL_HOSTS


def _session_of(request):
    if _is_owner_request(request):
        return {"name": "Chủ nhà", "owner": True}

    cookie = request.cookies.get(SESSION_COOKIE)
    # Phiên chủ nhà cấp qua /login?key= không nằm trong access.json, phải kiểm riêng
    if cookie and secrets.compare_digest(cookie, _OWNER_SESSION_TOKEN):
        return {"name": "Chủ nhà", "owner": True}
    return access.check_session(cookie)


def _set_session_cookie(response, token, request):
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=GUEST_TTL_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


app = FastAPI(title="BTC Report Server", docs_url=None, redoc_url=None)


# ── GÁC CỬA ───────────────────────────────────────────────────────────────────
@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)

    if _session_of(request):
        return await call_next(request)

    # API trả JSON 401, trang HTML trả form xin quyền cho đẹp mắt
    if path.startswith("/api/") or path == "/events":
        return JSONResponse({"error": "Chưa có quyền truy cập.",
                             "hint": "Mở trang chủ để gửi yêu cầu."}, status_code=401)
    return HTMLResponse(_render("request_access.html"), status_code=200)


# ── TRANG ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    session = _session_of(request)
    return HTMLResponse(_render(
        "dashboard.html",
        viewer=session.get("name", "khách"),
        is_owner=bool(session.get("owner")),
        initial=json.dumps(STATE.public(), ensure_ascii=False),
    ))


@app.get("/report", response_class=HTMLResponse)
async def report_page():
    if not STATE.report_html:
        return HTMLResponse(
            "<body style='background:#0a0e1a;color:#e2e8f0;font-family:Segoe UI;"
            "padding:60px;text-align:center'>"
            "<h2>Báo cáo đang được dựng</h2>"
            "<p style='color:#64748b'>Lần đầu khởi động cần ~15 giây. Tải lại trang sau.</p>"
            "</body>", status_code=503)
    return HTMLResponse(STATE.report_html)


@app.get("/login")
async def login(request: Request, key: str = ""):
    """Cửa sau của chủ nhà – dùng khi Telegram hỏng hoặc vào từ máy khác."""
    if key and secrets.compare_digest(key, OWNER_KEY):
        resp = RedirectResponse("/", status_code=303)
        _set_session_cookie(resp, _OWNER_SESSION_TOKEN, request)
        return resp
    return HTMLResponse(_render("request_access.html"), status_code=200)


# ── API ───────────────────────────────────────────────────────────────────────
@app.get("/api/signals")
async def api_signals():
    return STATE.public()


@app.get("/api/report")
async def api_report():
    if not STATE.report_ctx:
        return JSONResponse({"error": "Chưa có báo cáo."}, status_code=503)
    return json.loads(json.dumps(STATE.report_ctx, default=str))


@app.get("/api/signals/history")
async def api_history(limit: int = 50, symbol: str = ""):
    """Nhật ký tín hiệu mua/bán. Khách đã duyệt xem được hết, như chủ nhà."""
    limit = max(1, min(limit, 500))
    return {"entries": journal.read(limit=limit, symbol=symbol or None)}


@app.get("/api/link")
async def api_link(request: Request):
    """Link công khai hiện tại – để shortcut ngoài desktop hỏi server chứ không
    đóng băng URL vào file (quick tunnel đổi URL mỗi lần khởi động).

    CHỈ chủ nhà. Cửa gác ở trên cho cả khách đã duyệt đi qua /api/*, nên phải
    kiểm quyền chủ nhà lần nữa ở đây.

    Không kèm OWNER_KEY: đây là link để gửi cho người khác. Lộ key là khách tự
    cấp quyền chủ nhà cho mình, thu hồi phiên cũng vô nghĩa.
    """
    session = _session_of(request)
    if not (session and session.get("owner")):
        return JSONResponse({"error": "Chỉ chủ nhà."}, status_code=403)
    return {"url": STATE.tunnel_url}


@app.get("/healthz")
async def healthz():
    s = STATE.public()["status"]
    return {"ok": True, "uptime_seconds": s["uptime_seconds"], "paused": s["paused"]}


# ── SSE ───────────────────────────────────────────────────────────────────────
@app.get("/events")
async def events(request: Request):
    q = STATE.subscribe()

    async def stream():
        try:
            yield f"event: hello\ndata: {json.dumps(STATE.public(), ensure_ascii=False)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"          # giữ kết nối qua proxy của Cloudflare
                    continue
                yield (f"event: {msg['event']}\n"
                       f"data: {json.dumps(msg['data'], ensure_ascii=False, default=str)}\n\n")
        finally:
            STATE.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ── LUỒNG XIN QUYỀN ───────────────────────────────────────────────────────────
def _client_ip(request):
    fwd = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


@app.post("/access/request")
async def request_access(request: Request, name: str = Form(""), message: str = Form("")):
    try:
        req = access.create_request(
            name, message,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent", "?"),
        )
    except access.InvalidRequest as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except access.RateLimited as e:
        # Chặn TRƯỚC khi gửi Telegram – nếu không thì bot làm ngập điện thoại chủ nhà
        return JSONResponse({"error": str(e)}, status_code=429)

    await asyncio.get_running_loop().run_in_executor(None, bot.notify_access_request, req)
    return {"request_id": req["id"], "status": "pending"}


@app.get("/access/status")
async def access_status(request: Request, id: str = ""):
    status, session = access.session_status(id)
    resp = JSONResponse({"status": status})
    if status == "approved" and session:
        _set_session_cookie(resp, session["token"], request)
    return resp
