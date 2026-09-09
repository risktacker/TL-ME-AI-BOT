from config import Settings
from risk.risk_engine import RiskState, approve_trade, volume_for_profile, volume_from_risk


def test_daily_loss_gate():
    decision = approve_trade(1000, RiskState(daily_pnl=-10), 5, Settings(risk_profile="proportional"))
    assert decision.allowed is False
    assert decision.reason == "daily_loss_limit"


def test_consecutive_loss_gate():
    assert not approve_trade(1000, RiskState(consecutive_losses=3), 5,
                             Settings(risk_profile="proportional")).allowed


def test_micro_profile_does_not_use_daily_or_streak_shutdowns():
    decision = approve_trade(10, RiskState(daily_pnl=-2, consecutive_losses=4, trades_today=5),
                             1, Settings(risk_profile="micro_aggressive"))
    assert decision.allowed
    assert decision.reason == "micro_structure_approved"


def test_small_account_skips_when_minimum_lot_risks_too_much():
    decision = volume_from_risk(0.25, 5, 0.01, 1.0, 0.01, 0.01, 100)
    assert not decision.allowed
    assert decision.reason == "minimum_lot_exceeds_risk"


def test_valid_volume_is_rounded_down():
    decision = volume_from_risk(25, 5, 0.01, 0.01, 0.01, 0.01, 100)
    assert decision.allowed
    assert decision.estimated_risk <= 25


def test_micro_profile_uses_minimum_volume_and_reports_structural_loss():
    decision = volume_for_profile(10, 1, 0.01, 1, 0.01, 0.01, 100,
                                  Settings(risk_profile="micro_aggressive"))
    assert decision.allowed
    assert decision.volume == 0.01
    assert decision.estimated_risk == 1.0
