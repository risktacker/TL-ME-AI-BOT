from config import Settings
from risk.risk_engine import approve_trade, volume_from_risk


def test_daily_loss_gate():
    s = Settings()
    assert approve_trade(10000, -100, 10, s).allowed is False


def test_volume_is_bounded():
    volume = volume_from_risk(25, 10, 0.01, 1.0, 0.01, 0.01, 10.0)
    assert 0.01 <= volume <= 10.0
