"""MetaTrader 5 gateway for broker-native history and account metadata."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:  # Linux CI intentionally does not install the Windows package.
    mt5 = None


TIMEFRAMES = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "H1": "TIMEFRAME_H1",
}


@dataclass
class MT5Gateway:
    login: int | None = None
    password: str | None = None
    server: str | None = None
    path: str | None = None

    def connect(self) -> None:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 is available only on the Windows MT5 host")
        kwargs = {key: value for key, value in {
            "path": self.path, "login": self.login, "password": self.password, "server": self.server,
        }.items() if value is not None}
        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    def shutdown(self) -> None:
        if mt5 is not None:
            mt5.shutdown()

    def resolve_symbol(self, requested: str) -> str:
        """Resolve broker suffixes such as XAUUSDm without guessing silently."""
        direct = mt5.symbol_info(requested) if mt5 else None
        if direct is not None:
            return requested
        symbols = mt5.symbols_get(group=f"*{requested}*") if mt5 else None
        names = sorted({item.name for item in symbols or ()})
        exact_prefix = [name for name in names if name.upper().startswith(requested.upper())]
        if len(exact_prefix) == 1:
            return exact_prefix[0]
        raise RuntimeError(f"Cannot uniquely resolve {requested}; MT5 candidates={names}")

    def rates_range(self, symbol: str, timeframe: str, start: datetime,
                    end: datetime) -> pd.DataFrame:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed")
        constant_name = TIMEFRAMES.get(timeframe.upper())
        if constant_name is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"Could not select {symbol}: {mt5.last_error()}")
        rows = mt5.copy_rates_range(symbol, getattr(mt5, constant_name), start, end)
        if rows is None or len(rows) == 0:
            raise RuntimeError(f"No {timeframe} rates for {symbol}: {mt5.last_error()}")
        frame = pd.DataFrame(rows)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        columns = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
        return frame[[column for column in columns if column in frame.columns]]

    def account_equity(self) -> float:
        info = mt5.account_info() if mt5 else None
        if info is None:
            raise RuntimeError("MT5 account information unavailable")
        return float(info.equity)

    def account_snapshot(self) -> dict[str, Any]:
        info = mt5.account_info() if mt5 else None
        if info is None:
            raise RuntimeError("MT5 account information unavailable")
        return {
            "login": int(info.login), "server": str(info.server), "currency": str(info.currency),
            "balance": float(info.balance), "equity": float(info.equity),
            "leverage": int(info.leverage), "trade_mode": int(info.trade_mode),
        }

    def terminal_snapshot(self) -> dict[str, Any]:
        terminal = mt5.terminal_info() if mt5 else None
        if terminal is None:
            raise RuntimeError("MT5 terminal information unavailable")
        return {"connected": bool(terminal.connected), "trade_allowed": bool(terminal.trade_allowed),
                "tradeapi_disabled": bool(terminal.tradeapi_disabled)}

    def positions(self, symbol: str | None = None, magic: int | None = None) -> list[Any]:
        rows = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if rows is None:
            raise RuntimeError(f"Could not read positions: {mt5.last_error() if mt5 else 'unavailable'}")
        return [row for row in rows if magic is None or int(row.magic) == magic]

    def risk_state_today(self, magic: int) -> dict[str, float | int]:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(now - timedelta(days=30), now) if mt5 else None
        if deals is None:
            raise RuntimeError(f"Could not read deal history: {mt5.last_error() if mt5 else 'unavailable'}")
        all_exits = [deal for deal in deals if int(deal.magic) == magic and
                 int(deal.entry) in {mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY}]
        exits_today = [deal for deal in all_exits if datetime.fromtimestamp(int(deal.time), timezone.utc) >= start]
        pnl = [float(deal.profit + deal.commission + deal.swap + deal.fee) for deal in exits_today]
        losses = 0
        for deal in reversed(all_exits):
            value = float(deal.profit + deal.commission + deal.swap + deal.fee)
            if value >= 0: break
            losses += 1
        entries = [deal for deal in deals if int(deal.magic) == magic and int(deal.entry) == mt5.DEAL_ENTRY_IN
                   and datetime.fromtimestamp(int(deal.time), timezone.utc) >= start]
        return {"daily_pnl": sum(pnl), "consecutive_losses": losses, "trades_today": len(entries)}

    def current_tick(self, symbol: str) -> Any:
        tick = mt5.symbol_info_tick(symbol) if mt5 else None
        if tick is None:
            raise RuntimeError(f"No current tick for {symbol}")
        return tick

    def recent_closed_deals(self, magic: int, limit: int = 10) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(datetime(2020, 1, 1, tzinfo=timezone.utc), now) if mt5 else None
        if deals is None:
            raise RuntimeError(f"Could not read deal history: {mt5.last_error() if mt5 else 'unavailable'}")
        exits = [deal for deal in deals if int(deal.magic) == magic and
                 int(deal.entry) in {mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY}]
        return [{"time": datetime.fromtimestamp(int(deal.time), timezone.utc).isoformat(),
                 "symbol": str(deal.symbol), "profit": float(deal.profit + deal.commission + deal.swap + deal.fee),
                 "volume": float(deal.volume), "ticket": int(deal.ticket)} for deal in exits[-limit:]]

    def latest_rates(self, symbol: str, timeframe: str, count: int = 600) -> pd.DataFrame:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed")
        constant_name = TIMEFRAMES.get(timeframe.upper())
        if constant_name is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        rows = mt5.copy_rates_from_pos(symbol, getattr(mt5, constant_name), 0, count)
        if rows is None or len(rows) == 0:
            raise RuntimeError(f"No recent {timeframe} rates for {symbol}: {mt5.last_error()}")
        frame = pd.DataFrame(rows)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        return frame

    def symbol_info(self, symbol: str) -> Any:
        info = mt5.symbol_info(symbol) if mt5 else None
        if info is None:
            raise RuntimeError(f"MT5 symbol unavailable: {symbol}")
        return info

    def symbol_snapshot(self, symbol: str) -> dict[str, Any]:
        info = self.symbol_info(symbol)
        return {
            "name": info.name, "digits": int(info.digits), "point": float(info.point),
            "trade_tick_size": float(info.trade_tick_size),
            "trade_tick_value": float(info.trade_tick_value),
            "trade_contract_size": float(info.trade_contract_size),
            "volume_min": float(info.volume_min), "volume_max": float(info.volume_max),
            "volume_step": float(info.volume_step),
        }
