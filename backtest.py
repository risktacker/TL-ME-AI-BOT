"""Conservative event backtest with costs, fast exits, and risk lockouts."""
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd
from config import Settings
from strategy import signal_series


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    starting_equity: float

    def summary(self) -> dict:
        if self.trades.empty:
            return {"trades": 0, "net_r": 0.0, "expectancy_r": 0.0,
                    "win_rate": 0.0, "profit_factor": 0.0, "max_drawdown_r": 0.0}
        r = self.trades["r"]
        curve = r.cumsum()
        drawdown = curve - curve.cummax().clip(lower=0)
        wins, losses = r[r > 0].sum(), abs(r[r < 0].sum())
        return {
            "trades": int(len(r)),
            "net_r": round(float(r.sum()), 4),
            "expectancy_r": round(float(r.mean()), 4),
            "win_rate": round(float((r > 0).mean()), 4),
            "profit_factor": round(float(wins / losses), 4) if losses else float("inf"),
            "max_drawdown_r": round(float(abs(drawdown.min())), 4),
            "average_holding_bars": round(float(self.trades["holding_bars"].mean()), 2),
        }


def run_backtest(frame: pd.DataFrame, settings: Settings) -> BacktestResult:
    signals = signal_series(frame, settings)
    data = signals.attrs["data"]
    rows: list[dict] = []
    next_available = 0
    daily: dict[str, dict[str, float | int]] = {}
    cost = settings.spread_price + 2 * settings.slippage_price

    for i in range(len(data) - 1):
        side = int(signals.iloc[i])
        if i < next_available or side == 0:
            continue
        day = str(data.iloc[i]["time"].date())
        state = daily.setdefault(day, {"r": 0.0, "trades": 0, "losses": 0})
        if state["r"] <= -(settings.max_daily_loss_pct / settings.risk_per_trade_pct):
            continue
        if state["trades"] >= settings.max_trades_per_day or state["losses"] >= settings.max_consecutive_losses:
            continue
        atr = float(data.iloc[i]["atr"])
        if not atr > 0:
            continue

        entry = float(data.iloc[i + 1]["open"])
        risk_distance = settings.stop_atr * atr
        stop = entry - risk_distance if side == 1 else entry + risk_distance
        target = entry + settings.target_r * risk_distance if side == 1 else entry - settings.target_r * risk_distance
        outcome = None
        exit_i = None
        exit_reason = ""
        stop_live = stop

        end = min(len(data) - 1, i + settings.max_holding_bars)
        for j in range(i + 1, end + 1):
            high, low, close = map(float, (data.iloc[j]["high"], data.iloc[j]["low"], data.iloc[j]["close"]))
            # Conservative ambiguity policy: stop is checked before target.
            if (side == 1 and low <= stop_live) or (side == -1 and high >= stop_live):
                outcome, exit_i, exit_reason = (-1.0 if stop_live == stop else 0.0), j, "stop"
                break
            if (side == 1 and high >= target) or (side == -1 and low <= target):
                outcome, exit_i, exit_reason = settings.target_r, j, "target"
                break
            break_even_trigger = entry + settings.break_even_at_r * risk_distance if side == 1 else entry - settings.break_even_at_r * risk_distance
            if (side == 1 and high >= break_even_trigger) or (side == -1 and low <= break_even_trigger):
                stop_live = entry
            if j == end:
                raw_r = ((close - entry) * side) / risk_distance
                outcome, exit_i, exit_reason = max(-1.0, min(settings.target_r, raw_r)), j, "time"

        if outcome is None or exit_i is None:
            continue
        # Convert round-trip price costs to R once, including non-binary time exits.
        net_r = outcome - cost / risk_distance
        rows.append({
            "entry_time": data.iloc[i + 1]["time"], "exit_time": data.iloc[exit_i]["time"],
            "session": data.iloc[i]["session"], "side": side, "r": net_r,
            "exit_reason": exit_reason, "holding_bars": exit_i - i,
        })
        state["r"] += net_r
        state["trades"] += 1
        state["losses"] = state["losses"] + 1 if net_r < 0 else 0
        next_available = exit_i + 1
    return BacktestResult(pd.DataFrame(rows), settings.starting_equity)
