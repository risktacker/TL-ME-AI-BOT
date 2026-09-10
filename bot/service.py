"""Fail-closed MT5 demo service for one closed-candle decision at a time."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time

from config import Settings
from core.journal import RuntimeStore
from core.mt5_client import MT5Gateway
from core.trade_executor import TradeExecutor, TradePlan
from risk.risk_engine import RiskState, approve_trade, volume_for_profile
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
        self.symbols: list[str] = []
        self.research_only_symbols: list[str] = []
        self.symbol_errors: dict[str, str] = {}

    def _publish_position(self) -> None:
        positions = self.gateway.positions(magic=self.settings.magic_number)
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
            closed = self.executor.close_all()
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
        positions = self.gateway.positions(magic=self.settings.magic_number)
        if positions:
            maximum_seconds = self.settings.max_holding_bars * 15 * 60
            now_ts = datetime.now(timezone.utc).timestamp()
            expired = [position for position in positions if now_ts - float(position.time) >= maximum_seconds]
            for position in expired:
                self.executor.close_position(position)
                self.store.event("time_exit", ticket=int(position.ticket), symbol=str(position.symbol))
            return "time_exit" if expired else "position_open"

        candidates = []
        latest_bars = {}
        for symbol in self.symbols:
            try:
                symbol_settings = replace(self.settings, symbol=symbol)
                rates = self.gateway.latest_rates(symbol, self.settings.timeframe, 800)
                closed = rates.iloc[:-1].copy()
                bar = closed.iloc[-1]["time"].isoformat()
                latest_bars[symbol] = bar
                signal = generate_signal(closed, symbol_settings)
                signal["spread"] = float(rates.iloc[-1].get("spread", 0))
                if signal["signal"]:
                    candidates.append((float(signal["edge_score"]), symbol, signal))
            except Exception as exc:
                self.symbol_errors[symbol] = str(exc)
                logging.warning("scanner skipped symbol=%s error=%s", symbol, exc)
        service = self.store.read("service", {})
        if service.get("last_processed_bars") == latest_bars: return "already_processed"
        self.store.write("service", {**service, "last_processed_bars": latest_bars,
                                     "heartbeat": datetime.now(timezone.utc).isoformat()})
        if not candidates:
            self.store.write("market", {"symbol": "MULTI", "signal": "flat",
                                        "signal_reason": "scanner found no qualified edge",
                                        "edge_score": 0, "scanned": len(latest_bars),
                                        "unavailable": len(self.symbol_errors), "session": "scanner"})
            return "no_signal"
        _, symbol, signal = max(candidates, key=lambda candidate: candidate[0])
        bar = latest_bars[symbol]
        self.store.write("market", {**signal, "signal": signal["side"],
                                    "signal_reason": "highest-ranked closed M15 edge",
                                    "scanned": len(self.symbols), "candidates": len(candidates)})
        atr = float(signal["atr"])
        tick = self.gateway.symbol_info(symbol)
        decision = approve_trade(float(account["equity"]), RiskState(**risk_raw), self.settings.stop_atr * atr, self.settings)
        if not decision.allowed:
            self.store.event("risk_rejected", reason=decision.reason, bar=bar)
            return decision.reason
        volume = volume_for_profile(float(account["equity"]), decision.stop_distance,
                                    float(tick.trade_tick_size), float(tick.trade_tick_value),
                                    float(tick.volume_step), float(tick.volume_min), float(tick.volume_max),
                                    self.settings)
        if not volume.allowed:
            self.store.event("size_rejected", reason=volume.reason, estimated_risk=volume.estimated_risk)
            return volume.reason
        quote = self.gateway.current_tick(symbol)
        price = float(quote.ask if signal["signal"] == 1 else quote.bid)
        stop = price - decision.stop_distance if signal["signal"] == 1 else price + decision.stop_distance
        target = price + self.settings.target_r * decision.stop_distance if signal["signal"] == 1 else price - self.settings.target_r * decision.stop_distance
        result = self.executor.submit(TradePlan(symbol, signal["signal"], volume.volume, stop, target,
                                                magic=self.settings.magic_number, comment="GOLIDE ranked M15"))
        self.store.event("order_submitted", order=int(result.order), deal=int(result.deal), bar=bar,
                         side=signal["side"], volume=volume.volume, edge_score=signal["edge_score"],
                         estimated_stop_loss=volume.estimated_risk)
        return "submitted"

    def run_forever(self) -> None:
        configure_logging()
        self.gateway.connect()
        try:
            for requested in self.settings.symbols:
                if requested.upper() not in self.settings.qualified_symbols:
                    self.research_only_symbols.append(requested)
                    logging.info("research-only symbol=%s reason=not independently validated", requested)
                    continue
                try:
                    self.symbols.append(self.gateway.resolve_symbol(requested))
                except Exception as exc:
                    self.symbol_errors[requested] = str(exc)
                    logging.warning("unavailable requested_symbol=%s error=%s", requested, exc)
            if not self.symbols:
                raise RuntimeError("None of the independently validated markets could be resolved in MT5")
            while True:
                try:
                    status = self.cycle()
                    logging.info("cycle=%s symbols=%s", status, ",".join(self.symbols))
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
