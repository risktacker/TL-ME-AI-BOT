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


class FakeMT5:
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    SYMBOL_FILLING_RETURN = 4
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2


class SymbolInfo:
    def __init__(self, filling_mode): self.filling_mode = filling_mode


def test_filling_bitmask_is_translated_to_order_enum(monkeypatch):
    import core.trade_executor as module
    monkeypatch.setattr(module, "mt5", FakeMT5)
    assert TradeExecutor._filling_type(SymbolInfo(FakeMT5.SYMBOL_FILLING_IOC)) == FakeMT5.ORDER_FILLING_IOC
    assert TradeExecutor._filling_type(SymbolInfo(FakeMT5.SYMBOL_FILLING_FOK)) == FakeMT5.ORDER_FILLING_FOK


def test_combined_filling_flags_prefer_ioc(monkeypatch):
    import core.trade_executor as module
    monkeypatch.setattr(module, "mt5", FakeMT5)
    flags = FakeMT5.SYMBOL_FILLING_FOK | FakeMT5.SYMBOL_FILLING_IOC
    assert TradeExecutor._filling_type(SymbolInfo(flags)) == FakeMT5.ORDER_FILLING_IOC


def test_unknown_filling_policy_fails_closed(monkeypatch):
    import core.trade_executor as module
    monkeypatch.setattr(module, "mt5", FakeMT5)
    with pytest.raises(RuntimeError, match="No supported MT5 filling policy"):
        TradeExecutor._filling_type(SymbolInfo(8))
