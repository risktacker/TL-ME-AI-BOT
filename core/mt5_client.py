"""Small MT5 gateway. No browser automation and no DOM selectors."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


@dataclass
class MT5Gateway:
    login: int | None = None
    password: str | None = None
    server: str | None = None
    path: str | None = None

    def connect(self) -> None:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed")
        kwargs = {k: v for k, v in {"path": self.path, "login": self.login,
                                     "password": self.password, "server": self.server}.items()
                  if v is not None}
        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    def shutdown(self) -> None:
        if mt5 is not None:
            mt5.shutdown()

    def rates(self, symbol: str, timeframe: int, count: int = 500) -> pd.DataFrame:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed")
        rows = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rows is None:
            raise RuntimeError(f"Could not load rates for {symbol}: {mt5.last_error()}")
        frame = pd.DataFrame(rows)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        return frame[["time", "open", "high", "low", "close", "tick_volume"]]

    def account_equity(self) -> float:
        info = mt5.account_info() if mt5 else None
        if info is None:
            raise RuntimeError("MT5 account information unavailable")
        return float(info.equity)

    def symbol_info(self, symbol: str) -> Any:
        info = mt5.symbol_info(symbol) if mt5 else None
        if info is None:
            raise RuntimeError(f"MT5 symbol unavailable: {symbol}")
        return info
