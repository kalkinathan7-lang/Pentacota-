import json, os, threading, mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from . import config, paper as P, backtest
from .scanner import Scanner

STATIC = os.path.join(config.ROOT, "static")
cfg = config.load()
scanner = Scanner(cfg)
bt = {"running": False, "result": None, "error": None}

def _run_bt(symbols):
    bt.update(running=True, result=None, error=None)
    try: bt["result"] = [backtest.run(s.upper(), cfg) for s in symbols]
    except Exception as e: bt["error"] = f"{type(e).__name__}: {e}"
    bt["running"] = False

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj, code=200):
        b = json.dumps(obj, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}
    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/state": return self._send(scanner.snapshot())
        if p.startswith("/api/coin/"):
            d = scanner.detail.get(p.split("/")[-1].upper())
            return self._send(d or {"error": "not scanned"}, 200 if d else 404)
        if p == "/api/backtest": return self._send(bt)
        f = os.path.join(STATIC, "index.html" if p in ("/", "") else p.lstrip("/"))
        if os.path.commonpath([STATIC, os.path.abspath(f)]) == STATIC and os.path.isfile(f):
            b = open(f, "rb").read()
            self.send_response(200); self.send_header("Content-Type", mimetypes.guess_type(f)[0] or "text/plain")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else: self._send({"error": "not found"}, 404)
    def do_POST(self):
        p = urlparse(self.path).path; b = self._body()
        if p == "/api/scanner/start": scanner.start()
        elif p == "/api/scanner/stop": scanner.stop()
        elif p == "/api/kill":
            on = bool(b.get("on", True)); P.set_kill(on)
            if on: scanner.paper.flatten(scanner.prices)
        elif p == "/api/paper/reset": scanner.paper.reset()
        elif p == "/api/backtest":
            if bt["running"]: return self._send({"error": "backtest already running"}, 409)
            syms = [s for s in b.get("symbols", ["BTC"]) if s.isalnum()][:5]
            threading.Thread(target=_run_bt, args=(syms,), daemon=True).start()
        else: return self._send({"error": "not found"}, 404)
        self._send({"ok": True})

def main():
    h, p = cfg["server"]["host"], cfg["server"]["port"]
    print(f"Pentacota ({cfg['mode']['trading']} mode) -> http://{h}:{p}")
    ThreadingHTTPServer((h, p), H).serve_forever()
