"""Pure-python indicators. Every function returns a list aligned to the input (None until warmed up)."""

def sma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n: s -= vals[i - n]
        if i >= n - 1: out[i] = s / n
    return out

def ema(vals, n):
    out = [None] * len(vals)
    if len(vals) < n: return out
    k = 2.0 / (n + 1)
    e = sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = vals[i] * k + e * (1 - k)
        out[i] = e
    return out

def rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n: return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0); losses += max(-d, 0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out

def atr(candles, n=14):
    out = [None] * len(candles)
    if len(candles) <= n: return out
    trs = []
    for i, c in enumerate(candles):
        if i == 0: trs.append(c["h"] - c["l"])
        else:
            pc = candles[i - 1]["c"]
            trs.append(max(c["h"] - c["l"], abs(c["h"] - pc), abs(c["l"] - pc)))
    a = sum(trs[1:n + 1]) / n
    out[n] = a
    for i in range(n + 1, len(candles)):
        a = (a * (n - 1) + trs[i]) / n
        out[i] = a
    return out

def pivots(candles, left, right, kind):
    """Swing highs (kind='h') or lows (kind='l'). Returns list of prices."""
    vals = [c[kind] for c in candles]
    res = []
    for i in range(left, len(vals) - right):
        w = vals[i - left:i + right + 1]
        if (vals[i] == max(w) if kind == "h" else vals[i] == min(w)):
            res.append(vals[i])
    return res
