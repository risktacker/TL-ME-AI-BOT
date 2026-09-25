"""High-impact event blackout filter using an externally maintained CSV."""
from __future__ import annotations

from pathlib import Path
import pandas as pd


def load_events(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        return pd.DataFrame(columns=["time", "currency", "impact", "event"])
    events = pd.read_csv(source, parse_dates=["time"])
    events["time"] = pd.to_datetime(events["time"], utc=True)
    return events


def high_impact_blackout(now: pd.Timestamp, events: pd.DataFrame,
                         minutes_before: int = 30, minutes_after: int = 30) -> bool:
    if events.empty:
        return False
    now = pd.Timestamp(now).tz_convert("UTC") if pd.Timestamp(now).tzinfo else pd.Timestamp(now, tz="UTC")
    high = events[(events["impact"].str.lower() == "high") & events["currency"].isin(["USD", "ALL"])]
    delta = (high["time"] - now).dt.total_seconds() / 60
    return bool(delta.between(-minutes_after, minutes_before).any())

