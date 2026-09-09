"""Out-of-sample and Monte Carlo validation utilities."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from backtest import run_backtest
from config import Settings


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    reasons: tuple[str, ...]
    out_of_sample: dict
    monte_carlo_95_drawdown_r: float
    profitable_bootstrap_fraction: float


def validate_strategy(frame: pd.DataFrame, settings: Settings, seed: int = 42,
                      simulations: int = 2000) -> ValidationReport:
    if len(frame) < 1000:
        return ValidationReport(False, ("insufficient_history",), {}, 0.0, 0.0)
    split = int(len(frame) * 0.70)
    out_sample = frame.iloc[split:].reset_index(drop=True)
    result = run_backtest(out_sample, settings)
    summary = result.summary()
    if result.trades.empty:
        return ValidationReport(False, ("no_out_of_sample_trades",), summary, 0.0, 0.0)

    returns = result.trades["r"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    ending = np.empty(simulations)
    drawdowns = np.empty(simulations)
    for index in range(simulations):
        sample = rng.choice(returns, size=len(returns), replace=True)
        curve = np.cumsum(sample)
        peak = np.maximum.accumulate(np.maximum(curve, 0))
        ending[index] = curve[-1]
        drawdowns[index] = np.max(peak - curve)

    profitable = float(np.mean(ending > 0))
    dd95 = float(np.quantile(drawdowns, 0.95))
    reasons: list[str] = []
    if summary["trades"] < 50:
        reasons.append("fewer_than_50_out_of_sample_trades")
    if summary["expectancy_r"] <= 0:
        reasons.append("non_positive_expectancy")
    if summary["profit_factor"] < 1.20:
        reasons.append("profit_factor_below_1_20")
    if profitable < 0.80:
        reasons.append("bootstrap_profit_probability_below_80pct")
    if dd95 > 10:
        reasons.append("monte_carlo_drawdown_above_10R")
    return ValidationReport(not reasons, tuple(reasons), summary, round(dd95, 4), round(profitable, 4))

