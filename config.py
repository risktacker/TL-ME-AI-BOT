"""Configuration for the XAUUSD intraday research and execution engine."""
from __future__ import annotations

from dataclasses import dataclass
import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    strategy_name: str = "donchian_mtf_momentum"

    # Account protection. Fractions: 0.0025 == 0.25%.
    risk_per_trade_pct: float = 0.0025
    max_daily_loss_pct: float = 0.01
    max_consecutive_losses: int = 3
    max_trades_per_day: int = 1

    # Regime and volatility measurement.
    trend_fast_ema: int = 20
    trend_slow_ema: int = 50
    h4_fast_ema: int = 12
    h4_slow_ema: int = 30
    breakout_bars: int = 20
    atr_period: int = 14
    atr_median_period: int = 50
    min_atr_ratio: float = 0.80
    max_atr_ratio: float = 2.50

    # Entry package: opening-range breakout + trend + price-action score.
    opening_range_minutes: int = 60
    entry_window_minutes: int = 180
    breakout_buffer_atr: float = 0.05
    displacement_body_atr: float = 0.40
    confirmation_score: int = 2
    use_london: bool = True
    use_new_york: bool = True

    # Fast intraday exits.
    stop_atr: float = 1.50
    target_r: float = 1.75
    max_holding_bars: int = 12
    break_even_at_r: float = 0.0

    # Backtest execution assumptions, expressed in price units.
    spread_price: float = 0.20
    point_price: float = 0.001
    slippage_price: float = 0.05
    max_spread_atr: float = 0.12
    starting_equity: float = 1000.0

    live_trading: bool = False
    enable_order_submission: bool = False
    validation_passed: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            symbol=os.getenv("BOT_SYMBOL", cls.symbol),
            strategy_name=os.getenv("BOT_STRATEGY", cls.strategy_name),
            risk_per_trade_pct=float(os.getenv("RISK_PER_TRADE_PCT", cls.risk_per_trade_pct)),
            max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", cls.max_daily_loss_pct)),
            max_consecutive_losses=int(os.getenv("MAX_CONSECUTIVE_LOSSES", cls.max_consecutive_losses)),
            max_trades_per_day=int(os.getenv("MAX_TRADES_PER_DAY", cls.max_trades_per_day)),
            spread_price=float(os.getenv("BACKTEST_SPREAD_PRICE", cls.spread_price)),
            slippage_price=float(os.getenv("BACKTEST_SLIPPAGE_PRICE", cls.slippage_price)),
            live_trading=_bool("LIVE_TRADING"),
            enable_order_submission=_bool("ENABLE_ORDER_SUBMISSION"),
            validation_passed=_bool("VALIDATION_PASSED"),
        )
