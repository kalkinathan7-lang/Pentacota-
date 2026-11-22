from __future__ import annotations
import os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import requests
import pandas as pd

BASE = os.getenv("COINDCX_BASE_URL", "https://api.coindcx.com").rstrip("/")
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "12"))

class DataError(RuntimeError):
    pass

def _get(path: str, params: dict | None = None) -> Any:
    r = requests.get(BASE + path, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def get_tickers() -> list[dict]:
    data = _get("/exchange/ticker")
    if not isinstance(data, list):
        raise DataError("Ticker endpoint returned unexpected data")
    return data

def get_market_details() -> list[dict]:
    data = _get("/exchange/v1/markets_details")
    if not isinstance(data, list):
        raise DataError("Markets-details endpoint returned unexpected data")
    return data

def get_candles(market_pair: str, interval: str, limit: int = 300) -> pd.DataFrame:
    # CoinDCX spot public candles: pair such as B-BTC_USDT, interval 15m or 1h.
    raw = _get("/market_data/candles", {"pair": market_pair, "interval": interval, "limit": limit})
    if not isinstance(raw, list) or not raw:
        raise DataError(f"No candles for {market_pair} ({interval})")
    df = pd.DataFrame(raw)
    required = {"open", "high", "low", "close", "volume", "time"}
    if not required.issubset(df.columns):
        raise DataError(f"Candle fields missing for {market_pair}")
    df = df[list(required)].copy()
    for c in ["open", "high", "low", "close", "volume", "time"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna().sort_values("time").drop_duplicates("time").reset_index(drop=True)
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    if len(df) < 220:
        raise DataError(f"Insufficient candles ({len(df)}) for EMA200")
    # Ignore the latest potentially incomplete candle for analysis.
    return df.iloc[:-1].copy()

def _market_pair(detail: dict) -> str | None:
    # Prefer documented market/pair-like fields. Market-details response may vary.
    for key in ("pair", "market_pair", "market", "symbol"):
        v = detail.get(key)
        if isinstance(v, str) and v:
            if v.startswith("B-") and "_" in v:
                return v
    base = detail.get("base_currency_short_name") or detail.get("base_currency")
    quote = detail.get("target_currency_short_name") or detail.get("target_currency")
    if base and quote:
        return f"B-{str(base).upper()}_{str(quote).upper()}"
    return None

def get_top_usdt_universe(limit: int = 50) -> list[dict]:
    tickers = get_tickers()
    details = get_market_details()
    detail_map = {}
    for d in details:
        pair = _market_pair(d)
        if pair:
            detail_map[pair.replace("B-", "").replace("_", "")] = d
            detail_map[pair] = d
    candidates = []
    for t in tickers:
        market = str(t.get("market", "")).upper()
        if not market.endswith("USDT") or market in {"USDTUSDT"}:
            continue
        d = detail_map.get(market)
        if d is None:
            d = detail_map.get("B-" + market[:-4] + "_USDT")
        pair = _market_pair(d) if d else None
        if not pair:
            # Explicitly mark unresolved mapping; scanner skips it instead of guessing API pair.
            continue
        try:
            price = float(t.get("last_price", 0))
            volume = float(t.get("volume", 0))
            change = float(t.get("change_24_hour", 0))
        except (TypeError, ValueError):
            continue
        candidates.append({"symbol": market[:-4], "market": market, "pair": pair,
                           "price": price, "volume_24h": volume, "change_24h": change,
                           "ticker_timestamp": t.get("timestamp")})
    candidates.sort(key=lambda x: x["volume_24h"], reverse=True)
    return candidates[:limit]

def scan_market(universe: list[dict], progress=None) -> list[dict]:
    results = []
    total = len(universe)
    def worker(coin):
        one = get_candles(coin["pair"], "1h", 300)
        fifteen = get_candles(coin["pair"], "15m", 300)
        return coin, one, fifteen
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(worker, c): c for c in universe}
        done = 0
        for fut in as_completed(futures):
            done += 1
            coin = futures[fut]
            try:
                result = fut.result()
                results.append({"coin": coin, "1h": result[1], "15m": result[2], "error": None})
            except Exception as e:
                results.append({"coin": coin, "1h": None, "15m": None, "error": str(e)})
            if progress:
                progress(done, total)
    return results
