from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from config import Settings
from data_pipeline import acquire_exness_history


class FakeGateway:
    connected = False
    closed = False

    def connect(self): self.connected = True
    def shutdown(self): self.closed = True
    def resolve_symbol(self, requested): return "XAUUSDm"
    def account_snapshot(self): return {"server": "Exness-Demo", "trade_mode": 0}
    def symbol_snapshot(self, symbol): return {"name": symbol, "volume_min": 0.01, "point": 0.001}
    def rates_range(self, symbol, timeframe, start, end):
        periods = 100 if timeframe == "M1" else 20
        time = pd.date_range(start, periods=periods, freq="1min" if timeframe == "M1" else "15min")
        return pd.DataFrame({"time": time, "open": 2500, "high": 2501,
                             "low": 2499, "close": 2500, "spread": 20})


def test_acquisition_exports_broker_data(tmp_path: Path):
    gateway = FakeGateway()
    result = acquire_exness_history(
        gateway, Settings(), tmp_path, days=90,
        now=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )
    assert gateway.connected and gateway.closed
    assert result["symbol"] == "XAUUSDm"
    assert Path(result["files"]["M15"]).exists()
    assert Path(result["metadata"]).exists()


def test_validation_uses_broker_native_price_units(tmp_path: Path):
    gateway = FakeGateway()
    from data_pipeline import acquire_and_validate
    result = acquire_and_validate(
        gateway, Settings(), tmp_path / "data", tmp_path / "reports", days=90,
        now=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )
    assumptions = result["validation"]["execution_assumptions"]
    assert assumptions["point_price"] == 0.001
    assert assumptions["median_spread_price"] == 0.02
    assert assumptions["one_way_slippage_price"] == 0.005
