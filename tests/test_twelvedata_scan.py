import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location(
    "twelvedata_scan", Path(__file__).resolve().parents[1] / "scripts" / "twelvedata_scan.py"
)
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def frame(close):
    c = pd.Series(close, dtype=float)
    return pd.DataFrame({"open": c, "high": c + 0.1, "low": c - 0.1, "close": c})


def test_straight_uptrend_scores_high_and_long():
    s = scan.score_symbol(frame(np.linspace(100, 120, 120)), 20, 50, 3, 0.25)
    assert s["direction"] == 1 and s["score"] > 0.9


def test_chop_is_blocked():
    chop = 100 + np.tile([0.5, -0.5], 60)
    s = scan.score_symbol(frame(chop), 20, 50, 3, 0.25)
    assert s["direction"] == 0


def test_correlated_pair_keeps_only_the_stronger_trend():
    base = np.cumsum(np.random.default_rng(1).normal(size=200))
    returns = pd.DataFrame({"A": np.diff(base), "B": np.diff(base) * 1.01, "C": np.random.default_rng(2).normal(size=199)})
    scores = {"A": {"direction": 1, "score": 0.6}, "B": {"direction": 1, "score": 0.4}, "C": {"direction": -1, "score": 0.3}}
    out = scan.pick_uncorrelated(scores, returns, 0.8)
    assert out["A"]["direction"] == 1 and out["B"]["direction"] == 0 and out["C"]["direction"] == -1


def test_scan_file_format(tmp_path):
    p = tmp_path / "scan.csv"
    scan.write_scan({"XAU/USD": {"direction": -1, "score": 0.42}}, p)
    assert p.read_text() == "XAUUSD,-1,0.42\n"
