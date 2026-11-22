# PENTACOTA — Crypto Trading Intelligence (Prototype)

A Streamlit application for market scanning, technical setup analysis, risk planning, and paper-trading workflow. It uses CoinDCX **public spot market-data endpoints**. It does not place orders and it is not a live trading bot.

## Important limitations
- Public market endpoints and response formats can change. Verify API compatibility before relying on this application.
- Scanner candidates are not trading advice. Strategy thresholds are initial hypotheses, not validated performance claims.
- Scanner fetches candles for eligible USDT spot markets; the top 50 are selected by available 24h ticker volume. It can fail or skip markets when data is missing/stale.
- CoinDCX public candles support 15m and 1h. 4h context is resampled from 1h candles.
- Paper trade log is stored locally in `paper_trades.csv`; it is a manual paper-trading log, not a simulator of exchange fills.
- No API keys are required. Do not use an API key with trading permissions in this prototype.

## Run locally
1. Install Python 3.10+.
2. Extract the ZIP.
3. Open a terminal in this folder and run:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\\Scripts\\activate
   # macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt
   streamlit run app.py
   ```
4. The app opens in your browser. Press **Scan market** to refresh.

## Project structure
- `app.py` — dashboard and controls
- `pentacota/data.py` — CoinDCX public API client, data checks, market universe
- `pentacota/indicators.py` — EMA, RSI, ATR, volume average, structure levels
- `pentacota/strategy.py` — multi-timeframe setup rules, score, dynamic trade plan
- `pentacota/risk.py` — risk sizing and portfolio guardrails
- `pentacota/paper.py` — local paper trade log
- `pentacota/backtest.py` — simple historical rule backtest harness (not yet optimized)

## Scanner logic (initial rule set)
- 1h trend: EMA20/50 alignment, price relative to EMA200, EMA slope
- 15m setup: pullback proximity to EMA20/50, candle confirmation, RSI, volume vs 20-bar average
- 4h context: resampled 1h EMA trend
- BTC context: BTC 1h trend and recent return
- Structure-based stop with ATR buffer; target selected from reward/risk and nearby swing level
- Score is a transparent weighted score; score alone cannot override missing data or invalid conditions

## Safety defaults
- Risk per trade: 0.5% of equity
- Max simultaneous paper positions: 2
- Daily loss guard: 2% (manual paper log only)
- No automatic execution, no API secret storage, no live orders, no leverage

## Tests
Run:
```bash
python -m unittest discover -s tests -v
```
