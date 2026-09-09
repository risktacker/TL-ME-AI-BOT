from dashboard.state import overview
from dashboard.app import api_control
from fastapi import HTTPException
import pytest


def test_dashboard_never_reports_live_unlocked():
    state = overview()
    assert state["bot"]["live_unlocked"] is False
    assert state["risk"]["risk_per_trade_pct"] == 0.25


def test_dashboard_has_expected_sections():
    assert {"bot", "account", "market", "position", "validation", "recent_trades", "risk"} <= overview().keys()


def test_control_requires_configured_token(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "correct-secret")
    with pytest.raises(HTTPException) as error:
        api_control("pause", "Bearer wrong-secret")
    assert error.value.status_code == 401
