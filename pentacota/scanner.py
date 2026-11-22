import threading, time, json, os, traceback
from concurrent.futures import ThreadPoolExecutor
from . import data, paper as P
from .strategy import analyze, btc_state
from .config import DATA

class Scanner:
    def __init__(self, cfg):
        self.cfg, self.paper = cfg, P.Paper(cfg)
        self.running, self.thread = False, None
        self.lock = threading.Lock()
        self.rows, self.detail, self.btc, self.error = [], {}, None, None
        self.prices, self.last_scan, self.scanned, self.cycle_ms = {}, None, 0, 0
        self.log = []

    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True); self.thread.start()

    def stop(self): self.running = False

    def _loop(self):
        while self.running:
            t0 = time.time()
            try: self.scan_once(); self.error = None
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"; traceback.print_exc()
            self.cycle_ms = int((time.time() - t0) * 1000)
            for _ in range(self.cfg["scanner"]["interval_sec"]):
                if not self.running: break
                time.sleep(1)

    def _one(self, r, btc, equity):
        q = self.cfg["exchange"]["quote"]; sym = r["base"]
        try:
            c15 = data.get_candles(sym, q, "15m", 200); c1h = data.get_candles(sym, q, "1h", 300)
            c4h = data.get_candles(sym, q, "4h", 120)
            s = analyze(sym, c15, c1h, c4h, btc, {"qv": r["qv"], "spread_pct": r["spread_pct"]}, self.cfg, price=r["last"], equity=equity)
            return s, c15
        except Exception as e:                      # missing / stale / unreliable data -> reject the setup
            return {"symbol": sym, "status": "NO TRADE", "score": 0, "reason": f"data unavailable: {e}", "trend": "-",
                    "ind": {"price": r["last"], "quote_volume_24h": r["qv"]}, "checks": [], "parts": {}, "plan": None,
                    "direction": None, "invalidation": [], "data_ok": False}, []

    def scan_once(self):
        cfg = self.cfg; q = cfg["exchange"]["quote"]
        coins = data.top_symbols(cfg)
        btc = btc_state(data.get_candles("BTC", q, "1h", 300))
        prices = {r["base"]: r["last"] for r in coins}
        eq = self.paper.equity(prices)
        with ThreadPoolExecutor(cfg["scanner"]["workers"]) as ex:
            res = list(ex.map(lambda r: self._one(r, btc, eq), coins))
        c15s = {s["symbol"]: c for s, c in res}
        sigs = [s for s, _ in res]
        for s, r in zip(sigs, coins):
            s["rsi"] = s["ind"].get("rsi_1h"); s["price"] = r["last"]; s["volume"] = r["qv"]
        order = {"LONG": 0, "SHORT": 0, "WAITING": 1, "NO TRADE": 2}
        sigs.sort(key=lambda s: (order[s["status"]], -s["score"]))
        self.paper.update(prices, c15s)
        valid = [s for s in sigs if s["status"] in ("LONG", "SHORT")]
        for s in valid:
            self._audit(s)
            if cfg["mode"]["auto_paper_trade"] and cfg["mode"]["trading"] == "paper":
                ok, why = self.paper.can_open(s, prices)
                if ok: self.paper.open(s, prices[s["symbol"]])
                else: s["blocked"] = why
        with self.lock:
            self.rows, self.btc, self.prices = sigs, btc, prices
            self.detail = {s["symbol"]: s for s in sigs}
            self.scanned, self.last_scan = len(coins), int(time.time() * 1000)

    def _audit(self, s):
        try:
            with open(os.path.join(DATA, "signals.jsonl"), "a") as f:
                f.write(json.dumps({"ts": int(time.time() * 1000), "symbol": s["symbol"], "status": s["status"],
                                    "score": s["score"], "plan": s["plan"], "ind": s["ind"], "reason": s["reason"]}) + "\n")
        except Exception: pass

    def snapshot(self):
        with self.lock:
            rows = [{k: s.get(k) for k in ("symbol", "price", "trend", "rsi", "volume", "score", "status", "reason", "blocked")} for s in self.rows]
            cnt = lambda st: sum(1 for s in self.rows if s["status"] == st)
            return {"running": self.running, "error": self.error, "last_scan": self.last_scan, "cycle_ms": self.cycle_ms,
                    "scanned": self.scanned, "valid": cnt("LONG") + cnt("SHORT"), "waiting": cnt("WAITING"),
                    "btc": self.btc, "rows": rows, "mode": self.cfg["mode"]["trading"],
                    "account": self.paper.snapshot(self.prices)}
