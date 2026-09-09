"""MT5 execution boundary with explicit safety and broker checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from config import Settings
from core.mt5_client import MT5Gateway, mt5


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    side: int
    volume: float
    stop_loss: float
    take_profit: float
    deviation: int = 20
    magic: int = 260909
    comment: str = "TL-ME session breakout"


@dataclass
class TradeExecutor:
    settings: Settings
    gateway: MT5Gateway

    def _assert_unlocked(self) -> None:
        if not (self.settings.live_trading and self.settings.enable_order_submission
                and self.settings.validation_passed):
            raise PermissionError("Live trading requires LIVE_TRADING, ENABLE_ORDER_SUBMISSION, and VALIDATION_PASSED")
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed")

    def submit(self, plan: TradePlan) -> Any:
        self._assert_unlocked()
        if plan.side not in (-1, 1) or plan.volume <= 0:
            raise ValueError("Invalid trade plan")
        info = self.gateway.symbol_info(plan.symbol)
        if not info.visible and not mt5.symbol_select(plan.symbol, True):
            raise RuntimeError(f"Could not select {plan.symbol}")
        tick = mt5.symbol_info_tick(plan.symbol)
        if tick is None:
            raise RuntimeError(f"No current tick for {plan.symbol}")
        price = float(tick.ask if plan.side == 1 else tick.bid)
        if plan.side == 1 and not (plan.stop_loss < price < plan.take_profit):
            raise ValueError("Invalid buy stop/target geometry")
        if plan.side == -1 and not (plan.take_profit < price < plan.stop_loss):
            raise ValueError("Invalid sell stop/target geometry")
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": plan.symbol, "volume": plan.volume,
            "type": mt5.ORDER_TYPE_BUY if plan.side == 1 else mt5.ORDER_TYPE_SELL,
            "price": price, "sl": plan.stop_loss, "tp": plan.take_profit,
            "deviation": plan.deviation, "magic": plan.magic, "comment": plan.comment,
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": info.filling_mode,
        }
        checked = mt5.order_check(request)
        if checked is None or checked.retcode != 0:
            raise RuntimeError(f"MT5 order check failed: {checked}")
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"MT5 order failed: {result}; last_error={mt5.last_error()}")
        return result

    def close_all(self, symbol: str | None = None) -> list[Any]:
        self._assert_unlocked()
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            raise RuntimeError(f"Could not read positions: {mt5.last_error()}")
        results = []
        for position in positions:
            tick = mt5.symbol_info_tick(position.symbol)
            side = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if side == mt5.ORDER_TYPE_SELL else tick.ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL, "position": position.ticket,
                "symbol": position.symbol, "volume": position.volume, "type": side,
                "price": price, "deviation": 30, "magic": 260909,
                "comment": "TL-ME emergency close", "type_time": mt5.ORDER_TIME_GTC,
            }
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                raise RuntimeError(f"Emergency close failed for {position.ticket}: {result}")
            results.append(result)
        return results


LiveExecutor = TradeExecutor

