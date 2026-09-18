"""NIFTY 50 swing-trading strategy.

Strategy:
- Daily candles
- EMA(20) > EMA(50) trend filter
- Close breaks above the highest High of the prior 20 sessions
- RSI(14) > 50 confirmation
- Volume > prior-20-session average volume confirmation
- Trend + breakout are mandatory.
- RSI and volume are used for candidate confirmation/ranking.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StrategyConfig:
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    breakout_period: int = 20
    volume_period: int = 20
    rsi_threshold: float = 50.0


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Compute Wilder-style RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # Constant/rising prices can produce zero average loss.
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    return rsi


def add_indicators(df: pd.DataFrame, config: StrategyConfig | None = None) -> pd.DataFrame:
    """Return OHLCV data with strategy indicators and signal components."""
    config = config or StrategyConfig()
    out = df.copy()

    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    out = out.sort_index()
    out["EMA20"] = out["Close"].ewm(
        span=config.ema_fast, adjust=False, min_periods=config.ema_fast
    ).mean()
    out["EMA50"] = out["Close"].ewm(
        span=config.ema_slow, adjust=False, min_periods=config.ema_slow
    ).mean()
    out["RSI14"] = compute_rsi(out["Close"], config.rsi_period)

    # Shift(1) is essential: today's close is compared with the
    # highest high of the PREVIOUS 20 sessions, excluding today.
    out["Prior20High"] = out["High"].shift(1).rolling(
        config.breakout_period, min_periods=config.breakout_period
    ).max()
    out["Prior20AvgVolume"] = out["Volume"].shift(1).rolling(
        config.volume_period, min_periods=config.volume_period
    ).mean()

    out["TrendOK"] = out["EMA20"] > out["EMA50"]
    out["BreakoutOK"] = out["Close"] > out["Prior20High"]
    out["RSIOK"] = out["RSI14"] > config.rsi_threshold
    out["VolumeOK"] = out["Volume"] > out["Prior20AvgVolume"]

    # Mandatory conditions: trend + breakout.
    out["Signal"] = out["TrendOK"] & out["BreakoutOK"]

    # Confirmation score is bounded to 0..2.
    out["RSINormalized"] = ((out["RSI14"] - config.rsi_threshold) / 50.0).clip(0, 1)
    out["VolumeRatio"] = (
        out["Volume"] / out["Prior20AvgVolume"].replace(0, np.nan)
    )
    out["VolumeNormalized"] = (out["VolumeRatio"] - 1.0).clip(0, 1)
    out["ConfirmationScore"] = (
        out["RSINormalized"].fillna(0) + out["VolumeNormalized"].fillna(0)
    )

    return out


def generate_candidates(
    symbol_data: dict[str, pd.DataFrame],
    config: StrategyConfig | None = None,
    max_candidates: int = 5,
) -> pd.DataFrame:
    """Generate and rank today's qualifying candidates across symbols."""
    rows = []

    for symbol, df in symbol_data.items():
        if df.empty:
            continue

        ind = add_indicators(df, config)
        row = ind.iloc[-1]

        if bool(row["Signal"]):
            rows.append(
                {
                    "Symbol": symbol,
                    "Date": ind.index[-1],
                    "Close": float(row["Close"]),
                    "RSI14": float(row["RSI14"]) if pd.notna(row["RSI14"]) else np.nan,
                    "VolumeRatio": (
                        float(row["VolumeRatio"])
                        if pd.notna(row["VolumeRatio"])
                        else np.nan
                    ),
                    "ConfirmationScore": float(row["ConfirmationScore"]),
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "Symbol", "Date", "Close", "RSI14",
                "VolumeRatio", "ConfirmationScore"
            ]
        )

    candidates = pd.DataFrame(rows).sort_values(
        ["ConfirmationScore", "RSI14", "VolumeRatio"],
        ascending=False,
    )
    return candidates.head(max_candidates).reset_index(drop=True)
