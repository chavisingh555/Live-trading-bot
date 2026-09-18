"""Event-driven daily-bar backtest engine for the NIFTY 50 swing strategy."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import math
import pandas as pd
import numpy as np

from .strategy import StrategyConfig, add_indicators


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    max_positions: int = 5
    allocation_per_position: Optional[float] = None
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    max_holding_days: int = 20
    round_trip_cost_pct: float = 0.0010
    slippage_per_side_pct: float = 0.0005


@dataclass
class Position:
    symbol: str
    shares: int
    entry_date: pd.Timestamp
    entry_price: float
    cost_basis: float
    target_price: float
    stop_price: float


@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: int
    exit_reason: str
    gross_pnl: float
    transaction_cost: float
    slippage_cost: float
    net_pnl: float
    holding_days: int


def _execution_price(raw_price: float, side: str, slippage_pct: float) -> float:
    """Apply adverse slippage to an execution price."""
    if side == "buy":
        return raw_price * (1 + slippage_pct)
    if side == "sell":
        return raw_price * (1 - slippage_pct)
    raise ValueError("side must be 'buy' or 'sell'")


class Backtester:
    """Backtest a next-open-entry, long-only swing strategy."""

    def __init__(
        self,
        data: Dict[str, pd.DataFrame],
        strategy_config: StrategyConfig | None = None,
        config: BacktestConfig | None = None,
    ):
        self.raw_data = {k: v.sort_index().copy() for k, v in data.items()}
        self.strategy_config = strategy_config or StrategyConfig()
        self.config = config or BacktestConfig()

        self.data = {
            symbol: add_indicators(df, self.strategy_config)
            for symbol, df in self.raw_data.items()
            if not df.empty
        }

        self.cash = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[dict] = []

    def _allocation(self) -> float:
        if self.config.allocation_per_position is not None:
            return self.config.allocation_per_position
        return self.config.initial_capital / self.config.max_positions

    def _open_position(self, symbol: str, date: pd.Timestamp, row: pd.Series) -> None:
        if symbol in self.positions or len(self.positions) >= self.config.max_positions:
            return

        raw_open = float(row["Open"])
        if not math.isfinite(raw_open) or raw_open <= 0:
            return

        entry_price = _execution_price(
            raw_open, "buy", self.config.slippage_per_side_pct
        )

        allocation = min(self._allocation(), self.cash)
        shares = int(allocation // entry_price)
        if shares <= 0:
            return

        notional = shares * entry_price
        # Split the configured round-trip cost equally between entry and exit.
        entry_cost = notional * (self.config.round_trip_cost_pct / 2.0)
        total_required = notional + entry_cost
        if total_required > self.cash:
            shares = int(self.cash // (entry_price * (1 + self.config.round_trip_cost_pct / 2)))
            if shares <= 0:
                return
            notional = shares * entry_price
            entry_cost = notional * (self.config.round_trip_cost_pct / 2.0)
            total_required = notional + entry_cost

        self.cash -= total_required

        self.positions[symbol] = Position(
            symbol=symbol,
            shares=shares,
            entry_date=date,
            entry_price=entry_price,
            cost_basis=notional,
            target_price=entry_price * (1 + self.config.take_profit_pct),
            stop_price=entry_price * (1 - self.config.stop_loss_pct),
        )

    def _close_position(
        self,
        symbol: str,
        date: pd.Timestamp,
        raw_exit_price: float,
        reason: str,
    ) -> None:
        pos = self.positions.pop(symbol)
        exit_price = _execution_price(
            raw_exit_price, "sell", self.config.slippage_per_side_pct
        )
        gross_pnl = (exit_price - pos.entry_price) * pos.shares

        exit_cost = (exit_price * pos.shares) * (self.config.round_trip_cost_pct / 2.0)
        entry_cost = pos.cost_basis * (self.config.round_trip_cost_pct / 2.0)
        transaction_cost = entry_cost + exit_cost

        # Slippage cost is approximated as the difference between raw and
        # slippage-adjusted execution on both sides.
        entry_slippage = (pos.entry_price - pos.cost_basis / pos.shares) * pos.shares
        exit_slippage = (raw_exit_price - exit_price) * pos.shares
        slippage_cost = max(0.0, entry_slippage) + max(0.0, exit_slippage)

        net_pnl = gross_pnl - transaction_cost

        self.cash += exit_price * pos.shares - exit_cost

        holding_days = int((date - pos.entry_date).days)

        self.trades.append(
            Trade(
                symbol=symbol,
                entry_date=pos.entry_date,
                exit_date=date,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                shares=pos.shares,
                exit_reason=reason,
                gross_pnl=gross_pnl,
                transaction_cost=transaction_cost,
                slippage_cost=slippage_cost,
                net_pnl=net_pnl,
                holding_days=holding_days,
            )
        )

    def _mark_to_market(self, date: pd.Timestamp) -> float:
        equity = self.cash
        for symbol, pos in self.positions.items():
            df = self.data[symbol]
            if date in df.index:
                equity += pos.shares * float(df.loc[date, "Close"])
        return equity

    def _process_exit(self, symbol: str, date: pd.Timestamp, row: pd.Series) -> bool:
        """Return True if a position was closed today.

        If both stop and target are touched in the same daily candle, use the
        conservative stop-first assumption. If the opening price gaps through
        either level, the open is used as the exit price.
        """
        pos = self.positions[symbol]
        o, h, l = map(float, [row["Open"], row["High"], row["Low"]])

        # Opening gap handling.
        if o <= pos.stop_price:
            self._close_position(symbol, date, o, "stop_loss_gap")
            return True
        if o >= pos.target_price:
            self._close_position(symbol, date, o, "take_profit_gap")
            return True

        stop_hit = l <= pos.stop_price
        target_hit = h >= pos.target_price

        if stop_hit and target_hit:
            self._close_position(symbol, date, pos.stop_price, "stop_loss_same_bar")
            return True
        if stop_hit:
            self._close_position(symbol, date, pos.stop_price, "stop_loss")
            return True
        if target_hit:
            self._close_position(symbol, date, pos.target_price, "take_profit")
            return True

        holding_days = int((date - pos.entry_date).days)
        if holding_days >= self.config.max_holding_days:
            self._close_position(symbol, date, float(row["Close"]), "max_holding_period")
            return True

        return False

    def run(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Run the backtest and return trades and daily equity."""
        all_dates = sorted(
            set().union(*(df.index.tolist() for df in self.data.values()))
        )

        pending_entries: Dict[pd.Timestamp, List[str]] = {}

        for i, date in enumerate(all_dates):
            # Execute entries scheduled from the previous day's signals.
            for symbol in pending_entries.pop(date, []):
                if symbol in self.data and date in self.data[symbol].index:
                    self._open_position(symbol, date, self.data[symbol].loc[date])

            # Exits are checked before today's new signal generation.
            for symbol in list(self.positions):
                if date in self.data[symbol].index:
                    self._process_exit(symbol, date, self.data[symbol].loc[date])

            # Generate today's signals and schedule entry for next available
            # trading date for that symbol.
            candidates = []
            for symbol, df in self.data.items():
                if date not in df.index:
                    continue
                row = df.loc[date]
                if bool(row["Signal"]):
                    score = float(row["ConfirmationScore"])
                    candidates.append((symbol, score))

            candidates.sort(key=lambda x: x[1], reverse=True)

            slots = self.config.max_positions - len(self.positions)
            for symbol, _score in candidates[:max(0, slots)]:
                if symbol in self.positions:
                    continue

                df = self.data[symbol]
                idx = df.index.get_loc(date)
                if isinstance(idx, slice) or idx + 1 >= len(df.index):
                    continue
                next_date = df.index[idx + 1]
                pending_entries.setdefault(next_date, []).append(symbol)

            self.equity_curve.append(
                {
                    "Date": date,
                    "Cash": self.cash,
                    "Equity": self._mark_to_market(date),
                    "OpenPositions": len(self.positions),
                }
            )

        # Force-close positions at the last available close.
        if all_dates:
            final_date = all_dates[-1]
            for symbol in list(self.positions):
                if final_date in self.data[symbol].index:
                    self._close_position(
                        symbol,
                        final_date,
                        float(self.data[symbol].loc[final_date, "Close"]),
                        "end_of_backtest",
                    )

            self.equity_curve.append(
                {
                    "Date": final_date,
                    "Cash": self.cash,
                    "Equity": self.cash,
                    "OpenPositions": 0,
                }
            )

        trades_df = pd.DataFrame([asdict(t) for t in self.trades])
        equity_df = pd.DataFrame(self.equity_curve)
        if not equity_df.empty:
            equity_df = equity_df.drop_duplicates("Date").sort_values("Date")
        return trades_df, equity_df


def performance_summary(
    trades: pd.DataFrame, equity: pd.DataFrame, initial_capital: float
) -> dict:
    """Calculate standard backtest summary statistics."""
    if equity.empty:
        return {
            "initial_capital": initial_capital,
            "final_equity": initial_capital,
            "net_profit": 0.0,
            "return_pct": 0.0,
            "trade_count": 0,
            "win_rate_pct": 0.0,
            "max_drawdown_pct": 0.0,
        }

    curve = equity["Equity"].astype(float)
    running_max = curve.cummax()
    drawdown = curve / running_max - 1.0

    trade_count = len(trades)
    win_rate = (
        float((trades["net_pnl"] > 0).mean() * 100)
        if trade_count
        else 0.0
    )

    final_equity = float(curve.iloc[-1])
    return {
        "initial_capital": float(initial_capital),
        "final_equity": final_equity,
        "net_profit": final_equity - initial_capital,
        "return_pct": (final_equity / initial_capital - 1) * 100,
        "trade_count": trade_count,
        "win_rate_pct": win_rate,
        "max_drawdown_pct": float(drawdown.min() * 100),
        "average_trade_pnl": (
            float(trades["net_pnl"].mean()) if trade_count else 0.0
        ),
    }
