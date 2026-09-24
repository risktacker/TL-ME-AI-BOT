"""Bounded development selection followed by one fresh comparison per market.

Never starts trading. The fresh partition may be evaluated only once for this
selection. M1 prices use the baseline's explicit spread/slippage approximation.
"""
from dataclasses import replace
from pathlib import Path
import argparse, hashlib, json
import numpy as np
import pandas as pd
from config import Settings
from experiments.lifecycle import Policy, prepare, simulate, metrics

CONFIGS = {
    'baseline': dict(stop_atr=1.5,displacement_body_atr=.4,minimum_edge_score=0.,hold=12),
    'momentum_1atr_8bars': dict(stop_atr=1.,displacement_body_atr=.6,minimum_edge_score=0.,hold=8),
    'momentum_075atr_4bars': dict(stop_atr=.75,displacement_body_atr=.6,minimum_edge_score=0.,hold=4),
    'ranked_1atr_4bars': dict(stop_atr=1.,displacement_body_atr=.4,minimum_edge_score=4.,hold=4),
}


def settings(spec,spread,name):
    p=CONFIGS[name].copy();p.pop('hold')
    return replace(Settings(),symbol=spec['name'],point_price=spec['point'],
                   spread_price=spread,slippage_price=spread*.25,**p)


def minlot_metrics(t,spec):
    m=metrics(t)
    if t.empty:return m
    cash=t.r*t.risk_distance/spec['trade_tick_size']*spec['trade_tick_value']*spec['volume_min']
    curve=cash.cumsum();m['minlot_net_cash_estimate']=float(cash.sum())
    m['minlot_dd_cash_estimate']=float((curve.cummax().clip(lower=0)-curve).max())
    return m


def replay_m1(data,m1,s,hold,stress=False):
    rows=[];available=pd.Timestamp.min.tz_localize('UTC')
    m1=m1.set_index('time').sort_index()
    for row in data[data.signal.ne(0)].itertuples():
        entry_time=row.time+pd.Timedelta(minutes=15)
        if entry_time<available or entry_time not in m1.index:continue
        end=entry_time+pd.Timedelta(minutes=15*hold)
        window=m1[(m1.index>=entry_time)&(m1.index<end)]
        if window.empty or window.index[-1]+pd.Timedelta(minutes=1)<end:continue
        entry=float(window.iloc[0].open);risk=row.atr*s.stop_atr;side=int(row.signal)
        spread=float(window.iloc[0].spread)*s.point_price
        cost=spread*(1.5 if stress else 1)+2*s.slippage_price*(2 if stress else 1)
        reason='time'
        for bar in window.itertuples():
            op=side*(bar.open-entry)/risk
            adverse=side*((bar.low if side==1 else bar.high)-entry)/risk
            favorable=side*((bar.high if side==1 else bar.low)-entry)/risk
            if op<=-1:outcome=op;reason='stop_gap';break
            if op>=1.75:outcome=1.75;reason='target';break
            if adverse<=-1:outcome=-1.;reason='stop';break
            if favorable>=1.75:outcome=1.75;reason='target';break
            outcome=side*(bar.close-entry)/risk
        exit_time=bar.Index+pd.Timedelta(minutes=1)
        rows.append(dict(entry_time=entry_time,exit_time=exit_time,r=float(outcome-cost/risk),
                         holding_minutes=(exit_time-entry_time).total_seconds()/60,
                         risk_distance=risk,cost_price=cost,exit_reason=reason,side=side))
        # Match baseline's no same-exit-bar re-entry rule at M15 resolution.
        available=bar.Index.floor('15min')+pd.Timedelta(minutes=30)
    return pd.DataFrame(rows)


def main(root,out):
    out.mkdir(parents=True,exist_ok=True)
    if (out/'frozen_selection.json').exists():raise SystemExit('Selection already exists; do not retune against this fresh set.')
    inventory={};selection={};development={}
    # Complete selection for ALL markets before reading any fresh price file.
    for path in sorted(root.glob('*_development_M15.csv')):
        sym=path.name.removesuffix('_development_M15.csv')
        spec=json.loads((root/f'{sym}_metadata.json').read_text())['symbol_specification']
        frame=pd.read_csv(path);spread=float(frame.spread.median())*spec['point']
        inventory[sym]={'spec':spec,'spread':spread,'development_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        results={}
        for name,p in CONFIGS.items():
            s=settings(spec,spread,name);d=prepare(frame,s)
            t=simulate(d,s,Policy(name,hold=p['hold']))
            results[name]=minlot_metrics(t,spec)
        base=results['baseline']
        eligible=[k for k,m in results.items() if k!='baseline' and m['trades']>=50
            and m['expectancy_r']>max(0,base['expectancy_r']) and (m['profit_factor'] or 0)>=1.2
            and m['max_drawdown_r']<=base['max_drawdown_r']
            and m.get('minlot_dd_cash_estimate',0)<=base.get('minlot_dd_cash_estimate',0)]
        # Diagnostic candidate is frozen even if development rejects all options.
        choice=max(eligible or [k for k in CONFIGS if k!='baseline'],key=lambda k:results[k]['expectancy_r'])
        selection[sym]={'candidate':choice,'development_pass':choice in eligible}
        development[sym]=results
        print(sym,choice,'development_pass=',choice in eligible,flush=True)
    frozen={'configs':CONFIGS,'selection':selection,'development':development,'inventory':inventory}
    (out/'frozen_selection.json').write_text(json.dumps(frozen,indent=2,allow_nan=False))
    result={}
    for sym,choice in selection.items():
        spec=inventory[sym]['spec'];spread=inventory[sym]['spread']
        dev=pd.read_csv(root/f'{sym}_development_M15.csv').tail(1600)
        fresh_path=root/f'{sym}_fresh_M15.csv';fresh=pd.read_csv(fresh_path)
        m1=pd.read_csv(root/f'{sym}_fresh_M1.csv');m1.time=pd.to_datetime(m1.time,utc=True)
        joined=pd.concat([dev,fresh],ignore_index=True)
        cutoff=pd.to_datetime(fresh.time.iloc[0],utc=True)
        comparisons={}
        for name in ('baseline',choice['candidate']):
            s=settings(spec,spread,name);d=prepare(joined,s)
            d=d[d.time>=cutoff].copy()
            for stress in (False,True):
                t=replay_m1(d,m1,s,CONFIGS[name]['hold'],stress)
                m=minlot_metrics(t,spec)
                if not t.empty:
                    unit=spec['trade_tick_value']*spec['volume_min']/spec['trade_tick_size']
                    exposure=(t.risk_distance+t.cost_price)*unit
                    m['max_modeled_stop_cash']=float(exposure.max())
                    m['median_modeled_stop_cash']=float(exposure.median())
                    m['stop_fits_10_count']=int((exposure<10).sum())
                    m['stop_fits_15_count']=int((exposure<15).sum())
                    t.to_csv(out/f'{sym}_{name}_{"stress" if stress else "normal"}.csv',index=False)
                comparisons[name+('_stress' if stress else '')]=m
        b=comparisons['baseline'];c=comparisons[choice['candidate']]
        passed=(choice['development_pass'] and c['trades']>=50 and c['expectancy_r']>max(0,b['expectancy_r'])
                and (c['profit_factor'] or 0)>=1.2 and c['max_drawdown_r']<=b['max_drawdown_r']
                and comparisons[choice['candidate']+'_stress']['expectancy_r']>0)
        result[sym]={'selection':choice,'fresh_sha256':hashlib.sha256(fresh_path.read_bytes()).hexdigest(),
                     'comparisons':comparisons,'performance_gate':bool(passed),'demo_approved':False}
        print(sym,'fresh baseline/candidate',b['trades'],round(b['expectancy_r'],4),c['trades'],round(c['expectancy_r'],4),flush=True)
    (out/'fresh_results.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print('No orders sent. Fresh set now consumed; do not retune against it.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.data_dir,a.output)
