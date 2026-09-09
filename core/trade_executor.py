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
        mode = self.settings.execution_mode
        if mode not in {"demo", "live"}:
            raise PermissionError("Execution is disabled")
        if not (self.settings.enable_order_submission and self.settings.validation_passed):
            raise PermissionError("Submission requires ENABLE_ORDER_SUBMISSION and VALIDATION_PASSED")
        account = self.gateway.account_snapshot()
        if mode == "demo" and account["trade_mode"] != 0:
            raise PermissionError("Demo mode refuses a non-demo MT5 account")
        if mode == "live" and (not self.settings.live_trading or account["trade_mode"] == 0):
            raise PermissionError("Live mode requires LIVE_TRADING and a non-demo MT5 account")
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed")

    def submit(self, plan: TradePlan) -> Any:
        self._assert_unlocked()
        if plan.side not in (-1, 1) or plan.volume <= 0:
            raise ValueError("Invalid trade plan")
        info = self.gateway.symbol_info(plan.symbol)
        if not info.visible and not mt5.symbol_select(plan.symbol, True):
            raise RuntimeError(f"Could not select {plan.symbol}")
        tick = self.gateway.current_tick(plan.symbol)
        price = float(tick.ask if plan.side == 1 else tick.bid)
        if plan.side == 1 and not (plan.stop_loss < price < plan.take_profit):
            raise ValueError("Invalid buy stop/target geometry")
        if plan.side == -1 and not (plan.take_profit < price < plan.stop_loss):
            raise ValueError("Invalid sell stop/target geometry")
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": plan.symbol, "volume": plan.volume,
            "type": mt5.ORDER_TYPE_BUY if plan.side == 1 else mt5.ORDER_TYPE_SELL,
            "price": round(price, int(info.digits)), "sl": round(plan.stop_loss, int(info.digits)),
            "tp": round(plan.take_profit, int(info.digits)),
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
        positions = self.gateway.positions(symbol=symbol, magic=self.settings.magic_number)
        results = []
        for position in positions:
            tick = self.gateway.current_tick(position.symbol)
            side = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if side == mt5.ORDER_TYPE_SELL else tick.ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL, "position": position.ticket,
                "symbol": position.symbol, "volume": position.volume, "type": side,
                "price": price, "deviation": 30, "magic": 260909,
                "comment": "TL-ME emergency close", "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": self.gateway.symbol_info(position.symbol).filling_mode,
            }
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                raise RuntimeError(f"Emergency close failed for {position.ticket}: {result}")
            results.append(result)
        return results

    def close_position(self, position: Any, comment: str = "GOLIDE timed exit") -> Any:
        self._assert_unlocked()
        tick = self.gateway.current_tick(position.symbol)
        side = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "position": position.ticket,
            "symbol": position.symbol, "volume": position.volume, "type": side,
            "price": tick.bid if side == mt5.ORDER_TYPE_SELL else tick.ask,
            "deviation": 30, "magic": self.settings.magic_number, "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self.gateway.symbol_info(position.symbol).filling_mode,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"Position close failed for {position.ticket}: {result}")
        return result


LiveExecutor = TradeExecutor
