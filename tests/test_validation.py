import pandas as pd
from config import Settings
from validation import validate_strategy


def test_validation_refuses_too_little_history():
    time = pd.date_range("2026-01-01", periods=100, freq="15min", tz="UTC")
    frame = pd.DataFrame({"time": time, "open": 1, "high": 2, "low": 0, "close": 1})
    report = validate_strategy(frame, Settings())
    assert not report.passed
    assert "insufficient_history" in report.reasons

