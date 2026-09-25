"""Append-only trade journal for reproducible research."""
from __future__ import annotations
from pathlib import Path
import pandas as pd


def append_trade(row: dict, path: str = "data/trades.csv") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(target, mode="a", header=not target.exists(), index=False)
