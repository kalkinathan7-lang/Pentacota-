"""Walk-forward backtest using the SAME analyze() as the live scanner. No look-ahead: each decision sees only
candles that had closed; entries fill at the NEXT 15m open; same-bar SL/TP resolves to the stop."""
from .data import get_candles, IV_MS
from .strategy import analyze, btc_state

def _view(c, upto_ms, iv, ptr):
    while ptr[0] < len(c) and c[ptr[0]]["t"] + iv <= upto_ms: ptr[0] += 1
    return c[:ptr[0]]

def run(base, cfg, c15=None, c1h=None, c4h=None, b1h=None, max_bars=None):
    q = cfg["exchange"]["quote"]; R = cfg["risk"]
    c15 = c15 or get_candles(base, q, "15m", 1000, False); c1h = c1h or get_candles(base, q, "1h", 1000, False)
    c4h = c4h or get_candles(base, q, "4h", 500, False)
    b1h = b1h or (c1h if base == "BTC" else get_candles("BTC", q, "1h", 1000, False))
    p1, p4, pb = [0], [0], [0]
    trades, eq, peak, mdd = [], 1.0, 1.0, 0.0
    i, n = 60, len(c15)
    while i < n - 2:
        t_close = c15[i]["t"] + 900_000
        v1 = _view(c1h, t_close, IV_MS["1h"], p1)
        v4 = _view(c4h, t_close, IV_MS["4h"], p4)
        vb = _view(b1h, t_close, IV_MS["1h"], pb)
        if len(v1) < 210 or len(v4) < 55 or len(vb) < 60: i += 1; continue
        w = c15[max(0, i - 199):i + 1]
        qv = sum(c["v"] * c["c"] for c in c15[max(0, i - 95):i + 1])
        sig = analyze(base, w, v1[-300:], v4[-120:], btc_state(vb[-300:]), {"qv": qv, "spread_pct": None}, cfg, price=c15[i]["c"])
        if sig["status"] not in ("LONG", "SHORT"): i += 1; continue
        d = 1 if sig["status"] == "LONG" else -1; pl = sig["plan"]
        fill = c15[i + 1]["o"] * (1 + d * R["slippage_pct"] / 100)
        if (fill - pl["sl"]) * d <= 0 or abs(fill - pl["entry"]) > .5 * sig["ind"]["atr_15m"] or (pl["tp"] - fill) * d <= 0:
            i += 1; continue
        risk = abs(fill - pl["sl"]); j = i + 1; ex = None
        while j < n:
            c = c15[j]
            sl = c["l"] <= pl["sl"] if d == 1 else c["h"] >= pl["sl"]
            tp = c["h"] >= pl["tp"] if d == 1 else c["l"] <= pl["tp"]
            if sl: ex = (pl["sl"] * (1 - d * R["slippage_pct"] / 100), "SL"); break
            if tp: ex = (pl["tp"], "TP"); break
            if j - i >= 96: ex = (c["c"], "TIME"); break
            j += 1
        if ex is None: break                                              # trade still open at end of data: excluded
        fees_r = R["fee_pct"] / 100 * (fill + ex[0]) / risk
        r = (ex[0] - fill) * d / risk - fees_r
        eq *= 1 + r * R["risk_per_trade_pct"] / 100
        peak = max(peak, eq); mdd = max(mdd, (peak - eq) / peak)
        trades.append({"time": c15[i]["t"], "dir": sig["status"], "entry": fill, "sl": pl["sl"], "tp": pl["tp"],
                       "exit": ex[0], "why": ex[1], "r": round(r, 2), "score": sig["score"]})
        i = j + 1
    rs = [t["r"] for t in trades]; wins = [x for x in rs if x > 0]; loss = [x for x in rs if x <= 0]
    return {"symbol": base, "bars_15m": n, "trades": len(trades),
            "win_rate": round(len(wins) / len(rs) * 100, 1) if rs else None,
            "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
            "profit_factor": round(sum(wins) / abs(sum(loss)), 2) if loss and sum(loss) else None,
            "return_pct": round((eq - 1) * 100, 2), "max_drawdown_pct": round(mdd * 100, 2), "list": trades[-50:][::-1]}
