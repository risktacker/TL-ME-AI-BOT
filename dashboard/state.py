"""Read dashboard state and apply safe pause/emergency controls."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import pandas as pd
from config import Settings

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def _validation() -> dict[str, Any]:
    reports = sorted((ROOT / "reports").glob("*_validation.json"), key=lambda item: item.stat().st_mtime)
    if reports:
        payload = _read_json(reports[-1], {})
        return payload.get("validation", payload)
    return _read_json(Path(__file__).with_name("baseline.json"), {"passed": False, "reasons": ["validation_report_not_connected"], "full_period": {}, "holdout": {}})


def _trades() -> list[dict[str, Any]]:
    runtime = _read_json(RUNTIME / "trades.json", {})
    if isinstance(runtime.get("items"), list):
        return runtime["items"][-10:]
    path = ROOT / "data" / "trades.csv"
    if not path.exists():
        return []
    return pd.read_csv(path).tail(10).fillna("").to_dict(orient="records")


def overview() -> dict[str, Any]:
    settings = Settings.from_env()
    control = _read_json(RUNTIME / "control.json", {"mode": "locked", "paused": True})
    market = _read_json(RUNTIME / "market.json", {"symbol": "XAUUSDm", "session": "offline", "signal": "flat", "signal_reason": "MT5 bridge not connected", "spread": None})
    account = _read_json(RUNTIME / "account.json", {"environment": "demo", "balance": None, "equity": None, "daily_pnl": 0.0, "drawdown_pct": 0.0, "trades_today": 0})
    position = _read_json(RUNTIME / "position.json", {"open": False})
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "bot": {"name": "TL-ME Multi-Market", "strategy": "Ranked MTF Momentum", "mode": control.get("mode", "locked"), "paused": bool(control.get("paused", True)), "live_unlocked": False, "connection": "connected" if market.get("session") != "offline" else "offline"},
        "account": account, "market": market, "position": position,
        "validation": _validation(), "recent_trades": _trades(),
        "risk": {"profile": settings.risk_profile, "micro_volume": settings.micro_volume,
                 "selection": ("all_independent_ranked_candidates"
                               if settings.submit_all_candidates
                               else "highest_ranked_qualified_setup"),
                 "fast_manager": settings.fast_manager_enabled,
                 "daily_shutdown": settings.risk_profile == "proportional"},
    }


def set_control(action: str) -> dict[str, Any]:
    if action not in {"pause", "resume_demo", "emergency_stop"}:
        raise ValueError("Unsupported control action")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    current = _read_json(RUNTIME / "control.json", {"mode": "locked", "paused": True})
    if action == "pause": current.update({"paused": True})
    elif action == "resume_demo": current.update({"mode": "demo", "paused": False})
    else: current.update({"mode": "emergency_stop", "paused": True, "close_all_requested": True})
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    (RUNTIME / "control.json").write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current
