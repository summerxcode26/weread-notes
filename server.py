#!/usr/bin/env python3
"""
Static file server with password protection and /api/refresh endpoint.
Usage: python3 server.py [port]
"""

import hashlib, hmac, http.server, json, os, secrets, sys, threading, urllib.parse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
ROOT = os.path.dirname(os.path.abspath(__file__))
PASSWORD = "Weread0517"

# Random secret per process — sessions invalidate on server restart
_SESSION_SECRET = secrets.token_hex(32)

def _make_token() -> str:
    return hmac.new(_SESSION_SECRET.encode(), b"weread-authed", hashlib.sha256).hexdigest()

def _check_cookie(headers) -> bool:
    raw = headers.get("Cookie", "")
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == "wr_session":
            return hmac.compare_digest(v.strip(), _make_token())
    return False

_refresh_lock = threading.Lock()
_refresh_running = False

LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>微信读书笔记 · 登录</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:#0f0f13;font-family:-apple-system,'PingFang SC',sans-serif;}
.card{background:#1a1a22;border:1px solid #2e2e40;border-radius:16px;
  padding:44px 40px;width:360px;text-align:center;
  box-shadow:0 24px 80px rgba(0,0,0,0.6);}
.glow{position:fixed;top:-200px;left:50%;transform:translateX(-50%);
  width:700px;height:400px;
  background:radial-gradient(ellipse,rgba(124,106,247,.12) 0%,transparent 70%);
  pointer-events:none;}
h1{font-size:1.4rem;font-weight:700;margin-bottom:6px;
  background:linear-gradient(135deg,#c4b9ff,#7c6af7,#3fc8f2);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
p{font-size:.85rem;color:#8888aa;margin-bottom:28px;}
input{width:100%;padding:12px 16px;background:#22222e;border:1px solid #2e2e40;
  border-radius:9px;color:#e8e8f0;font-size:1rem;font-family:inherit;
  outline:none;transition:border-color .2s;text-align:center;letter-spacing:.1em;}
input:focus{border-color:#7c6af7;}
input::placeholder{letter-spacing:0;color:#555570;}
.err{color:#f2564f;font-size:.8rem;margin-top:10px;min-height:20px;}
button{width:100%;margin-top:18px;padding:13px;background:linear-gradient(135deg,#7c6af7,#5a4de0);
  border:none;border-radius:9px;color:#fff;font-size:.95rem;font-weight:600;
  cursor:pointer;font-family:inherit;transition:opacity .2s;}
button:hover{opacity:.88;}
</style>
</head>
<body>
<div class="glow"></div>
<div class="card">
  <h1>📝 微信读书笔记</h1>
  <p>请输入访问密码</p>
  <form method="POST" action="/login">
    <input type="password" name="pwd" placeholder="密码" autofocus autocomplete="current-password">
    <div class="err">ERRMSG</div>
    <button type="submit">进入</button>
  </form>
</div>
</body>
</html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    # ── Auth helpers ──────────────────────────────
    def _authed(self):
        return _check_cookie(self.headers)

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _serve_login(self, error=""):
        html = LOGIN_HTML.replace("ERRMSG", error).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    # ── GET ───────────────────────────────────────
    def do_GET(self):
        if self.path.startswith("/login"):
            self._serve_login()
            return
        if not self._authed():
            self._redirect("/login")
            return
        if self.path == "/api/refresh":
            self._handle_refresh()
        else:
            super().do_GET()

    # ── POST ──────────────────────────────────────
    def do_POST(self):
        if self.path == "/login":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            params = urllib.parse.parse_qs(body)
            pwd = params.get("pwd", [""])[0]
            if hmac.compare_digest(pwd, PASSWORD):
                token = _make_token()
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie",
                    f"wr_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")
                self.end_headers()
            else:
                self._serve_login("密码错误，请重试")
        else:
            self.send_response(405)
            self.end_headers()

    # ── /api/refresh ──────────────────────────────
    def _handle_refresh(self):
        global _refresh_running
        with _refresh_lock:
            if _refresh_running:
                self._json({"status": "running", "updated": False, "message": "同步中，请稍候..."})
                return
            _refresh_running = True

        def run():
            global _refresh_running
            try:
                import fetch_data
                count = fetch_data.run()
                print(f"[refresh] done — {count} notes")
            except Exception as e:
                print(f"[refresh] error: {e}")
            finally:
                _refresh_running = False

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=3)
        if t.is_alive():
            self._json({"status": "running", "updated": False, "message": "同步中，完成后请手动刷新页面"})
        else:
            self._json({"status": "ok", "updated": True, "message": "同步完成，正在刷新..."})

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        msg = args[0] if args else ""
        if "/api/" in msg or "POST" in msg or "login" in msg:
            super().log_message(fmt, *args)


if __name__ == "__main__":
    os.chdir(ROOT)
    print(f"WeRead Notes  →  http://localhost:{PORT}")
    print(f"Password: {PASSWORD}")
    print("Press Ctrl+C to stop.\n")
    with http.server.ThreadingHTTPServer(("", PORT), Handler) as srv:
        srv.serve_forever()
