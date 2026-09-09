"""Fail-closed MT5 demo service for one closed-candle decision at a time."""
from __future__ import annotations
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time

from config import Settings
from core.journal import RuntimeStore
from core.mt5_client import MT5Gateway
from core.trade_executor import TradeExecutor, TradePlan
from risk.risk_engine import RiskState, approve_trade, volume_from_risk
from strategy import generate_signal


def configure_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    handler = RotatingFileHandler("logs/bot.log", maxBytes=2_000_000, backupCount=5)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[handler, logging.StreamHandler()])


class DemoService:
    def __init__(self, settings: Settings, gateway: MT5Gateway | None = None,
                 store: RuntimeStore | None = None) -> None:
        self.settings = settings
        self.gateway = gateway or MT5Gateway(path=None)
        self.store = store or RuntimeStore()
        self.executor = TradeExecutor(settings, self.gateway)
        self.symbol = settings.symbol

    def _publish_position(self) -> None:
        positions = self.gateway.positions(self.symbol, self.settings.magic_number)
        if not positions:
            self.store.write("position", {"open": False})
            return
        position = positions[0]
        self.store.write("position", {"open": True, "ticket": int(position.ticket),
                         "side": "buy" if int(position.type) == 0 else "sell",
                         "entry": float(position.price_open), "stop": float(position.sl),
                         "target": float(position.tp), "volume": float(position.volume),
                         "running_pnl": float(position.profit)})

    def cycle(self) -> str:
        control = self.store.read("control", {"mode": "locked", "paused": True})
        if control.get("close_all_requested"):
            closed = self.executor.close_all(self.symbol)
            self.store.write("control", {"mode": "emergency_stop", "paused": True,
                                         "close_all_requested": False})
            self.store.event("emergency_close", positions=len(closed))
            return "emergency_close"
        account = self.gateway.account_snapshot()
        terminal = self.gateway.terminal_snapshot()
        risk_raw = self.gateway.risk_state_today(self.settings.magic_number)
        self.store.write("account", {**account, **risk_raw, "environment": "demo",
                                     "drawdown_pct": max(0.0, (account["balance"]-account["equity"])/max(account["balance"], 1)*100)})
        self.store.write("trades", {"items": self.gateway.recent_closed_deals(self.settings.magic_number)})
        self._publish_position()
        if control.get("paused", True): return "paused"
        if not terminal["connected"] or not terminal["trade_allowed"] or terminal["tradeapi_disabled"]:
            raise RuntimeError("MT5 terminal is not ready for automated trading")
        if self.gateway.positions(self.symbol, self.settings.magic_number): return "position_open"
        rates = self.gateway.latest_rates(self.symbol, self.settings.timeframe, 800)
        closed = rates.iloc[:-1].copy()
        bar = closed.iloc[-1]["time"].isoformat()
        service = self.store.read("service", {})
        if service.get("last_processed_bar") == bar: return "already_processed"
        signal = generate_signal(closed, self.settings)
        self.store.write("market", {**signal, "signal": signal["side"], "signal_reason": "closed M15 decision",
                                    "spread": float(rates.iloc[-1].get("spread", 0)), "session": signal.get("session", "")})
        self.store.write("service", {**service, "last_processed_bar": bar,
                                     "heartbeat": datetime.now(timezone.utc).isoformat()})
        if signal["signal"] == 0: return "no_signal"
        atr = float(signal["atr"])
        tick = self.gateway.symbol_info(self.symbol)
        decision = approve_trade(float(account["equity"]), RiskState(**risk_raw), self.settings.stop_atr * atr, self.settings)
        if not decision.allowed:
            self.store.event("risk_rejected", reason=decision.reason, bar=bar)
            return decision.reason
        volume = volume_from_risk(decision.risk_amount, decision.stop_distance,
                                  float(tick.trade_tick_size), float(tick.trade_tick_value),
                                  float(tick.volume_step), float(tick.volume_min), float(tick.volume_max))
        if not volume.allowed:
            self.store.event("size_rejected", reason=volume.reason, estimated_risk=volume.estimated_risk)
            return volume.reason
        quote = self.gateway.current_tick(self.symbol)
        price = float(quote.ask if signal["signal"] == 1 else quote.bid)
        stop = price - decision.stop_distance if signal["signal"] == 1 else price + decision.stop_distance
        target = price + self.settings.target_r * decision.stop_distance if signal["signal"] == 1 else price - self.settings.target_r * decision.stop_distance
        result = self.executor.submit(TradePlan(self.symbol, signal["signal"], volume.volume, stop, target,
                                                magic=self.settings.magic_number, comment="GOLIDE M15 demo"))
        self.store.event("order_submitted", order=int(result.order), deal=int(result.deal), bar=bar,
                         side=signal["side"], volume=volume.volume)
        return "submitted"

    def run_forever(self) -> None:
        configure_logging()
        self.gateway.connect()
        try:
            self.symbol = self.gateway.resolve_symbol(self.settings.symbol)
            while True:
                try:
                    status = self.cycle()
                    logging.info("cycle=%s symbol=%s", status, self.symbol)
                except Exception as exc:
                    logging.exception("cycle failed")
                    self.store.write("service", {"heartbeat": datetime.now(timezone.utc).isoformat(),
                                                 "status": "error", "error": str(exc)})
                time.sleep(max(5, self.settings.poll_seconds))
        finally:
            self.gateway.shutdown()


def run_service() -> None:
    settings = Settings.from_env()
    if settings.execution_mode != "demo":
        raise SystemExit("Service startup refused: EXECUTION_MODE must be demo")
    DemoService(settings).run_forever()
