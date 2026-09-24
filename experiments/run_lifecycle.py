"""Run: python -m experiments.run_lifecycle --data-dir PATH --output PATH.

Historical 70/30 is a *reused comparison*, not an untouched final holdout.
Select on first 70% only; freeze candidate before reporting the remaining 30%.
"""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from config import Settings
from experiments.lifecycle import POLICIES, metrics, portfolio, prepare, simulate


def run(data_dir, output):
    output.mkdir(parents=True,exist_ok=True)
    all_trades, rows, inventory, micro = {}, [], [], []
    for path in sorted(data_dir.glob("*_M15.csv")):
        symbol = path.name.removesuffix("_M15.csv")
        spec = json.loads(path.with_name(symbol+"_metadata.json").read_text())["symbol_specification"]
        frame = pd.read_csv(path)
        spread = float(frame.spread.median())*spec["point"]
        settings = replace(Settings(),symbol=symbol,point_price=spec["point"],spread_price=spread,slippage_price=.25*spread)
        data = prepare(frame,settings)
        split = data.time.iloc[int(len(data)*.7)]
        inventory.append(dict(symbol=symbol,rows=len(frame),first=str(data.time.iloc[0]),last=str(data.time.iloc[-1]),
                              sha256=hashlib.sha256(path.read_bytes()).hexdigest(),comparison_split=str(split),spec=spec))
        for policy in POLICIES:
            trades = simulate(data,settings,policy)
            if trades.empty:
                rows.append(dict(symbol=symbol,policy=policy.name,development=metrics(trades),comparison=metrics(trades),full=metrics(trades),folds=[]))
                continue
            dev=trades[trades.exit_time<split]; check=trades[trades.entry_time>=split]
            stress_spread=simulate(data,settings,policy,spread_mult=1.5)
            stress_slip=simulate(data,settings,policy,slip_mult=2)
            stress=simulate(data,settings,policy,spread_mult=1.5,slip_mult=2)
            folds=[]
            for ix in np.array_split(np.arange(int(len(data)*.7)),5):
                part=trades[(trades.entry_time>=data.time.iloc[ix[0]]) & (trades.exit_time<data.time.iloc[ix[-1]])]
                folds.append(metrics(part,200))
            row=dict(symbol=symbol,policy=policy.name,development=metrics(dev),comparison=metrics(check),full=metrics(trades),folds=folds,
                     spread_stress=metrics(stress_spread[stress_spread.entry_time>=split]),
                     slippage_stress=metrics(stress_slip[stress_slip.entry_time>=split]),
                     combined_stress=metrics(stress[stress.entry_time>=split]),
                     by_session={str(k):metrics(g,200) for k,g in check.groupby("session")},
                     by_regime={str(k):metrics(g,200) for k,g in check.groupby("regime")})
            rows.append(row)
            trades["partition"]=np.where(trades.exit_time<split,"development",np.where(trades.entry_time>=split,"comparison","boundary"))
            all_trades[(symbol,policy.name)]=trades
            if policy.name=="baseline":
                loss=trades.risk_distance/spec["trade_tick_size"]*spec["trade_tick_value"]*spec["volume_min"]
                for equity in (10,25,50,100,1000):
                    micro.append(dict(symbol=symbol,equity=equity,min_lot=spec["volume_min"],
                                      median_min_lot_stop_cash=float(loss.median()),p95_min_lot_stop_cash=float(loss.quantile(.95)),
                                      median_stop_fraction=float(loss.median()/equity),
                                      fraction_fit_2pct_budget=float((loss<=equity*.02).mean()),
                                      fraction_fit_5pct_budget=float((loss<=equity*.05).mean())))
        print(symbol,"done",flush=True)
    # Each independently surviving development policy must beat the baseline
    # expectancy without raising drawdown, and win >=4/5 development folds.
    selected={}; comparisons=[]
    for symbol in sorted({r["symbol"] for r in rows}):
        base=next(r for r in rows if r["symbol"]==symbol and r["policy"]=="baseline")
        survivors=[]
        for r in (x for x in rows if x["symbol"]==symbol and x["policy"]!="baseline"):
            m=r["development"]; b=base["development"]
            if (m["trades"]>=50 and m["expectancy_r"]>max(0,b["expectancy_r"])
                and (m["profit_factor"] or 0)>=1.2 and m["max_drawdown_r"]<=b["max_drawdown_r"]
                and sum(f["net_r"]>0 for f in r["folds"])>=4): survivors.append(r)
        chosen=max(survivors,key=lambda x:x["development"]["expectancy_r"],default=base)
        selected[symbol]=chosen["policy"]
        c=chosen["comparison"]
        comparisons.append(dict(symbol=symbol,selected=chosen["policy"],independent_survivors=[x["policy"] for x in survivors],
            historical_gate=bool(c["trades"]>=50 and c["expectancy_r"]>0 and (c["profit_factor"] or 0)>=1.2
                 and c.get("profitable_bootstrap_fraction",0)>=.8 and c.get("monte_carlo_95_drawdown_r",999)<=10
                 and chosen.get("combined_stress",{}).get("expectancy_r",0)>0),
            production_eligible=False,reason="no untouched final data or tick/broker forward validation"))
    portfolios=[]
    for kind in ("baseline","development_selected"):
        ts=[v for (sym,pol),v in all_trades.items() if pol==("baseline" if kind=="baseline" else selected[sym])]
        if not ts: continue
        joined=pd.concat(ts,ignore_index=True)
        for count in (1,2,3):
            for part in ("development","comparison"):
                p,maximum=portfolio(joined[joined.partition==part],count)
                portfolios.append(dict(policy=kind,slots=count,partition=part,max_simultaneous_positions=maximum,
                    max_initial_risk_budget_r=1,metrics=metrics(p),
                    limitation="Normalized constant-risk slots, not broker-volume cash equity simulation; drawdown is realized, not tick mark-to-market."))
    report=dict(baseline_commit="4371ae461dbc1d110de8b55d0fb673cec3c6f559",data_status="previously used research data; not untouched OOS",
                policies=[asdict(p) for p in POLICIES],inventory=inventory,experiments=rows,selection=comparisons,
                portfolios=portfolios,micro_account=micro,production_promoted=False)
    (output/"lifecycle_results.json").write_text(json.dumps(report,indent=2,allow_nan=False))
    pd.DataFrame([dict(symbol=r["symbol"],policy=r["policy"],partition=part,**r[part]) for r in rows for part in ("development","comparison","full")]).to_csv(output/"lifecycle_metrics.csv",index=False)
    if all_trades: pd.concat([v.assign(policy=k[1]) for k,v in all_trades.items()],ignore_index=True).to_csv(output/"lifecycle_trades.csv",index=False)
    print(json.dumps(comparisons,indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--data-dir",type=Path,required=True);p.add_argument("--output",type=Path,default=Path("reports/lifecycle"))
    args=p.parse_args();run(args.data_dir,args.output)
