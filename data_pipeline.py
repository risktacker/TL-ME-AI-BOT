"""Acquire broker-native Exness history and immediately validate the strategy."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
import pandas as pd

from config import Settings
from core.market_data import validate_ohlc
from core.mt5_client import MT5Gateway
from validation import validate_strategy
from dataclasses import replace


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and (pd.isna(value) or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def acquire_exness_history(gateway: MT5Gateway, settings: Settings, output_dir: Path,
                           days: int = 730, now: datetime | None = None) -> dict[str, Any]:
    """Export M15 candles and broker specifications from the logged-in terminal."""
    if days < 90:
        raise ValueError("At least 90 days are required; two years is recommended")
    output_dir.mkdir(parents=True, exist_ok=True)
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    gateway.connect()
    try:
        symbol = gateway.resolve_symbol(settings.symbol)
        files: dict[str, str] = {}
        counts: dict[str, int] = {}
        for timeframe in ("M15",):
            frame = validate_ohlc(gateway.rates_range(symbol, timeframe, start, end))
            target = output_dir / f"{symbol}_{timeframe}.csv"
            frame.to_csv(target, index=False)
            files[timeframe] = str(target)
            counts[timeframe] = len(frame)
        metadata = {
            "source": "connected_mt5_terminal", "symbol": symbol,
            "exported_at_utc": end.isoformat(), "start_utc": start.isoformat(),
            "days_requested": days, "rows": counts,
            "account": gateway.account_snapshot(), "symbol_specification": gateway.symbol_snapshot(symbol),
        }
        metadata_path = output_dir / f"{symbol}_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return {"symbol": symbol, "files": files, "metadata": str(metadata_path), "rows": counts}
    finally:
        gateway.shutdown()


def acquire_and_validate(gateway: MT5Gateway, settings: Settings, output_dir: Path,
                         report_dir: Path, days: int = 730,
                         now: datetime | None = None) -> dict[str, Any]:
    acquisition = acquire_exness_history(gateway, settings, output_dir, days, now)
    frame = pd.read_csv(acquisition["files"]["M15"], parse_dates=["time"])
    metadata = json.loads(Path(acquisition["metadata"]).read_text(encoding="utf-8"))
    specification = metadata["symbol_specification"]
    point_price = float(specification["point"])
    recorded_spread = (float(frame["spread"].dropna().median()) * point_price
                       if "spread" in frame and not frame["spread"].dropna().empty
                       else settings.spread_price)
    # Use broker-native units for every market. One-way slippage is modelled as
    # 25% of its recorded median spread and doubled by the stress test.
    validation_settings = replace(
        settings, symbol=acquisition["symbol"], point_price=point_price,
        spread_price=recorded_spread, slippage_price=recorded_spread * 0.25,
    )
    report = _json_safe(asdict(validate_strategy(frame, validation_settings)))
    report["execution_assumptions"] = {
        "point_price": point_price,
        "median_spread_price": recorded_spread,
        "one_way_slippage_price": recorded_spread * 0.25,
        "source": "broker_metadata_and_recorded_m15_spread",
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f'{acquisition["symbol"]}_validation.json'
    payload = {"acquisition": acquisition, "validation": report}
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["report"] = str(report_path)
    return payload


def acquire_universe_and_validate(gateway: MT5Gateway, settings: Settings, output_dir: Path,
                                  report_dir: Path, days: int = 730,
                                  now: datetime | None = None) -> dict[str, Any]:
    """Export and validate every configured market independently."""
    results: dict[str, Any] = {}
    for requested in settings.symbols:
        symbol_settings = replace(settings, symbol=requested, symbols=(requested,))
        try:
            results[requested] = acquire_and_validate(
                gateway, symbol_settings, output_dir, report_dir, days, now,
            )
        except Exception as exc:
            results[requested] = {"error": str(exc)}
    passed = [name for name, payload in results.items()
              if payload.get("validation", {}).get("passed")]
    report_dir.mkdir(parents=True, exist_ok=True)
    summary_path = report_dir / "universe_validation.json"
    summary = {"requested": list(settings.symbols), "passed": passed, "markets": results}
    summary_path.write_text(json.dumps(_json_safe(summary), indent=2), encoding="utf-8")
    summary["report"] = str(summary_path)
    return summary
