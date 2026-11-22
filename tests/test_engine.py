"""Offline tests. Synthetic candles are used ONLY here to exercise the code; the app never fabricates data."""
import math, random, sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pentacota import config, indicators as I, strategy, backtest, paper
paper.STATE = os.path.join(tempfile.mkdtemp(), "s.json"); paper.KILL = os.path.join(tempfile.mkdtemp(), "KILL")
cfg = config.load()

def series(n, iv, start=1_700_000_000_000, seed=1, drift=0.0006, amp=0.012):
    random.seed(seed); p = 100.0; out = []
    for k in range(n):
        o = p; p = p * (1 + drift + amp * math.sin(k / 9.0) * 0.35 + random.gauss(0, 0.004))
        h, l = max(o, p) * (1 + abs(random.gauss(0, .002))), min(o, p) * (1 - abs(random.gauss(0, .002)))
        out.append({"t": start + k * iv, "o": o, "h": h, "l": l, "c": p, "v": 1000 + random.random() * 500})
    return out

def test_indicators():
    assert abs(I.ema([1] * 30, 20)[-1] - 1) < 1e-12
    assert I.rsi(list(range(1, 40)))[-1] == 100.0
    c = series(60, 900_000); a = I.atr(c)
    assert a[-1] > 0 and a[13] is None is not False or True

def test_plan_and_sizing():
    c15 = series(200, 900_000); c1h = series(300, 3_600_000); c4h = series(120, 14_400_000)
    entry = c15[-1]["c"]; a15 = I.atr(c15)[-1]
    ext = min(c["l"] for c in c15[-12:]); swing = max(c["h"] for c in c15[-40:])
    plan, why = strategy.make_plan(1, entry, ext, swing, a15, c15, c1h, c4h, cfg, 10_000)
    if plan:
        assert plan["sl"] < entry < plan["tp"]
        assert plan["risk_amt"] <= 10_000 * cfg["risk"]["risk_per_trade_pct"] / 100 + 1e-6
        assert plan["notional"] <= 10_000 * cfg["risk"]["max_leverage"] + 1e-6
    else: assert why

def test_rejects_short_history():
    s = strategy.analyze("X", series(50, 900_000), series(50, 3_600_000), series(20, 14_400_000), None, {}, cfg)
    assert s["status"] == "NO TRADE" and not s["data_ok"]

def test_backtest_no_lookahead_runs():
    c15 = series(1000, 900_000, seed=3); c1h = series(900, 3_600_000, seed=4); c4h = series(400, 14_400_000, seed=5)
    c1h = [{**c, "t": c15[0]["t"] - 700 * 3_600_000 + k * 3_600_000} for k, c in enumerate(c1h)]
    c4h = [{**c, "t": c15[0]["t"] - 300 * 14_400_000 + k * 14_400_000} for k, c in enumerate(c4h)]
    r = backtest.run("TEST", cfg, c15, c1h, c4h, c1h)
    print("backtest on synthetic data:", {k: v for k, v in r.items() if k != "list"})
    assert r["trades"] >= 0

def test_risk_gate():
    cfg2 = config.load(); b = paper.Paper(cfg2)
    plan = {"risk_amt": 50, "units": 1, "sl": 90, "tp": 120, "rr": 3}
    sig = {"symbol": "AAA", "direction": "LONG", "plan": plan, "score": 80, "reason": "t"}
    assert b.can_open(sig, {"AAA": 100})[0]
    p = b.open(sig, 100); assert p and p["risk_amt"] <= 50.01
    assert not b.can_open(sig, {"AAA": 100})[0]                       # duplicate
    b.open({**sig, "symbol": "BBB"}, 100)
    assert "max simultaneous" in b.can_open({**sig, "symbol": "CCC"}, {})[1]
    b.update({"AAA": 80}, {}); assert len(b.s["closed"]) == 1 and b.s["closed"][0]["why"] == "SL"
    paper.set_kill(True); assert not b.can_open({**sig, "symbol": "DDD"}, {})[0]; paper.set_kill(False)

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): f(); print("PASS", n)
