# Pentacota - Crypto Trading AI (CoinDCX)

Multi-timeframe trend-pullback scanner with dynamic SL/TP, risk controls, paper trading and backtesting.
Pure Python 3.9+ standard library. No installs needed.

## Run
    python run.py
Open http://127.0.0.1:8765 and press **Start scanner**. Needs internet access to CoinDCX public endpoints.

## Test (offline)
    python tests/test_engine.py

## How it works
- Scans top 50 CoinDCX USDT markets by 24h quote volume (stablecoins excluded).
- 1H trend (EMA20/50/200 stacked, price vs EMA200, RSI vs 50), 15M pullback + confirmation (candle, EMA20 reclaim,
  RSI turn, volume vs 20-bar avg), 4H context, BTC 1H filter, liquidity/spread gate.
- SL = beyond pullback swing + ATR buffer (min 1 ATR, max 4% distance). TP = nearest real support/resistance
  (1H/4H/15M pivots) that gives >= 1.5R, else measured move; otherwise the trade is rejected.
- Size = equity x 0.5% / stop distance, capped by max leverage.
- Status: LONG / SHORT / WAITING / NO TRADE. Missing, stale or failed data always means NO TRADE.
- Score (100): trend 20, BTC 15, momentum 15, pullback 15, volume 10, R/R 15, liquidity 10. Threshold 65 in config.json -
  calibrate with the Backtest panel; never lower it just to get more trades.
- Risk: 2 positions max, 2% daily loss lock, 1% total open risk cap, duplicate/cooldown block, stops never widened,
  kill switch (closes paper positions and blocks entries; also a data/KILL file).
- Every valid signal is appended to data/signals.jsonl for audit.

## Configuration
Edit config.json, or create config.local.json with only the keys you want to override.

## Live trading is intentionally locked
pentacota/live.py places no orders. Run the backtest, then weeks of paper trading, then validate CoinDCX order,
cancel and status endpoints with tiny size and add verified-fill reconciliation before enabling anything.
Never put API keys in this repo.

## Known limits
- Candle history per request is limited, so backtests cover recent weeks only: a smoke test, not proof.
- Shorts are simulated in paper mode; CoinDCX spot cannot short, so live shorts need futures integration.
- Candle endpoint format (pair "B-BTC_USDT") follows CoinDCX public docs and could not be tested from my
  sandbox (no internet). If CoinDCX changes it, edit pentacota/data.py.
- Not financial advice. Crypto trading can lose all capital.
