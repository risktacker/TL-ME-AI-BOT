"""Minimal event-driven backtest for the first strategy hypothesis."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from config import Settings
from market_data import validate_ohlc
from strategy import signal_series


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    starting_equity: float

    def summary(self) -> dict:
        if self.trades.empty:
            return {"trades": 0, "net_r": 0.0, "win_rate": 0.0, "max_drawdown_r": 0.0}
        curve = self.trades["r"].cumsum()
        peak = curve.cummax()
        dd = curve - peak
        return {
            "trades": int(len(self.trades)),
            "net_r": round(float(self.trades["r"].sum()), 4),
            "win_rate": round(float((self.trades["r"] > 0).mean()), 4),
            "max_drawdown_r": round(float(abs(dd.min())), 4),
            "avg_r": round(float(self.trades["r"].mean()), 4),
        }


def run_backtest(frame: pd.DataFrame, settings: Settings) -> BacktestResult:
    data = validate_ohlc(frame)
    signals = signal_series(data, settings)
    rows = []
    for i, signal in signals.items():
        if signal == 0 or i + 1 >= len(data):
            continue
        entry = float(data.iloc[i + 1]["open"])
        atr = float(data.iloc[i]["atr"])
        if atr <= 0:
            continue
        stop = entry - settings.stop_atr * atr if signal == 1 else entry + settings.stop_atr * atr
        target = entry + settings.target_r * abs(entry - stop) if signal == 1 else entry - settings.target_r * abs(entry - stop)
        outcome = None
        for j in range(i + 1, len(data)):
            high, low = float(data.iloc[j]["high"]), float(data.iloc[j]["low"])
            if signal == 1 and low <= stop:
                outcome = -1.0; exit_i = j; break
            if signal == -1 and high >= stop:
                outcome = -1.0; exit_i = j; break
            if signal == 1 and high >= target:
                outcome = settings.target_r; exit_i = j; break
            if signal == -1 and low <= target:
                outcome = settings.target_r; exit_i = j; break
        if outcome is not None:
            rows.append({"entry_time": data.iloc[i + 1]["time"], "exit_time": data.iloc[exit_i]["time"], "side": signal, "r": outcome})
    return BacktestResult(pd.DataFrame(rows), settings.starting_equity)
