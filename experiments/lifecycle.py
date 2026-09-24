"""Predeclared closed-bar exit experiments. No MT5 orders; no final-set fitting.

M15 OHLC cannot validate tick trailing. Stops ratchet only after a bar closes,
become effective next bar, and gaps fill adversely. Close decisions fill at
next open. Costs follow the existing price-cost model for comparability.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from config import Settings
from strategy import signal_series


@dataclass(frozen=True)
class Policy:
    name: str = "baseline"
    target: float = 1.75
    hold: int = 12
    be: float = 0.0
    trail: str = ""
    trail_atr: float = 1.5
    activation: float = 1.0
    invalidation: str = ""
    rearm: bool = False


POLICIES = (
    Policy(), Policy("target_1R", target=1.0),
    Policy("time_4", hold=4), Policy("time_8", hold=8),
    Policy("be_075", be=.75), Policy("be_100", be=1.0),
    Policy("atr_trail", trail="atr"),
    Policy("chandelier", trail="chandelier", trail_atr=2.0),
    Policy("structure_trail", trail="structure"),
    Policy("retracement", trail="retracement"),
    Policy("failed_breakout", invalidation="breakout"),
    Policy("regime_failure", invalidation="regime"),
    Policy("opposite_bos", invalidation="bos"),
    Policy("momentum_decay", invalidation="momentum"),
    Policy("time_decay", invalidation="time"),
    Policy("vol_contraction", invalidation="volatility"),
    Policy("opposite_signal", invalidation="opposite"),
    Policy("rearm_reset", rearm=True),
)


def prepare(frame, settings):
    signals = signal_series(frame, settings)
    data = signals.attrs["data"].copy()
    data["signal"] = signals.to_numpy()
    data["edge"] = signals.attrs["edge_scores"].to_numpy()
    a = data.atr / data.atr_median
    spread = data.spread * settings.point_price if "spread" in data else settings.spread_price
    common = (data.time.dt.hour.between(6, 16) & a.between(.85, 2)
              & (spread / data.atr <= settings.max_spread_atr)
              & ((data.close - data.open).abs() >= settings.displacement_body_atr * data.atr))
    long = common & (data.trend_fast > data.trend_slow) & (data.h4_fast > data.h4_slow) & (data.close > data.donchian_high)
    short = common & (data.trend_fast < data.trend_slow) & (data.h4_fast < data.h4_slow) & (data.close < data.donchian_low)
    data["raw_signal"] = np.select([long, short], [1, -1], default=0)
    # A fresh qualified breakout only after a completed bar returns inside its
    # rolling channel. No instant re-entry into an unchanged breakout.
    armed, rearmed = True, []
    for row in data.itertuples():
        if row.donchian_low <= row.close <= row.donchian_high:
            armed = True
        fire = int(row.raw_signal) if armed else 0
        rearmed.append(fire)
        if fire:
            armed = False
    data["rearmed_signal"] = rearmed
    return data


def simulate(data, settings, policy=Policy(), spread_mult=1., slip_mult=1.):
    """One position per symbol; fixed initial R denominator throughout."""
    arrays = {c: data[c].to_numpy() for c in data.columns}
    a = arrays
    signals = a["rearmed_signal" if policy.rearm else "signal"]
    trades, available = [], 0
    n = len(data)
    for i in np.flatnonzero(signals):
        if i < available or i >= n - 1 or not a["atr"][i] > 0:
            continue
        side = int(signals[i]); entry_i = i + 1
        entry = float(a["open"][entry_i]); risk = float(a["atr"][i]) * settings.stop_atr
        spread = (float(a["spread"][entry_i]) * settings.point_price if "spread" in a else settings.spread_price) * spread_mult
        cost = spread + 2 * settings.slippage_price * slip_mult
        stop_r, peak, reason = -1., 0., "time"
        end = min(n - 1, i + policy.hold)
        level = a["donchian_high" if side == 1 else "donchian_low"][i]
        for j in range(entry_i, end + 1):
            op_r = side * (a["open"][j] - entry) / risk
            adverse = side * (a["low" if side == 1 else "high"][j] - entry) / risk
            favorable = side * (a["high" if side == 1 else "low"][j] - entry) / risk
            close_r = side * (a["close"][j] - entry) / risk
            if op_r <= stop_r:
                outcome, reason = op_r, "stop_gap"; break
            if op_r >= policy.target:
                outcome, reason = policy.target, "target"; break
            if adverse <= stop_r:
                outcome, reason = stop_r, "stop"; break
            if favorable >= policy.target:
                outcome, reason = policy.target, "target"; break
            # No use of current high to assert a same-bar trailing fill.
            peak = max(peak, favorable)
            invalid = False
            if policy.invalidation == "breakout":
                invalid = side * (a["close"][j] - level) <= 0
            elif policy.invalidation == "regime":
                invalid = side * (a["trend_fast"][j] - a["trend_slow"][j]) <= 0 or side * (a["h4_fast"][j] - a["h4_slow"][j]) <= 0
            elif policy.invalidation == "bos":
                invalid = bool(a["bear_bos" if side == 1 else "bull_bos"][j])
            elif policy.invalidation == "opposite":
                invalid = a["raw_signal"][j] == -side
            elif policy.invalidation == "momentum":
                invalid = j >= entry_i + 2 and side * (a["close"][j] - a["close"][j-2]) < -.5 * a["atr"][j]
            elif policy.invalidation == "time":
                invalid = j - i >= 4 and peak < .5
            elif policy.invalidation == "volatility":
                invalid = a["atr"][j] < .75 * a["atr"][i]
            if invalid and j < n - 1:
                j += 1
                outcome = side * (a["open"][j] - entry) / risk
                reason = policy.invalidation; break
            if j == end:
                outcome = close_r; break
            candidate = stop_r
            if policy.be and close_r >= policy.be:
                candidate = max(candidate, cost / risk)
            if close_r >= policy.activation and policy.trail:
                if policy.trail == "atr":
                    candidate = max(candidate, close_r - policy.trail_atr * a["atr"][j] / risk)
                elif policy.trail == "chandelier":
                    candidate = max(candidate, peak - policy.trail_atr * a["atr"][j] / risk)
                elif policy.trail == "retracement":
                    candidate = max(candidate, peak * .5)
                elif policy.trail == "structure":
                    structure = min(a["low"][max(entry_i,j-2):j+1]) if side == 1 else max(a["high"][max(entry_i,j-2):j+1])
                    candidate = max(candidate, side * (structure - entry) / risk)
            # A stop already crossed at bar close becomes a next-open exit.
            if candidate >= close_r and candidate > stop_r and j < n - 1:
                j += 1; outcome = side * (a["open"][j] - entry) / risk
                reason = "protection_market"; break
            stop_r = candidate
        exit_time = a["time"][j] if reason in {"stop_gap", "protection_market", policy.invalidation} else a["time"][j] + pd.Timedelta(minutes=15)
        trades.append(dict(symbol=settings.symbol, entry_time=a["time"][entry_i], exit_time=exit_time,
                           r=float(outcome-cost/risk), side=side, holding_bars=j-i,
                           holding_minutes=(exit_time-a["time"][entry_i]).total_seconds()/60,
                           exit_reason=reason, session=str(a["session"][i]),
                           regime="high_vol" if a["atr"][i]/a["atr_median"][i] >= 1.25 else "normal_vol",
                           edge=float(a["edge"][i]), risk_distance=risk,
                           entry_price=entry, cost_price=cost))
        available = j + 1
    return pd.DataFrame(trades)


def metrics(trades, simulations=1000):
    if trades.empty:
        return {"trades": 0, "net_r": 0., "expectancy_r": 0., "profit_factor": 0., "max_drawdown_r": 0.}
    r = trades.r.to_numpy(float); wins = r[r>0]; losses = r[r<0]
    curve = np.cumsum(r); dd = np.maximum.accumulate(np.maximum(curve,0))-curve
    # Circular five-trade block bootstrap preserves some serial dependence.
    rng = np.random.default_rng(42)
    starts = rng.integers(0,len(r),size=(simulations,(len(r)+4)//5))
    ix = ((starts[:,:,None]+np.arange(5))%len(r)).reshape(simulations,-1)[:,:len(r)]
    samples = r[ix]; curves = samples.cumsum(axis=1)
    boot_dd = (np.maximum.accumulate(np.maximum(curves,0),axis=1)-curves).max(axis=1)
    daily = trades.groupby(pd.to_datetime(trades.exit_time,utc=True).dt.floor("D")).r.sum()
    days = pd.date_range(pd.to_datetime(trades.entry_time,utc=True).min().floor("D"), pd.to_datetime(trades.exit_time,utc=True).max().floor("D"),freq="B")
    daily = daily.reindex(days,fill_value=0)
    avg_win = float(wins.mean()) if len(wins) else 0.
    avg_loss = float(-losses.mean()) if len(losses) else 0.
    result = dict(trades=len(r),net_r=float(r.sum()),expectancy_r=float(r.mean()),
                  profit_factor=float(wins.sum()/-losses.sum()) if len(losses) else None,
                  win_rate=float((r>0).mean()),average_win_r=avg_win,average_loss_r=avg_loss,
                  payoff_ratio=avg_win/avg_loss if avg_loss else None,
                  max_drawdown_r=float(dd.max()),monte_carlo_95_drawdown_r=float(np.quantile(boot_dd,.95)),
                  profitable_bootstrap_fraction=float((samples.sum(axis=1)>0).mean()),
                  daily_r_sharpe=float(np.sqrt(252)*daily.mean()/daily.std()) if daily.std()>0 else None,
                  average_holding_minutes=float(trades.holding_minutes.mean()),
                  position_minutes=float(trades.holding_minutes.sum()))
    return result


def portfolio(trades, max_positions=1):
    """Event-ordered independent-symbol slots, total initial risk budget 1R.

Each slot gets 1/max_positions of the budget, rather than secretly multiplying
risk. No same-symbol stacking. Cash/volume feasibility is reported separately.
"""
    if trades.empty: return trades.copy(), 0
    ordered = trades.sort_values(["entry_time","edge","symbol"],ascending=[True,False,True])
    open_positions, accepted, maximum = [], [], 0
    for row in ordered.to_dict("records"):
        open_positions = [p for p in open_positions if p["exit_time"] > row["entry_time"]]
        if len(open_positions)>=max_positions or any(p["symbol"]==row["symbol"] for p in open_positions):
            continue
        open_positions.append(row); maximum=max(maximum,len(open_positions))
        accepted.append({**row,"r":row["r"]/max_positions})
    return pd.DataFrame(accepted).sort_values("exit_time").reset_index(drop=True),maximum
