"""Multi-Timeframe Trend Pullback strategy. 1H trend, 15M entry, 4H context, BTC filter.
All numbers come from supplied candles; if anything required is missing the setup is rejected."""
from .indicators import ema, rsi, atr, pivots, sma

def _last(x): return x[-1]

def trend_state(c1h):
    cl = [c["c"] for c in c1h]
    e20, e50, e200 = ema(cl, 20), ema(cl, 50), ema(cl, 200)
    if e200[-1] is None or e50[-6] is None: return None
    r = rsi(cl); a = atr(c1h)
    c = cl[-1]
    d = 1 if (e20[-1] > e50[-1] > e200[-1] and c > e200[-1]) else \
        -1 if (e20[-1] < e50[-1] < e200[-1] and c < e200[-1]) else 0
    return {"dir": d, "close": c, "e20": e20[-1], "e50": e50[-1], "e200": e200[-1], "rsi": r[-1], "atr": a[-1],
            "slope_pct": (e50[-1] - e50[-6]) / e50[-6] * 100}

def btc_state(c1h):
    """Looser than the coin trend test: bull/bear/neutral from price vs EMA50 and EMA20/50 order."""
    cl = [c["c"] for c in c1h]
    e20, e50 = ema(cl, 20), ema(cl, 50)
    if e50[-1] is None: return None
    r = rsi(cl)[-1]
    st = "bull" if cl[-1] > e50[-1] and e20[-1] > e50[-1] else \
         "bear" if cl[-1] < e50[-1] and e20[-1] < e50[-1] else "neutral"
    return {"state": st, "close": cl[-1], "e20": e20[-1], "e50": e50[-1], "rsi": r}

def _levels(d, entry, c15, c1h, c4h, swing):
    lv = pivots(c1h[-150:], 3, 3, "h" if d == 1 else "l") + pivots(c4h[-60:], 2, 2, "h" if d == 1 else "l") \
         + pivots(c15[-150:], 3, 3, "h" if d == 1 else "l") + [swing]
    lv = sorted({round(x, 10) for x in lv if (x - entry) * d > 0}, key=lambda x: abs(x - entry))
    return lv

def make_plan(d, entry, ext, swing, a15, c15, c1h, c4h, cfg, equity):
    S, R = cfg["strategy"], cfg["risk"]
    sl = ext - d * S["sl_atr_buffer"] * a15                  # beyond the pullback swing + ATR buffer
    sl = sl if (entry - sl) * d >= S["min_stop_atr"] * a15 else entry - d * S["min_stop_atr"] * a15
    risk = abs(entry - sl)
    if risk <= 0: return None, "stop distance is zero"
    if risk / entry * 100 > S["max_stop_pct"]:
        return None, f"structural stop {risk/entry*100:.2f}% away exceeds {S['max_stop_pct']}% limit"
    lv = _levels(d, entry, c15, c1h, c4h, swing)
    rr = lambda p: (abs(p - entry) - 0.1 * a15) / risk
    tp = basis = None; obstacles = []
    if lv and rr(lv[0]) < 0.8:
        return None, f"nearest {'resistance' if d==1 else 'support'} {lv[0]:.6g} leaves only {rr(lv[0]):.2f}R"
    for p in lv:
        if rr(p) >= S["min_rr"]:
            tp = p - d * 0.1 * a15
            basis = f"nearest {'resistance' if d==1 else 'support'} reaching {S['min_rr']}R at {p:.6g}"
            break
        obstacles.append(p)
    if tp is None:
        if lv: return None, f"no {'resistance' if d==1 else 'support'} level offers {S['min_rr']}R (best {rr(lv[-1]):.2f}R)"
        leg = max(c["h"] for c in c15[-60:]) - min(c["l"] for c in c15[-60:])   # no level in the way: measured move
        tp = entry + d * 0.75 * leg
        basis = "no overhead level; 75% of the last 60-bar swing range projected"
        if rr(tp) < S["min_rr"]: return None, f"measured-move target gives only {rr(tp):.2f}R"
    r_mult = abs(tp - entry) / risk
    units = equity * R["risk_per_trade_pct"] / 100 / risk
    cap = equity * R["max_leverage"] / entry
    capped = units > cap
    units = min(units, cap)
    notional = units * entry
    if notional < R["min_notional"]: return None, "position below minimum notional"
    return {"entry": entry, "sl": sl, "tp": tp, "rr": round(r_mult, 2), "stop_pct": round(risk / entry * 100, 3),
            "units": units, "notional": notional, "risk_amt": units * risk, "leverage_capped": capped,
            "tp_basis": basis, "obstacles": obstacles[:3]}, None

def analyze(sym, c15, c1h, c4h, btc, tick, cfg, price=None, equity=None):
    S, X = cfg["strategy"], cfg["exchange"]
    equity = equity or cfg["risk"]["start_equity"]
    out = {"symbol": sym, "status": "NO TRADE", "score": 0, "direction": None, "reason": "", "plan": None,
           "ind": {}, "checks": [], "parts": {}, "invalidation": [], "trend": "-", "data_ok": True}
    chk = lambda n, ok, det: out["checks"].append({"name": n, "ok": bool(ok), "detail": det})
    def done(status, reason):
        out["status"], out["reason"] = status, reason
        return out
    if len(c15) < 80 or len(c1h) < 210 or len(c4h) < 55 or btc is None:
        out["data_ok"] = False
        return done("NO TRADE", "insufficient candle history or BTC context - setup rejected")

    # ---------- indicators ----------
    cl15 = [c["c"] for c in c15]
    e20_15, e50_15 = ema(cl15, 20), ema(cl15, 50)
    r15 = rsi(cl15); a15 = atr(c15)[-1]
    vavg = sma([c["v"] for c in c15], 20)
    T = trend_state(c1h)
    cl4 = [c["c"] for c in c4h]; e20_4, e50_4 = ema(cl4, 20)[-1], ema(cl4, 50)[-1]
    last = c15[-1]; prev = c15[-2]
    price = price or last["c"]
    vol_ratio = last["v"] / vavg[-2] if vavg[-2] else 0
    out["ind"] = {"price": price, "ema20_15m": e20_15[-1], "ema50_15m": e50_15[-1], "rsi_15m": r15[-1],
                  "atr_15m": a15, "volume_ratio": round(vol_ratio, 2), "ema20_1h": T["e20"], "ema50_1h": T["e50"],
                  "ema200_1h": T["e200"], "rsi_1h": T["rsi"], "atr_1h": T["atr"], "ema50_slope_1h_pct": T["slope_pct"],
                  "ema20_4h": e20_4, "ema50_4h": e50_4, "btc_state": btc["state"], "btc_rsi_1h": btc["rsi"],
                  "quote_volume_24h": tick.get("qv"), "spread_pct": tick.get("spread_pct")}
    d = T["dir"]
    out["trend"] = {1: "BULL", -1: "BEAR", 0: "NEUTRAL"}[d]
    out["direction"] = {1: "LONG", -1: "SHORT"}.get(d)

    # ---------- gates ----------
    chk("1H trend (EMA20/50/200 stacked, price vs EMA200)", d != 0,
        f"EMA20 {T['e20']:.6g}, EMA50 {T['e50']:.6g}, EMA200 {T['e200']:.6g}, close {T['close']:.6g}")
    if d == 0: return done("NO TRADE", "1H trend not aligned: EMAs not stacked or price on wrong side of EMA200")
    if d == -1 and not S["allow_shorts"]: return done("NO TRADE", "bearish trend but shorts are disabled")
    mom = d * (T["rsi"] - 50) > 0
    chk("1H momentum (RSI14 vs 50)", mom, f"RSI {T['rsi']:.1f}")
    if not mom: return done("NO TRADE", f"momentum against trend (1H RSI {T['rsi']:.1f})")
    liq_ok = (tick.get("qv") or 0) >= X["min_quote_volume"] and (tick.get("spread_pct") is None or tick["spread_pct"] <= X["max_spread_pct"])
    chk("Liquidity", liq_ok, f"24h volume {tick.get('qv') or 0:,.0f} {cfg['exchange']['quote']}, spread {tick.get('spread_pct')}")
    if not liq_ok: return done("NO TRADE", "volume or spread fails liquidity rules")
    is_btc = sym.upper().startswith("BTC")
    btc_ok = is_btc or btc["state"] == "neutral" or (btc["state"] == "bull") == (d == 1)
    chk("BTC condition", btc_ok, f"BTC 1H is {btc['state']} (RSI {btc['rsi']:.1f})")
    if not btc_ok: return done("NO TRADE", f"BTC 1H is {btc['state']}, opposes a {out['direction']}")
    agree4 = d * (cl4[-1] - e50_4) > 0 and d * (e20_4 - e50_4) > 0
    chk("4H context (optional)", agree4, f"4H close {cl4[-1]:.6g} vs EMA50 {e50_4:.6g}")

    # ---------- pullback ----------
    lb = S["pullback_lookback"]; i0 = len(c15) - lb
    win = c15[-lb:]
    ext = min(c["l"] for c in win) if d == 1 else max(c["h"] for c in win)
    swing = max(c["h"] for c in c15[-40:]) if d == 1 else min(c["l"] for c in c15[-40:])
    touch15 = any((c["l"] <= e20_15[i0 + k] + .25 * a15) if d == 1 else (c["h"] >= e20_15[i0 + k] - .25 * a15)
                  for k, c in enumerate(win))
    touch1h = (ext <= T["e20"] + .25 * T["atr"]) if d == 1 else (ext >= T["e20"] - .25 * T["atr"])
    depth = abs(swing - ext) / a15
    intact = (ext >= T["e50"] - .75 * T["atr"] and price > T["e200"]) if d == 1 else (ext <= T["e50"] + .75 * T["atr"] and price < T["e200"])
    chk("Structure intact (pullback holds 1H EMA50 zone)", intact, f"pullback extreme {ext:.6g}")
    if not intact: return done("NO TRADE", "pullback broke 1H trend structure")
    pb_ok = (touch15 or touch1h) and depth >= 1.0
    chk("Pullback to EMA zone", pb_ok, f"depth {depth:.2f} ATR(15m) from swing {swing:.6g}; touched 15m EMA20 zone: {touch15}, 1H EMA20 zone: {touch1h}")
    if not pb_ok:
        if depth >= 0.8:
            out["parts"] = _score(out, d, T, btc, is_btc, agree4, depth, touch15, e50_15, ext, a15, r15, vol_ratio, tick, 0, cfg)
            out["score"] = sum(out["parts"].values())
            return done("WAITING", f"{out['direction']} trend intact; pullback of {depth:.1f} ATR still approaching the EMA zone")
        return done("NO TRADE", f"trend is {out['trend']} but no pullback yet (depth {depth:.2f} ATR) - price extended")

    # ---------- 15M confirmation ----------
    ok_candle = (last["c"] > last["o"]) if d == 1 else (last["c"] < last["o"])
    ok_ema = d * (last["c"] - e20_15[-1]) > 0
    ok_brk = d * (last["c"] - prev["c"]) > 0
    ok_rsi = r15[-1] is not None and d * (r15[-1] - r15[-2]) > 0 and (r15[-1] > 40 if d == 1 else r15[-1] < 60)
    ok_vol = vol_ratio >= S["vol_min_ratio"]
    for n, ok, det in [("Entry candle direction", ok_candle, f"O {last['o']:.6g} C {last['c']:.6g}"),
                       ("Close back beyond 15m EMA20", ok_ema, f"EMA20 {e20_15[-1]:.6g}"),
                       ("Close beyond previous close", ok_brk, f"prev close {prev['c']:.6g}"),
                       ("15m RSI turning with trade", ok_rsi, f"RSI {r15[-1]:.1f} (prev {r15[-2]:.1f})"),
                       ("Volume vs 20-bar average", ok_vol, f"{vol_ratio:.2f}x (min {S['vol_min_ratio']}x)")]:
        chk(n, ok, det)
    missing = [c["name"] for c in out["checks"][-5:] if not c["ok"]]
    out["parts"] = _score(out, d, T, btc, is_btc, agree4, depth, touch15, e50_15, ext, a15, r15, vol_ratio, tick, 0, cfg)
    if missing:
        out["score"] = sum(out["parts"].values())
        return done("WAITING", "pullback is in place; confirmation missing: " + ", ".join(missing))
    if abs(price - last["c"]) > .5 * a15:
        out["score"] = sum(out["parts"].values())
        return done("WAITING", f"price is {abs(price-last['c'])/a15:.2f} ATR away from the confirmation close; no chasing")

    # ---------- dynamic plan ----------
    plan, why = make_plan(d, price, ext, swing, a15, c15, c1h, c4h, cfg, equity)
    chk("Chart-based TP/SL and risk/reward", plan is not None, why or f"SL {plan['sl']:.6g}, TP {plan['tp']:.6g}, {plan['rr']}R")
    if plan is None: return done("NO TRADE", "no realistic trade plan: " + why)
    out["parts"] = _score(out, d, T, btc, is_btc, agree4, depth, touch15, e50_15, ext, a15, r15, vol_ratio, tick, plan["rr"], cfg)
    out["score"] = round(sum(out["parts"].values()), 1)
    out["plan"] = plan
    if out["score"] < S["min_score"]:
        return done("NO TRADE", f"setup is valid but weak: score {out['score']} < {S['min_score']}")
    out["invalidation"] = [f"Price {'closes below' if d == 1 else 'closes above'} the stop {plan['sl']:.6g}",
                           f"1H close {'below' if d == 1 else 'above'} 1H EMA50 {T['e50']:.6g}",
                           f"BTC 1H turns {'bearish' if d == 1 else 'bullish'}",
                           "Entry not filled within the zone before the next 15m close"]
    arrow = "bullish" if d == 1 else "bearish"
    return done(out["direction"], f"{arrow} 1H stack, RSI {T['rsi']:.0f}, pullback {depth:.1f} ATR into EMA zone, "
                f"confirmed on 15m with {vol_ratio:.1f}x volume, BTC {btc['state']}, {plan['rr']}R to {plan['tp_basis']}")

def _score(out, d, T, btc, is_btc, agree4, depth, touch15, e50_15, ext, a15, r15, vr, tick, rr, cfg):
    p = {}
    p["trend"] = 10 + (5 if agree4 else 0) + (5 if abs(T["slope_pct"]) > 0.3 else 0)
    p["btc"] = 15 if (is_btc or (btc["state"] == "bull") == (d == 1) and btc["state"] != "neutral") else 8
    m = min(1, abs(T["rsi"] - 50) / 15) * 10
    if (d == 1 and T["rsi"] > 75) or (d == -1 and T["rsi"] < 25): m = 3
    r_now, r_prev = r15[-1], r15[-2]
    if r_now is not None and d * (r_now - r_prev) > 0 and ((40 < r_now < 65) if d == 1 else (35 < r_now < 60)): m += 5
    p["momentum"] = min(15, m)
    near50 = (ext <= e50_15[-1] + .3 * a15) if d == 1 else (ext >= e50_15[-1] - .3 * a15)
    p["pullback"] = (8 if 1 <= depth <= 4 else 4) + (4 if near50 else 0) + 3
    p["volume"] = 10 if vr >= 1.5 else 7 if vr >= 1.0 else 4 if vr >= cfg["strategy"]["vol_min_ratio"] else 0
    p["rr"] = max(0, min(1, (rr - 1.0) / 2.0)) * 15
    qv = tick.get("qv") or 0
    p["liquidity"] = 10 if qv >= 5e7 else 8 if qv >= 1e7 else 6 if qv >= 3e6 else 4
    if tick.get("spread_pct") and tick["spread_pct"] > 0.1: p["liquidity"] = max(0, p["liquidity"] - 4)
    return {k: round(v, 1) for k, v in p.items()}
