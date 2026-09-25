"""Objective price-action features used by the strategy package.

The functions deliberately encode FVG/IFVG/BOS/liquidity terminology into
reproducible candle rules so it can be tested instead of interpreted by eye.
"""
from __future__ import annotations

import pandas as pd


def add_price_action_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    body = (out["close"] - out["open"]).abs()
    out["bull_displacement"] = (out["close"] > out["open"]) & (body >= out["atr"] * out.attrs.get("displacement_body_atr", 0.55))
    out["bear_displacement"] = (out["close"] < out["open"]) & (body >= out["atr"] * out.attrs.get("displacement_body_atr", 0.55))

    # Three-candle imbalance: candle 1 high/low does not overlap candle 3.
    out["bull_fvg"] = out["low"] > out["high"].shift(2)
    out["bear_fvg"] = out["high"] < out["low"].shift(2)

    # Inversion: price closes through the opposite edge of a recent FVG.
    bull_floor = out["low"].where(out["bull_fvg"]).ffill(limit=8)
    bear_ceiling = out["high"].where(out["bear_fvg"]).ffill(limit=8)
    out["bear_ifvg"] = bull_floor.notna() & (out["close"] < bull_floor) & (out["close"].shift(1) >= bull_floor.shift(1))
    out["bull_ifvg"] = bear_ceiling.notna() & (out["close"] > bear_ceiling) & (out["close"].shift(1) <= bear_ceiling.shift(1))

    prior_high = out["high"].shift(1).rolling(8).max()
    prior_low = out["low"].shift(1).rolling(8).min()
    out["bull_bos"] = out["close"] > prior_high
    out["bear_bos"] = out["close"] < prior_low
    out["sell_liquidity_sweep"] = (out["low"] < prior_low) & (out["close"] > prior_low)
    out["buy_liquidity_sweep"] = (out["high"] > prior_high) & (out["close"] < prior_high)
    return out

