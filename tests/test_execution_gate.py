import pytest
from config import Settings
from core.trade_executor import TradeExecutor


class Gateway:
    def __init__(self, trade_mode): self.trade_mode = trade_mode
    def account_snapshot(self): return {"trade_mode": self.trade_mode}


def test_demo_refuses_real_account():
    executor = TradeExecutor(Settings(execution_mode="demo", enable_order_submission=True,
                                      validation_passed=True), Gateway(2))
    with pytest.raises(PermissionError, match="non-demo"):
        executor._assert_unlocked()


def test_live_needs_independent_live_flag():
    executor = TradeExecutor(Settings(execution_mode="live", enable_order_submission=True,
                                      validation_passed=True, live_trading=False), Gateway(2))
    with pytest.raises(PermissionError, match="LIVE_TRADING"):
        executor._assert_unlocked()
