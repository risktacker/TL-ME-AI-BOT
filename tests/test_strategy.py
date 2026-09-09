import pandas as pd
from config import Settings
from strategy import indicators, signal_series


def sample_frame(days=8):
    time = pd.date_range("2026-01-05", periods=days * 24 * 4, freq="15min", tz="UTC")
    base = pd.Series(range(len(time)), dtype=float) * 0.04 + 2500
    return pd.DataFrame({"time": time, "open": base - 0.03, "high": base + 0.10,
                         "low": base - 0.10, "close": base})


def test_strategy_builds_required_features():
    data = indicators(sample_frame(), Settings())
    required = {"atr", "trend_fast", "trend_slow", "opening_high", "opening_low",
                "bull_fvg", "bear_fvg", "bull_ifvg", "bear_ifvg", "bull_bos", "bear_bos"}
    assert required <= set(data.columns)


def test_signals_are_discrete_and_session_bound():
    signals = signal_series(sample_frame(), Settings(confirmation_score=1, spread_price=0.01))
    data = signals.attrs["data"]
    assert set(signals.unique()) <= {-1, 0, 1}
    assert (data.loc[signals.ne(0), "session"] != "").all()

