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
    joined = pd.merge_asof(
        data.sort_values("time"), hourly[["trend_fast", "trend_slow"]].reset_index(),
        on="time", direction="backward", allow_exact_matches=True,
    )
    h4 = indexed["close"].resample("4h", closed="left", label="right").last().dropna().to_frame()
    h4["h4_fast"] = h4["close"].ewm(span=settings.h4_fast_ema, adjust=False).mean()
    h4["h4_slow"] = h4["close"].ewm(span=settings.h4_slow_ema, adjust=False).mean()
    return pd.merge_asof(joined.sort_values("time"), h4[["h4_fast", "h4_slow"]].reset_index(),
                         on="time", direction="backward", allow_exact_matches=True)


def indicators(frame: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    data = _higher_timeframe_trend(validate_ohlc(frame), settings)
    data["atr"] = _atr(data, settings.atr_period)
    data["atr_median"] = data["atr"].rolling(settings.atr_median_period).median()
    data["donchian_high"] = data["high"].shift(1).rolling(settings.breakout_bars).max()
    data["donchian_low"] = data["low"].shift(1).rolling(settings.breakout_bars).min()
    data.attrs["displacement_body_atr"] = settings.displacement_body_atr
    data = add_price_action_features(data)
    return add_session_ranges(
        data, settings.opening_range_minutes, settings.entry_window_minutes,
        settings.use_london, settings.use_new_york,
    )


def signal_series(frame: pd.DataFrame, settings: Settings) -> pd.Series:
    data = indicators(frame, settings)
    atr_ratio = data["atr"] / data["atr_median"]
    volatility_ok = atr_ratio.between(0.85, 2.0)
    spread = data["spread"] * settings.point_price if "spread" in data else settings.spread_price
    cost_ok = (spread / data["atr"]) <= settings.max_spread_atr
    trend_up = data["trend_fast"] > data["trend_slow"]
    trend_down = data["trend_fast"] < data["trend_slow"]
    h4_up = data["h4_fast"] > data["h4_slow"]
    h4_down = data["h4_fast"] < data["h4_slow"]
    liquid_hours = data["time"].dt.hour.between(6, 16)
    displacement = (data["close"] - data["open"]).abs() >= settings.displacement_body_atr * data["atr"]
    common = liquid_hours & volatility_ok & cost_ok & displacement
    long_signal = common & trend_up & h4_up & (data["close"] > data["donchian_high"])
    short_signal = common & trend_down & h4_down & (data["close"] < data["donchian_low"])
    raw = pd.Series(0, index=data.index, dtype="int8")
    raw.loc[long_signal.fillna(False)] = 1
    raw.loc[short_signal.fillna(False)] = -1
    # The tested edge is the first qualified breakout for this market-day. This
    # is signal de-duplication, not a loss shutdown; other markets keep scanning.
    fired = raw.ne(0)
    prior_today = fired.groupby(data["time"].dt.strftime("%Y-%m-%d")).cumsum() - fired.astype(int)
    raw.loc[fired & prior_today.gt(0)] = 0
    scores = pd.Series((_edge_score(data.iloc[index], int(raw.iloc[index]))
                        for index in range(len(data))), index=data.index, dtype=float)
    raw.loc[raw.ne(0) & scores.lt(settings.minimum_edge_score)] = 0
    raw.attrs["edge_scores"] = scores
    raw.attrs["data"] = data
    return raw


def _edge_score(row: pd.Series, signal: int) -> float:
    """Rank valid setups using dimensionless momentum and structure inputs."""
    atr = float(row["atr"])
    if not atr > 0 or signal == 0:
        return 0.0
    direction = float(signal)
    displacement = abs(float(row["close"] - row["open"])) / atr
    h1_separation = direction * float(row["trend_fast"] - row["trend_slow"]) / atr
    h4_separation = direction * float(row["h4_fast"] - row["h4_slow"]) / atr
    level = float(row["donchian_high"] if signal == 1 else row["donchian_low"])
    breakout = direction * float(row["close"] - level) / atr
    structure = int(bool(row["bull_bos"] if signal == 1 else row["bear_bos"]))
    imbalance = int(bool((row["bull_fvg"] or row["bull_ifvg"]) if signal == 1
                         else (row["bear_fvg"] or row["bear_ifvg"])))
    return round(displacement + max(0.0, h1_separation) + max(0.0, h4_separation)
                 + max(0.0, breakout) + structure + 0.5 * imbalance, 4)


def generate_signal(frame: pd.DataFrame, settings: Settings) -> dict:
    signals = signal_series(frame, settings)
    data = signals.attrs["data"]
    if data.empty:
        return {"symbol": settings.symbol, "signal": 0, "reason": "no_data"}
    row = data.iloc[-1]
    signal = int(signals.iloc[-1])
    score = float(signals.attrs["edge_scores"].iloc[-1])
    return {
        "symbol": settings.symbol, "strategy": settings.strategy_name, "signal": signal,
        "side": "buy" if signal == 1 else "sell" if signal == -1 else "flat",
        "edge_score": score,
        "qualified": bool(signal),
        "session": row["session"],
        "atr": None if pd.isna(row["atr"]) else float(row["atr"]),
        "opening_high": None if pd.isna(row["opening_high"]) else float(row["opening_high"]),
        "opening_low": None if pd.isna(row["opening_low"]) else float(row["opening_low"]),
    }
