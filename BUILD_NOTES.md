# Build Notes

The BOT is intentionally separated into:
- `strategy.py`: indicators, conditions, ranking
- `backtest.py`: execution simulation, portfolio, risk exits and performance
- `data.py`: loading/downloading OHLCV
- `run_backtest.py`: command-line orchestration

No empirical performance result is embedded in the source. Results must be generated from actual historical data.

The design is intended for academic backtesting, not unattended live order execution.
