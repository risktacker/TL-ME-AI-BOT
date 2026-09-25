"""Read-only Exness demo data/contract export. Never sends orders.

Run from repo root: python -m scripts.collect_demo_inputs
The previously inspected sample ends 2026-09-10 13:00 UTC. New data stays
separate from development data; this collector makes no profitability claim.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math
import zipfile
import pandas as pd
from config import Settings
from core.mt5_client import MT5Gateway, mt5
from strategy.engine import _atr


def feasibility(loss, margin, spread_loss, stopout, stopout_mode, equity):
    values = (loss, margin, spread_loss, stopout, equity)
    if any(v is None or not math.isfinite(float(v)) for v in values):
        return False
    if loss < 0 or margin < 0 or spread_loss < 0 or equity <= 0:
        return False
    floor = margin * stopout / 100 if stopout_mode == 0 else stopout
    # Isolated minimum-lot position, no existing account exposure assumed.
    # Entry spread reduces free equity; stop-out must not precede the SL.
    return loss < equity and margin + spread_loss < equity and equity - loss > floor


def main():
    if mt5 is None:
        raise SystemExit('Run this on Windows with the MetaTrader5 package installed.')
    now = datetime.now(timezone.utc)
    boundary = datetime(2026, 9, 10, 13, tzinfo=timezone.utc)
    root = Path('reports/demo_inputs') / now.strftime('%Y%m%dT%H%M%SZ')
    root.mkdir(parents=True, exist_ok=False)
    gateway = MT5Gateway()
    gateway.connect()
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Open and log into an Exness DEMO account first.')
        if 'exness' not in str(account.server).lower():
            raise RuntimeError('This export requires an Exness demo server.')
        report = dict(exported_at=now.isoformat(),fresh_boundary=boundary.isoformat(),
            currency=account.currency,leverage=account.leverage,
            stopout_mode=account.margin_so_mode,stopout_level=account.margin_so_so,
            markets={},orders_sent=0,
            limitations=['Current quotes/specifications, not historical margin or currency conversion.',
                        'No commission schedule or gap guarantee; feasibility is not profitability.',
                        'Fresh data is only untouched if it was not inspected in other work.'])
        for requested in Settings().symbols:
            result={}
            try:
                symbol=gateway.resolve_symbol(requested)
                frame=gateway.rates_range(symbol,'M15',now-timedelta(days=730),now)
                frame=frame[frame.time+pd.Timedelta(minutes=15)<=pd.Timestamp(now)].reset_index(drop=True)
                if frame.empty: raise RuntimeError('No completed M15 history')
                # Persist development and prospective test partitions separately.
                frame[frame.time<boundary].to_csv(root/f'{symbol}_development_M15.csv',index=False)
                frame[frame.time>=boundary].to_csv(root/f'{symbol}_fresh_M15.csv',index=False)
                m1=gateway.rates_range(symbol,'M1',boundary,now)
                m1=m1[m1.time+pd.Timedelta(minutes=1)<=pd.Timestamp(now)]
                m1.to_csv(root/f'{symbol}_fresh_M1.csv',index=False)
                info=gateway.symbol_info(symbol);quote=gateway.current_tick(symbol)
                if quote.ask <= 0 or quote.bid <= 0 or quote.ask < quote.bid:
                    raise RuntimeError('Invalid bid/ask quote')
                quote_age=max(0,now.timestamp()-quote.time)
                spec=gateway.symbol_snapshot(symbol)
                spec.update(trade_stops_level=info.trade_stops_level,
                            trade_freeze_level=info.trade_freeze_level,
                            trade_calc_mode=info.trade_calc_mode)
                (root/f'{symbol}_metadata.json').write_text(json.dumps({'symbol_specification':spec},indent=2))
                atr=float(_atr(frame,14).iloc[-1]);checks=[]
                for stop_atr in (.75,1.,1.5):
                    for side,kind in ((1,mt5.ORDER_TYPE_BUY),(-1,mt5.ORDER_TYPE_SELL)):
                        entry=float(quote.ask if side==1 else quote.bid)
                        stop=entry-side*stop_atr*atr
                        # Tick-grid rounding away from entry; do not shrink risk artificially.
                        unit=float(info.trade_tick_size)
                        stop=(math.floor(stop/unit) if side==1 else math.ceil(stop/unit))*unit
                        close_quote=float(quote.bid if side==1 else quote.ask)
                        distance=side*(close_quote-stop)
                        geometry=distance>0 and distance>=info.trade_stops_level*info.point
                        pnl=mt5.order_calc_profit(kind,symbol,info.volume_min,entry,stop)
                        loss=-float(pnl) if pnl is not None else None
                        margin=mt5.order_calc_margin(kind,symbol,info.volume_min,entry)
                        spread_pnl=mt5.order_calc_profit(kind,symbol,info.volume_min,entry,close_quote)
                        spread_loss=-float(spread_pnl) if spread_pnl is not None else None
                        checks.append(dict(side=side,stop_atr=stop_atr,entry=entry,stop=stop,
                            minimum_volume=info.volume_min,stop_loss_cash=loss,margin_cash=margin,
                            spread_cash=spread_loss,stop_geometry_valid=geometry,
                            equity_checks={str(e): bool(account.currency=='USD' and quote_age<=60 and geometry and
                                feasibility(loss,margin,spread_loss,account.margin_so_so,account.margin_so_mode,e))
                                for e in (10,12,15)}))
                result=dict(symbol=symbol,m15_rows=len(frame),fresh_m15_rows=int((frame.time>=boundary).sum()),
                    fresh_m1_rows=len(m1),first=str(frame.time.iloc[0]),last=str(frame.time.iloc[-1]),
                    quote_age_seconds=quote_age,minimum_lot_checks=checks)
                print(f'{requested}: {result["fresh_m15_rows"]} fresh M15 bars; contract checks saved',flush=True)
            except Exception as exc:
                result['error']=str(exc)
                print(f'{requested}: {exc}',flush=True)
            report['markets'][requested]=result
        (root/'broker_report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    finally:
        gateway.shutdown()
    archive=Path('GOLIDE-demo-inputs.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in root.iterdir(): z.write(path,path.name)
    print(f'Upload this file: {archive.resolve()}')
    print('No orders sent. No trading settings changed.')


if __name__=='__main__': main()
