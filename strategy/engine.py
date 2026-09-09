"""Established intraday package: session breakout + trend/momentum + ATR risk."""
from __future__ import annotations

import pandas as pd
from config import Settings
from core.market_data import validate_ohlc
from strategy.price_action import add_price_action_features
from strategy.session import add_session_ranges


def _atr(data: pd.DataFrame, period: int) -> pd.Series:
    previous = data["close"].shift(1)
    true_range = pd.concat((
        data["high"] - data["low"],
        (data["high"] - previous).abs(),
        (data["low"] - previous).abs(),
    ), axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _higher_timeframe_trend(data: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    indexed = data.set_index("time")
    hourly = indexed["close"].resample("1h", closed="left", label="right").last().dropna().to_frame()
    hourly["trend_fast"] = hourly["close"].ewm(span=settings.trend_fast_ema, adjust=False).mean()
    hourly["trend_slow"] = hourly["close"].ewm(span=settings.trend_slow_ema, adjust=False).mean()
    return pd.merge_asof(
        data.sort_values("time"), hourly[["trend_fast", "trend_slow"]].reset_index(),
        on="time", direction="backward", allow_exact_matches=True,
    )


def indicators(frame: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    data = _higher_timeframe_trend(validate_ohlc(frame), settings)
    data["atr"] = _atr(data, settings.atr_period)
    data["atr_median"] = data["atr"].rolling(settings.atr_median_period).median()
    data.attrs["displacement_body_atr"] = settings.displacement_body_atr
    data = add_price_action_features(data)
    return add_session_ranges(
        data, settings.opening_range_minutes, settings.entry_window_minutes,
        settings.use_london, settings.use_new_york,
    )


def signal_series(frame: pd.DataFrame, settings: Settings) -> pd.Series:
    data = indicators(frame, settings)
    entry_window = data["session_minute"] >= settings.opening_range_minutes
    atr_ratio = data["atr"] / data["atr_median"]
    volatility_ok = atr_ratio.between(settings.min_atr_ratio, settings.max_atr_ratio)
    cost_ok = (settings.spread_price / data["atr"]) <= settings.max_spread_atr
    trend_up = data["trend_fast"] > data["trend_slow"]
    trend_down = data["trend_fast"] < data["trend_slow"]
    long_break = data["close"] > data["opening_high"] + settings.breakout_buffer_atr * data["atr"]
    short_break = data["close"] < data["opening_low"] - settings.breakout_buffer_atr * data["atr"]
    long_score = (data["bull_displacement"].astype(int) + data["bull_fvg"].astype(int)
                  + data["bull_bos"].astype(int) + data["bull_ifvg"].astype(int)
                  + data["sell_liquidity_sweep"].astype(int))
    short_score = (data["bear_displacement"].astype(int) + data["bear_fvg"].astype(int)
                   + data["bear_bos"].astype(int) + data["bear_ifvg"].astype(int)
                   + data["buy_liquidity_sweep"].astype(int))
    common = entry_window & volatility_ok & cost_ok & data["opening_high"].notna()
    long_signal = common & trend_up & long_break & (long_score >= settings.confirmation_score)
    short_signal = common & trend_down & short_break & (short_score >= settings.confirmation_score)
    raw = pd.Series(0, index=data.index, dtype="int8")
    raw.loc[long_signal.fillna(False)] = 1
    raw.loc[short_signal.fillna(False)] = -1
    fired = raw.ne(0)
    prior_fired = fired.groupby(data["session_key"]).cumsum() - fired.astype(int)
    raw.loc[fired & prior_fired.gt(0)] = 0
    raw.attrs["data"] = data
    return raw


def generate_signal(frame: pd.DataFrame, settings: Settings) -> dict:
    signals = signal_series(frame, settings)
    data = signals.attrs["data"]
    if data.empty:
        return {"symbol": settings.symbol, "signal": 0, "reason": "no_data"}
    row = data.iloc[-1]
    signal = int(signals.iloc[-1])
    return {
        "symbol": settings.symbol, "strategy": settings.strategy_name, "signal": signal,
        "side": "buy" if signal == 1 else "sell" if signal == -1 else "flat",
        "session": row["session"],
        "atr": None if pd.isna(row["atr"]) else float(row["atr"]),
        "opening_high": None if pd.isna(row["opening_high"]) else float(row["opening_high"]),
        "opening_low": None if pd.isna(row["opening_low"]) else float(row["opening_low"]),
    }

