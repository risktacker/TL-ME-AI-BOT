from config import Settings
from risk.risk_engine import RiskState, approve_trade, volume_for_profile, volume_from_risk
from bot.service import DemoService
from core.journal import RuntimeStore


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


def test_micro_volume_compounds_in_broker_steps():
    decision = volume_for_profile(35, 1, 0.01, 1, 0.01, 0.01, 100,
                                  Settings(risk_profile="micro_aggressive"))
    assert decision.volume == 0.03
    assert decision.estimated_risk == 3.0


def test_micro_compound_starts_at_point_zero_one_and_scales_with_equity():
    settings = Settings(risk_profile="micro_compound", micro_equity_per_step=20)
    decision = volume_for_profile(20, 1, 0.01, 1, 0.01, 0.01, 100, settings)
    assert decision.allowed
    assert decision.volume == 0.01
    assert decision.estimated_risk == 1.0
    grown = volume_for_profile(40, 1, 0.01, 1, 0.01, 0.01, 100, settings)
    assert grown.volume == 0.02


def test_micro_compound_captures_the_users_selected_account_balance(tmp_path):
    settings = Settings(risk_profile="micro_compound", micro_equity_per_step=0)
    service = DemoService(settings, gateway=object(), store=RuntimeStore(tmp_path))
    resolved = service._sizing_settings({"login": 123, "balance": 20})
    assert resolved.micro_equity_per_step == 20
    # The same account keeps its chosen baseline rather than resetting after growth.
    resolved = service._sizing_settings({"login": 123, "balance": 27})
    assert resolved.micro_equity_per_step == 20
