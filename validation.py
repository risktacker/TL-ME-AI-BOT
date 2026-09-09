"""Full-period, rolling-regime, holdout, and Monte Carlo validation."""
from __future__ import annotations
from dataclasses import dataclass, replace
import numpy as np
import pandas as pd
from backtest import run_backtest
from config import Settings


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    reasons: tuple[str, ...]
    full_period: dict
    holdout: dict
    positive_periods: int
    total_periods: int
    worst_period_r: float
    monte_carlo_95_drawdown_r: float
    monte_carlo_95_drawdown_pct: float
    profitable_bootstrap_fraction: float
    walk_forward: dict
    cost_stress: dict


def _walk_forward(frame: pd.DataFrame, settings: Settings, folds: int = 5) -> dict:
    """Evaluate consecutive unseen time blocks; no parameters are fitted per fold."""
    block = len(frame) // folds
    summaries = []
    for index in range(folds):
        start, end = index * block, len(frame) if index == folds - 1 else (index + 1) * block
        warmup = max(0, start - 800)
        result = run_backtest(frame.iloc[warmup:end].reset_index(drop=True), settings)
        trades = result.trades
        if not trades.empty and start > 0:
            cutoff = pd.to_datetime(frame.iloc[start]["time"], utc=True)
            trades = trades[pd.to_datetime(trades["entry_time"], utc=True) >= cutoff]
        summaries.append(type(result)(trades.reset_index(drop=True), result.starting_equity).summary())
    return {"folds": summaries, "positive_folds": sum(item["net_r"] > 0 for item in summaries),
            "total_trades": sum(item["trades"] for item in summaries),
            "net_r": round(sum(item["net_r"] for item in summaries), 4)}


def _bootstrap(returns: np.ndarray, seed: int, simulations: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    ending, drawdowns = np.empty(simulations), np.empty(simulations)
    for index in range(simulations):
        sample = rng.choice(returns, size=len(returns), replace=True)
        curve = np.cumsum(sample)
        peak = np.maximum.accumulate(np.maximum(curve, 0))
        ending[index] = curve[-1]
        drawdowns[index] = np.max(peak - curve)
    return float(np.mean(ending > 0)), float(np.quantile(drawdowns, 0.95))


def validate_strategy(frame: pd.DataFrame, settings: Settings, seed: int = 42,
                      simulations: int = 2000) -> ValidationReport:
    if len(frame) < 5000:
        return ValidationReport(False, ("insufficient_history",), {}, {}, 0, 0, 0, 0, 0, 0, {}, {})
    full = run_backtest(frame, settings)
    full_summary = full.summary()
    split = int(len(frame) * 0.70)
    holdout_summary = run_backtest(frame.iloc[split:].reset_index(drop=True), settings).summary()
    if full.trades.empty:
        return ValidationReport(False, ("no_trades",), full_summary, holdout_summary, 0, 0, 0, 0, 0, 0, {}, {})
    times = pd.to_datetime(frame["time"], utc=True)
    period_results = []
    for _, indices in frame.groupby(times.dt.tz_localize(None).dt.to_period("Q")).groups.items():
        segment = frame.loc[indices].reset_index(drop=True)
        if len(segment) >= 500:
            period_results.append(run_backtest(segment, settings).summary()["net_r"])
    positive_periods = sum(value > 0 for value in period_results)
    profitable, dd95 = _bootstrap(full.trades["r"].to_numpy(float), seed, simulations)
    reasons: list[str] = []
    if full_summary["trades"] < 100: reasons.append("fewer_than_100_full_period_trades")
    if full_summary["expectancy_r"] <= 0: reasons.append("non_positive_full_expectancy")
    if full_summary["profit_factor"] < 1.20: reasons.append("full_profit_factor_below_1_20")
    if holdout_summary.get("expectancy_r", 0) <= 0: reasons.append("non_positive_holdout_expectancy")
    if period_results and positive_periods < max(1, len(period_results) - 1): reasons.append("unstable_rolling_periods")
    if profitable < 0.90: reasons.append("bootstrap_profit_probability_below_90pct")
    dd95_pct = dd95 * settings.risk_per_trade_pct
    if dd95_pct > 0.04: reasons.append("monte_carlo_drawdown_above_4pct")
    walk = _walk_forward(frame, settings)
    if walk["positive_folds"] < 4: reasons.append("walk_forward_fewer_than_4_positive_folds")
    stressed_settings = replace(settings, spread_price=settings.spread_price * 1.5,
                                  point_price=settings.point_price * 1.5,
                                  slippage_price=settings.slippage_price * 2)
    stress = run_backtest(frame, stressed_settings).summary()
    if stress["expectancy_r"] <= 0 or stress["profit_factor"] < 1.05:
        reasons.append("fails_150pct_spread_200pct_slippage_stress")
    return ValidationReport(not reasons, tuple(reasons), full_summary, holdout_summary,
                            positive_periods, len(period_results), round(min(period_results), 4),
                            round(dd95, 4), round(dd95_pct, 4), round(profitable, 4), walk, stress)
