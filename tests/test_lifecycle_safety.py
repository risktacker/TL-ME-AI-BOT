from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from config import Settings
from risk.risk_engine import volume_for_profile
from bot.service import DemoService
from core.journal import RuntimeStore


@pytest.mark.parametrize('value',[0,-1,float('nan'),float('inf')])
def test_micro_rejects_bad_tick_metadata(value):
    assert not volume_for_profile(10,1,.01,value,.01,.01,100,Settings()).allowed


def test_risk_ceiling_rejects_unaffordable_gold_minimum():
    d=volume_for_profile(10,13,.001,.1,.01,.01,200,Settings(max_stop_risk_pct=.05))
    assert not d.allowed and d.estimated_risk==13


def test_risk_ceiling_scales_down_without_loss_streak_shutdown():
    d=volume_for_profile(100,1,.01,1,.01,.01,100,Settings(max_stop_risk_pct=.02))
    assert d.allowed and d.volume==.02 and d.estimated_risk==2


def test_service_uses_broker_point_for_fx(monkeypatch,tmp_path):
    frame=pd.DataFrame({'time':pd.date_range('2026-01-01',periods=3,freq='15min',tz='UTC')})
    gateway=SimpleNamespace(account_snapshot=lambda:dict(balance=100,equity=100),
        terminal_snapshot=lambda:dict(connected=True,trade_allowed=True,tradeapi_disabled=False),
        risk_state_today=lambda magic:dict(daily_pnl=0,consecutive_losses=0,trades_today=0),
        recent_closed_deals=lambda magic:[],positions=lambda **kw:[],
        symbol_info=lambda symbol:SimpleNamespace(point=.00001),latest_rates=lambda *args:frame)
    store=RuntimeStore(tmp_path);store.write('control',{'paused':False})
    service=DemoService(Settings(),gateway,store);service.symbols=['EURUSDm']
    captured=[]
    def signal(frame,settings):
        captured.append(settings.point_price)
        return {'signal':0}
    monkeypatch.setattr('bot.service.generate_signal',signal)
    assert service.cycle()=='no_signal'
    assert captured==[.00001]


def test_sparse_scores_match_reference():
    from strategy.engine import signal_series,_edge_score
    n=900;rng=np.random.default_rng(71);close=2500+np.cumsum(rng.normal(size=n))
    f=pd.DataFrame(dict(time=pd.date_range('2026-01-01',periods=n,freq='15min',tz='UTC'),
        open=close-.6,close=close,high=close+1,low=close-1))
    sig=signal_series(f,Settings());data=sig.attrs['data']
    expected=pd.Series([_edge_score(data.iloc[i],int(sig.iloc[i])) for i in range(n)])
    pd.testing.assert_series_equal(sig.attrs['edge_scores'],expected)


@pytest.mark.parametrize('value',[None,float('nan'),float('inf'),1,0])
def test_broker_stop_exposure_fails_closed(monkeypatch,value):
    from core.mt5_client import MT5Gateway
    monkeypatch.setattr('core.mt5_client.mt5',SimpleNamespace(ORDER_TYPE_BUY=0,ORDER_TYPE_SELL=1,order_calc_profit=lambda *a:value))
    with pytest.raises(RuntimeError):MT5Gateway().stop_exposure('XAUUSDm',1,.01,2000,1990)


def test_broker_stop_exposure_is_account_currency(monkeypatch):
    from core.mt5_client import MT5Gateway
    monkeypatch.setattr('core.mt5_client.mt5',SimpleNamespace(ORDER_TYPE_BUY=0,ORDER_TYPE_SELL=1,order_calc_profit=lambda *a:-13.18))
    assert MT5Gateway().stop_exposure('XAUUSDm',1,.01,2000,1986.82)==13.18
