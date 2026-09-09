"""Hard account-risk gates and broker-aware volume sizing. No martingale."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from config import Settings


@dataclass(frozen=True)
class RiskState:
    daily_pnl: float = 0.0
    consecutive_losses: int = 0
    trades_today: int = 0


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    risk_amount: float
    stop_distance: float


@dataclass(frozen=True)
class VolumeDecision:
    allowed: bool
    reason: str
    volume: float
    estimated_risk: float


def approve_trade(equity: float, state: RiskState, stop_distance: float,
                  settings: Settings) -> RiskDecision:
    if equity <= 0 or stop_distance <= 0:
        return RiskDecision(False, "invalid_equity_or_stop", 0.0, stop_distance)
    if state.daily_pnl <= -equity * settings.max_daily_loss_pct:
        return RiskDecision(False, "daily_loss_limit", 0.0, stop_distance)
    if state.consecutive_losses >= settings.max_consecutive_losses:
        return RiskDecision(False, "consecutive_loss_limit", 0.0, stop_distance)
    if state.trades_today >= settings.max_trades_per_day:
        return RiskDecision(False, "daily_trade_limit", 0.0, stop_distance)
    return RiskDecision(True, "approved", equity * settings.risk_per_trade_pct, stop_distance)


def volume_from_risk(risk_amount: float, stop_distance: float, tick_size: float,
                     tick_value: float, volume_step: float, min_volume: float,
                     max_volume: float) -> VolumeDecision:
    if min(risk_amount, stop_distance, tick_size, tick_value, volume_step, min_volume) <= 0:
        return VolumeDecision(False, "invalid_symbol_metadata", 0.0, 0.0)
    risk_per_lot = (stop_distance / tick_size) * tick_value
    raw = risk_amount / risk_per_lot
    steps = (Decimal(str(raw)) / Decimal(str(volume_step))).to_integral_value(rounding=ROUND_DOWN)
    volume = float(steps * Decimal(str(volume_step)))
    if volume < min_volume:
        minimum_risk = risk_per_lot * min_volume
        return VolumeDecision(False, "minimum_lot_exceeds_risk", 0.0, minimum_risk)
    volume = min(volume, max_volume)
    estimated = risk_per_lot * volume
    return VolumeDecision(True, "approved", round(volume, 8), estimated)

