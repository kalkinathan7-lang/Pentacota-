"""LIVE EXECUTION IS LOCKED. This module deliberately places no orders.

Before any order code is written here you must: (1) backtest and paper trade the strategy, (2) verify every risk
control with the test suite, (3) validate order placement, cancel and status calls against CoinDCX's current API
docs using a tiny-size test, (4) add verified-fill reconciliation. Then set mode.trading='live' AND create
data/LIVE_UNLOCK yourself. Until then every call below raises."""
import hmac, hashlib, json, os
from .config import DATA

def sign(body: dict, secret: str) -> str:
    """CoinDCX signs the JSON body (compact separators) with HMAC-SHA256 using the API secret."""
    payload = json.dumps(body, separators=(",", ":"))
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def place_order(*_a, **_k):
    if not os.path.exists(os.path.join(DATA, "LIVE_UNLOCK")):
        raise RuntimeError("Live trading locked: paper-trade and validate first (see README).")
    raise NotImplementedError("Order placement intentionally not implemented; validate against exchange docs first.")
