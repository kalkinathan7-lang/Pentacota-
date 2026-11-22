"""Minimal educational backtest harness. It is not a validated performance report."""
import pandas as pd
from .indicators import add_indicators

def ema_trend_baseline(df: pd.DataFrame):
    x=add_indicators(df)
    x["signal"] = 0
    x.loc[(x.close>x.ema200)&(x.ema20>x.ema50),"signal"] = 1
    x.loc[(x.close<x.ema200)&(x.ema20<x.ema50),"signal"] = -1
    x["position"] = x.signal.shift(1).fillna(0)
    x["returns"] = x.close.pct_change().fillna(0)
    x["strategy_returns"] = x.position*x.returns
    x["equity_curve"] = (1+x.strategy_returns).cumprod()
    return x
