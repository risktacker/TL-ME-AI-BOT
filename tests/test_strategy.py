import pandas as pd
from config import Settings
from strategy import indicators, signal_series


def sample_frame(n=260):
    t = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    close = pd.Series(range(n), dtype=float) + 100
    return pd.DataFrame({"time": t, "open": close - 0.1, "high": close + 0.5,
                         "low": close - 0.5, "close": close})


def test_indicators_are_available():
    data = indicators(sample_frame(), Settings())
    assert {"ema_fast", "ema_slow", "atr", "range_high", "range_low"} <= set(data.columns)


def test_uptrend_breakout_can_signal():
    signals = signal_series(sample_frame(), Settings())
    assert int(signals.max()) == 1
