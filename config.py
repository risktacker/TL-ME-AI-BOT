"""Configuration with safe research defaults."""
from __future__ import annotations
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    symbol: str = "XAUUSD"
    risk_per_trade_pct: float = 0.0025
    max_daily_loss_pct: float = 0.01
    fast_ema: int = 50
    slow_ema: int = 200
    atr_period: int = 14
    breakout_bars: int = 20
    stop_atr: float = 1.5
    target_r: float = 2.0
    starting_equity: float = 10000.0
    live_trading: bool = False
    enable_order_submission: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            symbol=os.getenv("BOT_SYMBOL", cls.symbol),
            risk_per_trade_pct=float(os.getenv("RISK_PER_TRADE_PCT", cls.risk_per_trade_pct)),
            max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", cls.max_daily_loss_pct)),
            live_trading=os.getenv("LIVE_TRADING", "false").lower() == "true",
            enable_order_submission=os.getenv("ENABLE_ORDER_SUBMISSION", "false").lower() == "true",
        )
