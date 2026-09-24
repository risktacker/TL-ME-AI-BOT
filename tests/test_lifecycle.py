import pandas as pd
import pytest
from config import Settings
from experiments.lifecycle import Policy, metrics, portfolio, simulate


def fixture(side=1):
    f=pd.DataFrame(dict(time=pd.date_range('2026-01-01',periods=5,freq='15min',tz='UTC'),
        open=[100.]*5,high=[100.2]*5,low=[99.8]*5,close=[100.]*5,
        atr=[1]*5,atr_median=[1]*5,signal=[side,0,0,0,0],edge=[2]*5,
        rearmed_signal=[side,0,0,0,0],raw_signal=[side,0,0,0,0],
        donchian_high=[99]*5,donchian_low=[101]*5,session=['test']*5,
        trend_fast=[101]*5,trend_slow=[100]*5,h4_fast=[101]*5,h4_slow=[100]*5,
        bull_bos=[False]*5,bear_bos=[False]*5))
    return f


S=Settings(stop_atr=1,spread_price=0,slippage_price=0)


@pytest.mark.parametrize('side',[1,-1])
def test_stop_before_target_when_intrabar_order_unknown(side):
    f=fixture(side);f.loc[1,['high','low']]=[103,97]
    t=simulate(f,S)
    assert t.iloc[0].r==-1


@pytest.mark.parametrize('side',[1,-1])
def test_stop_gaps_are_not_capped_at_one_r(side):
    f=fixture(side);f.loc[2,['open','close']]=100-2*side
    f.loc[2,['high','low']]=[103,97]
    assert simulate(f,S).iloc[0].r==-2


def test_break_even_is_only_active_on_next_bar():
    f=fixture();f.loc[1,['high','low','close']]=[101,99.5,100.8]
    t=simulate(f,S,Policy('be',be=.75))
    assert t.iloc[0].holding_bars==2
    assert t.iloc[0].r==0


def test_cost_covered_break_even_and_short_symmetry():
    f=fixture(-1);f.loc[1,['high','low','close']]=[100.5,99,99.2]
    s=Settings(stop_atr=1,spread_price=.1,slippage_price=0)
    f.loc[2,['open','high','low','close']]=[99.7,100,99.5,99.8]
    assert simulate(f,s,Policy('be',be=.75)).iloc[0].r==pytest.approx(0)


def test_failed_breakout_uses_next_open_not_known_close():
    f=fixture();f['donchian_high']=100;f.loc[1,'close']=99.9
    f.loc[2,'open']=99.7
    assert simulate(f,S,Policy('fail',invalidation='breakout')).iloc[0].r==pytest.approx(-.3)


def test_portfolio_slots_do_not_multiply_risk_or_stack_symbol():
    a=simulate(fixture(),S);a['symbol']='A'
    b=a.assign(symbol='B');c=a.assign(symbol='C')
    all=pd.concat([a,a,b,c],ignore_index=True)
    all['r']=1
    p,count=portfolio(all,2)
    assert count==2 and len(p)==2
    assert p.r.sum()==1
    assert p.symbol.nunique()==2


def test_bootstrap_is_deterministic():
    t=simulate(fixture(),S)
    assert metrics(t)==metrics(t)
