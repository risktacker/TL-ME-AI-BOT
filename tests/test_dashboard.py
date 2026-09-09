from dashboard.state import overview


def test_dashboard_never_reports_live_unlocked():
    state = overview()
    assert state["bot"]["live_unlocked"] is False
    assert state["risk"]["risk_per_trade_pct"] == 0.25


def test_dashboard_has_expected_sections():
    assert {"bot", "account", "market", "position", "validation", "recent_trades", "risk"} <= overview().keys()

