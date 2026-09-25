"""Market-data validation and closed-candle handling."""
from __future__ import annotations
import pandas as pd

REQUIRED = ("time", "open", "high", "low", "close")


def validate_ohlc(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(f"Missing OHLC columns: {missing}")
    out = frame.copy()
    out["time"] = pd.to_datetime(out["time"], utc=True)
    for col in REQUIRED[1:]:
        out[col] = pd.to_numeric(out[col], errors="raise")
    out = out.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    if (out["high"] < out[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high below an open/close/low")
    if (out["low"] > out[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low above an open/close/high")
    return out
