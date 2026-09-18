import pandas as pd
import numpy as np

from src.strategy import StrategyConfig, add_indicators, compute_rsi


def make_data(n=80):
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    close = np.linspace(100, 150, n)
    high = close + 1
    low = close - 1
    open_ = close - 0.25
    volume = np.full(n, 1000.0)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def test_rsi_is_bounded():
    df = make_data()
    rsi = compute_rsi(df["Close"])
    valid = rsi.dropna()
    assert ((valid >= 0) & (valid <= 100)).all()


def test_prior_breakout_excludes_current_high():
    df = make_data()
    df.loc[df.index[-1], "Close"] = 151
    df.loc[df.index[-1], "High"] = 151

    out = add_indicators(df, StrategyConfig())
    prior = out["High"].iloc[:-1].tail(20).max()

    assert out["Prior20High"].iloc[-1] == prior
    assert out["BreakoutOK"].iloc[-1] is True or bool(out["BreakoutOK"].iloc[-1])
