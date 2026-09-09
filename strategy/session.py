"""DST-aware London and New York opening ranges for UTC candle data."""
from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo
import pandas as pd


SESSIONS = {
    "london": (ZoneInfo("Europe/London"), time(8, 0)),
    "new_york": (ZoneInfo("America/New_York"), time(8, 30)),
}


def add_session_ranges(frame: pd.DataFrame, opening_minutes: int, entry_minutes: int,
                       use_london: bool = True, use_new_york: bool = True) -> pd.DataFrame:
    out = frame.copy()
    out["session"] = ""
    out["session_key"] = ""
    out["session_minute"] = -1
    out["opening_high"] = float("nan")
    out["opening_low"] = float("nan")
    enabled = {"london": use_london, "new_york": use_new_york}

    utc = pd.DatetimeIndex(out["time"])
    for name, (zone, start) in SESSIONS.items():
        if not enabled[name]:
            continue
        local = utc.tz_convert(zone)
        minutes = local.hour * 60 + local.minute - (start.hour * 60 + start.minute)
        key = pd.Series(local.date.astype(str), index=out.index)
        in_scope = (minutes >= 0) & (minutes < opening_minutes + entry_minutes)
        opening = (minutes >= 0) & (minutes < opening_minutes)
        for day in key[in_scope].unique():
            scope_idx = out.index[in_scope & (key == day)]
            opening_idx = out.index[opening & (key == day)]
            if len(opening_idx) == 0:
                continue
            out.loc[scope_idx, "session"] = name
            out.loc[scope_idx, "session_key"] = f"{name}:{day}"
            out.loc[scope_idx, "session_minute"] = minutes[scope_idx]
            out.loc[scope_idx, "opening_high"] = out.loc[opening_idx, "high"].max()
            out.loc[scope_idx, "opening_low"] = out.loc[opening_idx, "low"].min()
    return out

