"""Focused strategy: trend regime + Donchian breakout + ATR filter.

Price action supplies the event. EMA defines the regime and ATR normalises
volatility; indicators are measurement tools, not a pile of entry triggers.
"""
from __future__ import annotations
import pandas as pd
from config import Settings
from core.market_data import validate_ohlc


def indicators(frame: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    data = validate_ohlc(frame)
    data["ema_fast"] = data["close"].ewm(span=settings.fast_ema, adjust=False).mean()
    data["ema_slow"] = data["close"].ewm(span=settings.slow_ema, adjust=False).mean()
    prev_close = data["close"].shift(1)
    tr = pd.concat([
        data["high"] - data["low"],
        (data["high"] - prev_close).abs(),
        (data["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    data["atr"] = tr.rolling(settings.atr_period).mean()
    data["range_high"] = data["high"].shift(1).rolling(settings.breakout_bars).max()
    data["range_low"] = data["low"].shift(1).rolling(settings.breakout_bars).min()
    data["volatility_median"] = data["atr"].rolling(50).median()
    return data


def signal_series(frame: pd.DataFrame, settings: Settings) -> pd.Series:
    data = indicators(frame, settings)
    trend_up = data["ema_fast"] > data["ema_slow"]
    trend_down = data["ema_fast"] < data["ema_slow"]
    active_vol = data["atr"] > data["volatility_median"]
    long_signal = trend_up & (data["close"] > data["range_high"]) & active_vol
    short_signal = trend_down & (data["close"] < data["range_low"]) & active_vol
    signal = pd.Series(0, index=data.index, dtype="int8")
    signal.loc[long_signal.fillna(False)] = 1
    signal.loc[short_signal.fillna(False)] = -1
    signal.attrs["data"] = data
    return signal


def generate_signal(frame: pd.DataFrame, settings: Settings) -> dict:
    data = indicators(frame, settings)
    signals = signal_series(data, settings)
    latest = int(signals.iloc[-1]) if len(signals) else 0
    return {"symbol": settings.symbol, "signal": latest,
            "atr": float(data.iloc[-1]["atr"]) if pd.notna(data.iloc[-1]["atr"]) else None}
