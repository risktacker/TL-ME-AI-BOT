"""Execution boundary, locked until the strategy is validated."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from config import Settings
from core.mt5_client import MT5Gateway


@dataclass
class TradeExecutor:
    settings: Settings
    gateway: MT5Gateway

    def submit(self, request: dict[str, Any]) -> Any:
        if not self.settings.live_trading or not self.settings.enable_order_submission:
            raise PermissionError("Order submission is locked by configuration")
        raise NotImplementedError("MT5 order submission will be added after backtest validation")

    def close_all(self) -> None:
        raise NotImplementedError("Emergency-close implementation is required before live mode")


LiveExecutor = TradeExecutor
