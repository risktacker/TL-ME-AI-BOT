"""Controlled benchmark of established M15 intraday strategy families."""
from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import product
import numpy as np
import pandas as pd

from config import Settings
from strategy import indicators


@dataclass(frozen=True)
class CandidateResult:
    name: str
    stop_atr: float
    target_r: float
    hold_bars: int
    trades: int
    net_r: float
    expectancy: float
    profit_factor: float
    win_rate: float
    max_drawdown: float
    positive_quarters: int
    worst_quarter_r: float
    score: float


def _features(frame: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    d = indicators(frame, settings)
    d["ema20"] = d.close.ewm(span=20, adjust=False).mean()
    d["ema50"] = d.close.ewm(span=50, adjust=False).mean()
    d["donchian_high"] = d.high.shift(1).rolling(20).max()
    d["donchian_low"] = d.low.shift(1).rolling(20).min()
    d["range10_high"] = d.high.shift(1).rolling(10).max()
    d["range10_low"] = d.low.shift(1).rolling(10).min()
    returns = d.close.pct_change()
    d["realized_vol"] = returns.rolling(12).std()
    d["vol_rank"] = d.realized_vol.rolling(96).rank(pct=True)
    delta = d.close.diff()
    up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + up / down.replace(0, np.nan))
    return d


def candidate_signals(data: pd.DataFrame) -> dict[str, pd.Series]:
    entry_window = data.session_minute.ge(60)
    liquid_hours = data.time.dt.hour.between(6, 16)
    h1_up, h1_down = data.trend_fast.gt(data.trend_slow), data.trend_fast.lt(data.trend_slow)
    h4_up, h4_down = data.h4_fast.gt(data.h4_slow), data.h4_fast.lt(data.h4_slow)
    active_vol = data.atr.gt(data.atr_median * 0.85) & data.atr.lt(data.atr_median * 2.0)
    body = (data.close - data.open).abs()
    displacement = body.gt(data.atr * 0.45)

    raw: dict[str, pd.Series] = {}
    raw["orb_h1_h4"] = pd.Series(np.select([
        entry_window & h1_up & h4_up & active_vol & displacement & data.close.gt(data.opening_high),
        entry_window & h1_down & h4_down & active_vol & displacement & data.close.lt(data.opening_low),
    ], [1, -1], default=0), index=data.index)
    raw["donchian_h1_h4"] = pd.Series(np.select([
        liquid_hours & h1_up & h4_up & active_vol & data.close.gt(data.donchian_high),
        liquid_hours & h1_down & h4_down & active_vol & data.close.lt(data.donchian_low),
    ], [1, -1], default=0), index=data.index)
    compression = data.vol_rank.shift(1).lt(0.25)
    raw["compression_breakout"] = pd.Series(np.select([
        liquid_hours & h1_up & h4_up & compression & data.close.gt(data.range10_high),
        liquid_hours & h1_down & h4_down & compression & data.close.lt(data.range10_low),
    ], [1, -1], default=0), index=data.index)
    raw["trend_pullback"] = pd.Series(np.select([
        liquid_hours & h1_up & h4_up & data.low.le(data.ema20) & data.close.gt(data.ema20) & data.close.gt(data.open) & data.rsi.between(45, 65),
        liquid_hours & h1_down & h4_down & data.high.ge(data.ema20) & data.close.lt(data.ema20) & data.close.lt(data.open) & data.rsi.between(35, 55),
    ], [1, -1], default=0), index=data.index)
    raw["session_sweep_reversal"] = pd.Series(np.select([
        entry_window & h1_up & data.low.lt(data.opening_low) & data.close.gt(data.opening_low) & data.close.gt(data.open),
        entry_window & h1_down & data.high.gt(data.opening_high) & data.close.lt(data.opening_high) & data.close.lt(data.open),
    ], [1, -1], default=0), index=data.index)

    # Debounce to one setup per session/day for every family.
    day = data.time.dt.strftime("%Y-%m-%d")
    for name, signal in raw.items():
        key = data.session_key.where(data.session_key.ne(""), "day:" + day)
        fired = signal.ne(0)
        prior = fired.groupby(key).cumsum() - fired.astype(int)
        signal.loc[fired & prior.gt(0)] = 0
    return raw


def simulate(data: pd.DataFrame, signal: pd.Series, stop_atr: float, target_r: float,
             hold_bars: int, point: float = 0.001, slippage: float = 0.05) -> pd.DataFrame:
    trades = []
    available = 0
    for i in range(len(data) - 1):
        side = int(signal.iloc[i])
        if side == 0 or i < available or not data.iloc[i].atr > 0:
            continue
        entry = float(data.iloc[i + 1].open)
        risk = float(data.iloc[i].atr) * stop_atr
        stop = entry - side * risk
        target = entry + side * risk * target_r
        end = min(len(data) - 1, i + hold_bars)
        outcome, exit_i = None, None
        for j in range(i + 1, end + 1):
            hi, lo, close = float(data.iloc[j].high), float(data.iloc[j].low), float(data.iloc[j].close)
            if (side == 1 and lo <= stop) or (side == -1 and hi >= stop):
                outcome, exit_i = -1.0, j; break
            if (side == 1 and hi >= target) or (side == -1 and lo <= target):
                outcome, exit_i = target_r, j; break
            if j == end:
                outcome, exit_i = max(-1.0, min(target_r, side * (close-entry)/risk)), j
        if outcome is None:
            continue
        spread_cost = float(data.iloc[i + 1].spread) * point if "spread" in data else 0.24
        net_r = outcome - (spread_cost + 2 * slippage) / risk
        trades.append({"time": data.iloc[i + 1].time, "r": net_r, "side": side})
        available = exit_i + 1
    return pd.DataFrame(trades)


def summarize(name: str, params: tuple[float, float, int], trades: pd.DataFrame) -> CandidateResult:
    stop, target, hold = params
    if trades.empty:
        return CandidateResult(name, stop, target, hold, 0, 0, 0, 0, 0, 0, 0, 0, -999)
    r = trades.r
    curve = r.cumsum(); dd = curve.cummax().clip(lower=0) - curve
    losses = abs(r[r < 0].sum()); pf = float(r[r > 0].sum()/losses) if losses else 99.0
    quarter = trades.time.dt.tz_localize(None).dt.to_period("Q")
    q = trades.assign(q=quarter).groupby("q").r.sum()
    positive = int((q > 0).sum()); worst = float(q.min())
    # Penalize instability and drawdown; reward expectancy only with enough trades.
    score = float(r.mean() * np.sqrt(len(r)) + 0.03 * positive + 0.01 * worst - 0.002 * dd.max())
    return CandidateResult(name, stop, target, hold, len(r), float(r.sum()), float(r.mean()),
                           pf, float((r > 0).mean()), float(dd.max()), positive, worst, score)


def benchmark(frame: pd.DataFrame, settings: Settings | None = None,
              point: float = 0.001, slippage: float = 0.05) -> pd.DataFrame:
    settings = settings or Settings()
    data = _features(frame, settings)
    signals = candidate_signals(data)
    split_time = pd.to_datetime(frame.iloc[int(len(frame) * 0.70)].time, utc=True)
    rows = []
    for name, signal in signals.items():
        # Deliberately small grid: enough to test parameter neighbourhoods,
        # without mining hundreds of combinations from one year of data.
        for params in product((1.0, 1.5), (1.25, 1.5, 1.75), (8, 12)):
            trades = simulate(data, signal, *params, point=point, slippage=slippage)
            train = summarize(name, params, trades[trades.time < split_time].reset_index(drop=True))
            holdout = summarize(name, params, trades[trades.time >= split_time].reset_index(drop=True))
            full = summarize(name, params, trades)
            row = full.__dict__.copy()
            row.update({
                "train_trades": train.trades, "train_expectancy": train.expectancy,
                "train_profit_factor": train.profit_factor,
                "holdout_trades": holdout.trades, "holdout_net_r": holdout.net_r,
                "holdout_expectancy": holdout.expectancy,
                "holdout_profit_factor": holdout.profit_factor,
                "holdout_max_drawdown": holdout.max_drawdown,
            })
            # Ranking requires both seen and unseen profitability; this is not a
            # parameter fit on the holdout, only a robustness rejection gate.
            row["robust_score"] = (min(train.expectancy, holdout.expectancy) * np.sqrt(max(1, holdout.trades))
                                   - 0.01 * holdout.max_drawdown)
            rows.append(row)
    return pd.DataFrame(rows).sort_values("robust_score", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("--point", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.05)
    args = parser.parse_args()
    frame = pd.read_csv(args.data, parse_dates=["time"])
    results = benchmark(frame, point=args.point, slippage=args.slippage)
    print(results.groupby("name").head(3).to_string(index=False))
