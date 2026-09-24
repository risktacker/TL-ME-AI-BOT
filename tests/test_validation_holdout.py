import numpy as np
import pandas as pd
from backtest import BacktestResult
from config import Settings
from validation import validate_strategy


def test_tiny_positive_holdout_cannot_pass_and_micro_dd_is_not_fractional(monkeypatch):
    frame=pd.DataFrame({'time':pd.date_range('2025-01-01',periods=5100,freq='15min',tz='UTC')})
    def fake(data,settings):
        n=20 if len(data)<2000 else 120
        return BacktestResult(pd.DataFrame(dict(r=np.ones(n),holding_bars=np.ones(n),
            entry_time=pd.date_range(data.time.iloc[0],periods=n,freq='15min',tz='UTC'))),1000)
    monkeypatch.setattr('validation.run_backtest',fake)
    r=validate_strategy(frame,Settings(),simulations=10)
    assert not r.passed
    assert 'fewer_than_50_holdout_trades' in r.reasons
    assert r.monte_carlo_95_drawdown_pct is None
