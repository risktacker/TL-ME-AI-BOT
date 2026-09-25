import pandas as pd
from strategy.session import add_session_ranges


def test_london_range_is_dst_aware():
    # In British summer time London 08:00 is 07:00 UTC.
    time = pd.date_range("2026-07-06 06:30", periods=16, freq="15min", tz="UTC")
    frame = pd.DataFrame({"time": time, "open": 1, "high": range(16),
                          "low": range(16), "close": 1})
    out = add_session_ranges(frame, 60, 180, use_london=True, use_new_york=False)
    row = out.loc[out["time"] == pd.Timestamp("2026-07-06 07:00", tz="UTC")].iloc[0]
    assert row["session"] == "london"
    assert row["session_minute"] == 0

