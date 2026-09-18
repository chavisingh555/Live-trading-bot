"""CLI entry point for the NIFTY 50 swing-trading backtest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backtest import BacktestConfig, Backtester, performance_summary
from .data import load_directory
from .strategy import StrategyConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NIFTY 50 swing backtest")
    parser.add_argument("--data-dir", default="data/raw")
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--initial-capital", type=float, default=1_000_000)
    parser.add_argument("--max-positions", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    data = load_directory(args.data_dir)

    strategy_config = StrategyConfig()
    backtest_config = BacktestConfig(
        initial_capital=args.initial_capital,
        max_positions=args.max_positions,
    )

    engine = Backtester(data, strategy_config, backtest_config)
    trades, equity = engine.run()
    summary = performance_summary(
        trades, equity, backtest_config.initial_capital
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades.to_csv(output_dir / "trades.csv", index=False)
    equity.to_csv(output_dir / "equity_curve.csv", index=False)

    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
