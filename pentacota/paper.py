"""Paper broker + risk gate. State is persisted to data/paper_state.json."""
import json, os, time, threading, datetime
from .config import DATA

STATE = os.path.join(DATA, "paper_state.json")
KILL = os.path.join(DATA, "KILL")

def kill_active(): return os.path.exists(KILL)
def set_kill(on):
    if on: open(KILL, "w").write(str(time.time()))
    elif os.path.exists(KILL): os.remove(KILL)

def _day(): return datetime.datetime.utcnow().strftime("%Y-%m-%d")

class Paper:
    def __init__(self, cfg):
        self.cfg, self.lock = cfg, threading.RLock()
        self.s = None
        if os.path.exists(STATE):
            try: self.s = json.load(open(STATE))
            except Exception: self.s = None
        if not self.s: self.reset()

    def reset(self):
        with self.lock:
            e = self.cfg["risk"]["start_equity"]
            self.s = {"balance": e, "start_equity": e, "positions": [], "closed": [], "day": _day(), "day_start": e, "next_id": 1}
            self._save()

    def _save(self):
        tmp = STATE + ".tmp"
        json.dump(self.s, open(tmp, "w"), indent=1); os.replace(tmp, STATE)

    def _roll_day(self):
        if self.s["day"] != _day():
            self.s["day"], self.s["day_start"] = _day(), self.equity({})

    def equity(self, prices):
        eq = self.s["balance"]
        for p in self.s["positions"]:
            px = prices.get(p["symbol"], p["entry"])
            eq += (px - p["entry"]) * p["units"] * p["dir"]
        return eq

    def day_pnl_pct(self, prices):
        return (self.equity(prices) / self.s["day_start"] - 1) * 100

    def can_open(self, sig, prices):
        R = self.cfg["risk"]; plan = sig["plan"]
        with self.lock:
            self._roll_day(); P = self.s["positions"]
            if kill_active(): return False, "kill switch is active"
            if self.day_pnl_pct(prices) <= -R["daily_loss_limit_pct"]: return False, "daily loss limit reached"
            if len(P) >= R["max_positions"]: return False, "max simultaneous positions reached"
            if any(p["symbol"] == sig["symbol"] for p in P): return False, "duplicate: position already open"
            now = time.time() * 1000
            if any(c["symbol"] == sig["symbol"] and now - c["closed_at"] < R["cooldown_min"] * 60000 for c in self.s["closed"][-30:]):
                return False, "cooldown after recent trade in this symbol"
            d = 1 if sig["direction"] == "LONG" else -1
            open_risk = sum(p["risk_amt"] for p in P) + plan["risk_amt"]
            if open_risk / self.equity(prices) * 100 > R["max_total_open_risk_pct"] + 1e-9: return False, "total open risk cap exceeded"
            return True, "ok"

    def open(self, sig, price):
        R = self.cfg["risk"]; plan = sig["plan"]
        d = 1 if sig["direction"] == "LONG" else -1
        fill = price * (1 + d * R["slippage_pct"] / 100)
        if (fill - plan["sl"]) * d <= 0: return None                      # already through the stop
        with self.lock:
            risk_dist = abs(fill - plan["sl"])
            units = min(plan["units"], plan["risk_amt"] / risk_dist)      # never exceed the planned risk
            pos = {"id": self.s["next_id"], "symbol": sig["symbol"], "dir": d, "entry": fill, "sl": plan["sl"],
                   "tp": plan["tp"], "units": units, "risk_amt": units * risk_dist, "opened_at": int(time.time() * 1000),
                   "score": sig["score"], "reason": sig["reason"], "rr": plan["rr"]}
            self.s["next_id"] += 1; self.s["positions"].append(pos); self._save()
            return pos

    def _close(self, pos, px, why):
        R = self.cfg["risk"]
        if why == "SL": px = px * (1 - pos["dir"] * R["slippage_pct"] / 100)
        gross = (px - pos["entry"]) * pos["units"] * pos["dir"]
        fees = R["fee_pct"] / 100 * (pos["entry"] + px) * pos["units"]
        pnl = gross - fees
        self.s["balance"] += pnl
        self.s["positions"] = [p for p in self.s["positions"] if p["id"] != pos["id"]]
        self.s["closed"].append({**pos, "exit": px, "pnl": pnl, "r": pnl / pos["risk_amt"] if pos["risk_amt"] else 0,
                                 "why": why, "closed_at": int(time.time() * 1000)})

    def update(self, last_px, candles15):
        """Check exits. Stops are never moved. Same-bar SL/TP ambiguity resolves to the stop (conservative)."""
        with self.lock:
            for p in list(self.s["positions"]):
                hit = None
                for c in candles15.get(p["symbol"], []):
                    if c["t"] + 900_000 <= p["opened_at"]: continue
                    sl_hit = c["l"] <= p["sl"] if p["dir"] == 1 else c["h"] >= p["sl"]
                    tp_hit = c["h"] >= p["tp"] if p["dir"] == 1 else c["l"] <= p["tp"]
                    if sl_hit: hit = ("SL", p["sl"]); break
                    if tp_hit: hit = ("TP", p["tp"]); break
                px = last_px.get(p["symbol"])
                if not hit and px is not None:
                    if (px <= p["sl"] if p["dir"] == 1 else px >= p["sl"]): hit = ("SL", p["sl"])
                    elif (px >= p["tp"] if p["dir"] == 1 else px <= p["tp"]): hit = ("TP", p["tp"])
                if hit: self._close(p, hit[1], hit[0])
            self._roll_day(); self._save()

    def flatten(self, last_px, why="KILL"):
        with self.lock:
            for p in list(self.s["positions"]):
                self._close(p, last_px.get(p["symbol"], p["entry"]), why)
            self._save()

    def snapshot(self, prices):
        with self.lock:
            closed = self.s["closed"]
            wins = [c for c in closed if c["pnl"] > 0]
            pos = [{**p, "last": prices.get(p["symbol"], p["entry"]),
                    "upnl": (prices.get(p["symbol"], p["entry"]) - p["entry"]) * p["units"] * p["dir"]} for p in self.s["positions"]]
            return {"equity": self.equity(prices), "balance": self.s["balance"], "start_equity": self.s["start_equity"],
                    "day_pnl_pct": self.day_pnl_pct(prices), "positions": pos, "closed": closed[-20:][::-1],
                    "trades": len(closed), "win_rate": (len(wins) / len(closed) * 100) if closed else None,
                    "kill": kill_active()}
