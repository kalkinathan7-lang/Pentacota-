"""CoinDCX public market data. Candles are always returned CLOSED-only, ascending, and freshness-checked."""
import json, time, threading, urllib.request

TICKER_URL = "https://api.coindcx.com/exchange/ticker"
CANDLE_URL = "https://public.coindcx.com/market_data/candles"
IV_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
CACHE_TTL = {"15m": 30, "1h": 240, "4h": 600}

class DataError(Exception): pass

def http_json(url, timeout=12, retries=2):
    last = None
    for a in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Pentacota/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e; time.sleep(0.6 * (a + 1))
    raise DataError(f"request failed: {url} ({last})")

def get_tickers():
    raw = http_json(TICKER_URL)
    out = {}
    for t in raw:
        try:
            out[t["market"]] = {"last": float(t["last_price"]), "bid": float(t.get("bid") or 0),
                                "ask": float(t.get("ask") or 0), "vol": float(t.get("volume") or 0),
                                "change": float(t.get("change_24_hour") or 0)}
        except (KeyError, ValueError, TypeError):
            continue
    return out

def top_symbols(cfg):
    X = cfg["exchange"]; q = X["quote"]
    tk = get_tickers(); rows = []
    for m, t in tk.items():
        if not m.endswith(q): continue
        base = m[:-len(q)]
        if not base or base in X["excluded_bases"] or t["last"] <= 0: continue
        qv = t["vol"] * t["last"]
        spread = ((t["ask"] - t["bid"]) / t["last"] * 100) if t["bid"] > 0 and t["ask"] > 0 else None
        rows.append({"base": base, "market": m, "last": t["last"], "qv": qv, "spread_pct": spread, "change": t["change"]})
    rows.sort(key=lambda r: r["qv"], reverse=True)
    return [r for r in rows if r["qv"] >= X["min_quote_volume"]][:X["top_n"]]

_cache, _lock = {}, threading.Lock()

def get_candles(base, quote, interval, limit=300, check_fresh=True):
    key = (base, quote, interval, limit)
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL[interval]:
        return hit[1]
    raw = http_json(f"{CANDLE_URL}?pair=B-{base}_{quote}&interval={interval}&limit={limit}")
    if not isinstance(raw, list) or not raw:
        raise DataError(f"no candles for {base}{quote} {interval}")
    c = sorted(({"t": int(x["time"]), "o": float(x["open"]), "h": float(x["high"]),
                 "l": float(x["low"]), "c": float(x["close"]), "v": float(x["volume"])} for x in raw),
               key=lambda x: x["t"])
    iv = IV_MS[interval]; now = int(time.time() * 1000)
    c = [x for x in c if x["t"] + iv <= now]          # drop the still-forming candle
    if not c: raise DataError(f"no closed candles for {base}{quote} {interval}")
    if check_fresh and now - (c[-1]["t"] + iv) > 2.5 * iv:
        raise DataError(f"stale {interval} data for {base}{quote}")
    with _lock:
        _cache[key] = (time.time(), c)
    return c
