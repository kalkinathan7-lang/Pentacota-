from __future__ import annotations
import math
import pandas as pd
from .indicators import add_indicators, resample_4h
from .risk import position_size


def _last(df):
    return df.iloc[-1]

def analyze(coin: dict, df1h: pd.DataFrame, df15m: pd.DataFrame, btc1h: pd.DataFrame | None, equity: float = 10000, risk_pct: float = 0.5, min_rr: float = 1.8) -> dict:
    out = {"symbol": coin["symbol"], "price": coin["price"], "status": "NO TRADE", "direction": None, "score": 0, "reason": "", "details": {}, "plan": None}
    if df1h is None or df15m is None or len(df1h) < 220 or len(df15m) < 220:
        out["reason"] = "Missing or insufficient candle data; setup rejected."
        return out
    h = add_indicators(df1h); m = add_indicators(df15m); four = resample_4h(df1h)
    if len(four) < 55:
        out["reason"] = "Insufficient 4h context candles; setup rejected."
        return out
    a, b, c = _last(h), _last(m), _last(four)
    price = float(b.close); atr = float(b.atr14)
    if not all(math.isfinite(float(v)) for v in [price, atr, b.rsi14, b.volume_sma20, a.ema200, c.ema50]) or atr <= 0:
        out["reason"] = "Indicator data incomplete or invalid."
        return out
    bull = a.close > a.ema200 and a.ema20 > a.ema50 and a.ema50 > a.ema200 and a.ema20 > h.ema20.iloc[-5]
    bear = a.close < a.ema200 and a.ema20 < a.ema50 and a.ema50 < a.ema200 and a.ema20 < h.ema20.iloc[-5]
    four_bull = c.close > c.ema50
    four_bear = c.close < c.ema50
    btc_bull = btc1h is not None and len(btc1h) >= 220 and _last(add_indicators(btc1h)).close > _last(add_indicators(btc1h)).ema200
    btc_bear = btc1h is not None and len(btc1h) >= 220 and _last(add_indicators(btc1h)).close < _last(add_indicators(btc1h)).ema200
    pullback = abs(price - float(b.ema20)) <= 0.65 * atr or abs(price - float(b.ema50)) <= 0.8 * atr
    bullish_candle = b.close > b.open and b.close > m.close.iloc[-2]
    bearish_candle = b.close < b.open and b.close < m.close.iloc[-2]
    vol_ok = b.volume >= 0.8 * b.volume_sma20
    rsi_long = 48 <= b.rsi14 <= 68
    rsi_short = 32 <= b.rsi14 <= 52
    trend_score = 25 if (bull or bear) else 0
    context_score = 10 if ((bull and four_bull and btc_bull) or (bear and four_bear and btc_bear)) else 4 if ((bull and four_bull) or (bear and four_bear)) else 0
    pullback_score = 15 if pullback else 0
    momentum_score = 15 if ((bull and rsi_long) or (bear and rsi_short)) else 0
    volume_score = 10 if vol_ok else 0
    candle_score = 10 if (bull and bullish_candle) or (bear and bearish_candle) else 0
    rr_score = 15
    score = trend_score + context_score + pullback_score + momentum_score + volume_score + candle_score + rr_score
    out["score"] = score
    out["details"] = {"1h trend":"BULLISH" if bull else "BEARISH" if bear else "MIXED", "4h context":"BULLISH" if four_bull else "BEARISH", "BTC trend":"BULLISH" if btc_bull else "BEARISH" if btc_bear else "UNKNOWN", "15m RSI":round(float(b.rsi14),2), "ATR":round(atr,8), "Volume vs avg":round(float(b.volume / b.volume_sma20),2) if b.volume_sma20 else None, "EMA20":float(b.ema20), "EMA50":float(b.ema50), "EMA200 1h":float(a.ema200), "Pullback":pullback}
    direction = "LONG" if bull and four_bull and btc_bull and pullback and bullish_candle and rsi_long and vol_ok else "SHORT" if bear and four_bear and btc_bear and pullback and bearish_candle and rsi_short and vol_ok else None
    if direction is None:
        developing = (bull and pullback) or (bear and pullback) or (bull and four_bull) or (bear and four_bear)
        out["status"] = "WAITING" if developing else "NO TRADE"
        out["reason"] = "Setup developing, but one or more confirmations are missing." if developing else "Trend, pullback, or market context conditions are invalid."
        return out
    # Structure-derived stop, ATR buffer, and target constrained by RR.
    if direction == "LONG":
        swing = float(m.swing_low.iloc[-1]) if pd.notna(m.swing_low.iloc[-1]) else price - atr
        stop = min(swing, price - 1.2 * atr) - 0.15 * atr
        risk = price - stop
        resistance = float(m.high.iloc[-30:-1].max())
        target = max(price + min(2.2*risk, max(0.0, resistance-price)), price + min_rr*risk)
        invalid = "15m close below stop/swing low; 1h EMA trend flips or BTC loses trend support."
    else:
        swing = float(m.swing_high.iloc[-1]) if pd.notna(m.swing_high.iloc[-1]) else price + atr
        stop = max(swing, price + 1.2 * atr) + 0.15 * atr
        risk = stop - price
        support = float(m.low.iloc[-30:-1].min())
        target = min(price - min(2.2*risk, max(0.0, price-support)), price-min_rr*risk)
        invalid = "15m close above stop/swing high; 1h EMA trend flips or BTC regains trend resistance."
    rr = abs(target-price)/risk if risk > 0 else 0
    qty = position_size(equity, price, stop, risk_pct)
    if risk <= 0 or rr < min_rr or not all(math.isfinite(x) for x in [price, stop, target, qty]) or qty <= 0:
        out["status"] = "NO TRADE"; out["reason"] = "Dynamic trade plan failed risk/reward or sizing validation."; return out
    out.update(status=direction, direction=direction, reason=f"1h trend + 4h context + BTC alignment; 15m pullback and candle confirmation; RSI {b.rsi14:.1f}; volume {b.volume/b.volume_sma20:.2f}x average.", plan={"entry":price,"stop_loss":stop,"take_profit":target,"risk_reward":rr,"quantity":qty,"risk_cash":equity*risk_pct/100,"invalidation":invalid})
    return out
