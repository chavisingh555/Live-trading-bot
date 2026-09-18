# NIFTY 50 Swing Trading BOT

Academic long-only swing-trading/backtesting project for Indian equities (NSE/NIFTY 50).

## Strategy

- Daily candles
- EMA(20) > EMA(50) trend condition
- Close > highest High of the previous 20 sessions
- RSI(14) > 50 confirmation
- Volume > previous 20-session average confirmation
- Trend and breakout are mandatory
- RSI and volume contribute to a confirmation score used for ranking
- Maximum 5 simultaneous positions
- Equal capital allocation
- Entry at next trading day's open
- 5% stop-loss
- 10% take-profit
- Maximum 20 trading days
- 0.10% round-trip transaction cost
- 0.05% slippage per side
- Conservative stop-first assumption when stop and target occur in the same daily candle

## Setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Download data

Use the NIFTY 50 symbols in `config/nifty50_symbols.csv` and save daily CSV files under `data/raw/`.

The downloader can also be called from Python:

```python
from src.data import download_yfinance

symbols = ["RELIANCE", "INFY", "TCS"]
download_yfinance(symbols, "2018-01-01", "2026-09-17", "data/raw")
```

## Run

```bash
python -m src.run_backtest --data-dir data/raw --initial-capital 1000000
```

Outputs are written to `results/`:

- `trades.csv`
- `equity_curve.csv`
- `summary.json`

## Important academic safeguard

The project does not claim historical performance until a reproducible dataset is actually downloaded, archived, and backtested. The NIFTY 50 constituent list can change over time; for a final submission, archive the exact constituent list and raw data used.
