import pandas as pd
import numpy as np
from config import Settings
from validation import validate_strategy


def test_validation_refuses_too_little_history():
    time = pd.date_range("2026-01-01", periods=100, freq="15min", tz="UTC")
    frame = pd.DataFrame({"time": time, "open": 1, "high": 2, "low": 0, "close": 1})
    report = validate_strategy(frame, Settings())
    assert not report.passed
    assert "insufficient_history" in report.reasons


def test_validation_report_exposes_deeper_gates():
    time = pd.date_range("2025-01-01", periods=5100, freq="15min", tz="UTC")
    close = 2500 + np.sin(np.arange(len(time)) / 30)
    frame = pd.DataFrame({"time": time, "open": close, "high": close + .2,
                          "low": close - .2, "close": close})
    report = validate_strategy(frame, Settings(), simulations=10)
    assert isinstance(report.walk_forward, dict)
    assert isinstance(report.cost_stress, dict)
