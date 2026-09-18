"""Market-data loading and optional yfinance downloader."""

from __future__ import annotations

from pathlib import Path
import pandas as pd


REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize common OHLCV column layouts."""
    out = df.copy()

    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [c[0] if isinstance(c, tuple) else c for c in out.columns]

    rename = {}
    for col in out.columns:
        key = str(col).strip().lower()
        mapping = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "adj close": "Adj Close",
            "volume": "Volume",
        }
        if key in mapping:
            rename[col] = mapping[key]
    out = out.rename(columns=rename)

    missing = set(REQUIRED_COLUMNS) - set(out.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")

    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)

    return out.sort_index()[REQUIRED_COLUMNS].dropna()


def load_symbol_csv(path: str | Path) -> pd.DataFrame:
    """Load one symbol's OHLCV CSV."""
    df = pd.read_csv(path, parse_dates=["Date"])
    df = df.set_index("Date")
    return normalize_ohlcv(df)


def load_directory(data_dir: str | Path) -> dict[str, pd.DataFrame]:
    """Load all CSV files in a directory as {symbol: OHLCV DataFrame}."""
    data_dir = Path(data_dir)
    result = {}

    for path in sorted(data_dir.glob("*.csv")):
        symbol = path.stem.upper()
        result[symbol] = load_symbol_csv(path)

    if not result:
        raise FileNotFoundError(f"No CSV files found in {data_dir}")

    return result


def download_yfinance(
    symbols: list[str],
    start: str,
    end: str,
    output_dir: str | Path,
) -> None:
    """Download daily OHLCV data using yfinance.

    NSE symbols are expected in Yahoo Finance form, e.g. RELIANCE.NS.
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "yfinance is required for downloading data. "
            "Install dependencies from requirements.txt."
        ) from exc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for symbol in symbols:
        ticker = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        df = yf.download(
            ticker,
            start=start,
            end=end,
            auto_adjust=False,
            progress=False,
        )

        if df.empty:
            print(f"WARNING: no data returned for {symbol}")
            continue

        df = normalize_ohlcv(df)
        df.index.name = "Date"
        df.to_csv(output_dir / f"{symbol.replace('.NS', '')}.csv")
        print(f"Saved {symbol}: {len(df)} rows")
