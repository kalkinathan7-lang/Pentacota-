import numpy as np
import pandas as pd

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    for n in (20, 50, 200):
        x[f"ema{n}"] = x.close.ewm(span=n, adjust=False).mean()
    delta = x.close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    x["rsi14"] = 100 - 100 / (1 + rs)
    tr = pd.concat([x.high-x.low, (x.high-x.close.shift()).abs(), (x.low-x.close.shift()).abs()], axis=1).max(axis=1)
    x["atr14"] = tr.ewm(alpha=1/14, adjust=False).mean()
    x["volume_sma20"] = x.volume.rolling(20).mean()
    x["swing_low"] = x.low.rolling(10).min().shift(1)
    x["swing_high"] = x.high.rolling(10).max().shift(1)
    return x

def resample_4h(df1h: pd.DataFrame) -> pd.DataFrame:
    x = df1h.set_index("time").resample("4h").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna().reset_index()
    return add_indicators(x)
