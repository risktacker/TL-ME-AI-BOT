"""Risk controls. No martingale and no balance-chasing."""
from __future__ import annotations
from dataclasses import dataclass
from config import Settings


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    risk_amount: float
    stop_distance: float


def approve_trade(equity: float, daily_pnl: float, stop_distance: float, settings: Settings) -> RiskDecision:
    if equity <= 0 or stop_distance <= 0:
        return RiskDecision(False, "invalid equity or stop distance", 0.0, stop_distance)
    if daily_pnl <= -equity * settings.max_daily_loss_pct:
        return RiskDecision(False, "daily loss limit reached", 0.0, stop_distance)
    risk_amount = equity * settings.risk_per_trade_pct
    return RiskDecision(True, "approved", risk_amount, stop_distance)


def volume_from_risk(risk_amount: float, stop_distance: float, tick_size: float,
                     tick_value: float, volume_step: float, min_volume: float, max_volume: float) -> float:
    if min(tick_size, tick_value, volume_step, stop_distance) <= 0:
        raise ValueError("Invalid symbol risk metadata")
    raw = risk_amount / ((stop_distance / tick_size) * tick_value)
    stepped = (raw // volume_step) * volume_step
    return round(max(min_volume, min(max_volume, stepped)), 8)
