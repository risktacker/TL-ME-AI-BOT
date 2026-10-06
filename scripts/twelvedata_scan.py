"""Twelve Data market scan for the TL-ME scalper.

Pulls recent candles for gold and the majors, measures how cleanly each one is
trending, checks how correlated they are, and writes the result to MT5's Common
Files folder as TLME/scan.csv. The EA (InpUseScanFile=true) then only trades
pairs the scan approves, and only in the approved direction.

Usage:
    set TWELVEDATA_API_KEY=...            (or put it in .env)
    python scripts/twelvedata_scan.py           # one scan
    python scripts/twelvedata_scan.py --loop 15  # rescan every 15 minutes

Twelve Data's price feed is not Exness's. That is fine here: the scan decides
direction and trend quality, never entry prices.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # optional
    pass

API_URL = "https://api.twelvedata.com/time_series"
DEFAULT_SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "USD/CHF"]


# --------------------------------------------------------------------------- data
def fetch(symbol: str, interval: str, bars: int, api_key: str) -> pd.DataFrame:
    query = urllib.parse.urlencode(
        {"symbol": symbol, "interval": interval, "outputsize": bars, "apikey": api_key, "timezone": "UTC"}
    )
    with urllib.request.urlopen(f"{API_URL}?{query}", timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("status") != "ok":
        raise RuntimeError(f"{symbol}: {payload.get('message', payload)}")
    df = pd.DataFrame(payload["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    return df.sort_values("datetime").set_index("datetime")[["open", "high", "low", "close"]]


# ---------------------------------------------------------------------- measures
def efficiency_ratio(close: pd.Series, window: int) -> float:
    """1.0 = price moved in a straight line, 0.0 = pure chop."""
    tail = close.iloc[-(window + 1):]
    net = abs(tail.iloc[-1] - tail.iloc[0])
    path = tail.diff().abs().sum()
    return float(net / path) if path > 0 else 0.0


def trend_direction(close: pd.Series, ema_period: int, slope_bars: int) -> int:
    ema = close.ewm(span=ema_period, adjust=False).mean()
    if close.iloc[-1] > ema.iloc[-1] and ema.iloc[-1] > ema.iloc[-1 - slope_bars]:
        return 1
    if close.iloc[-1] < ema.iloc[-1] and ema.iloc[-1] < ema.iloc[-1 - slope_bars]:
        return -1
    return 0


def score_symbol(df: pd.DataFrame, er_window: int, ema_period: int, slope_bars: int, min_er: float) -> dict:
    close = df["close"]
    er = efficiency_ratio(close, er_window)
    direction = trend_direction(close, ema_period, slope_bars)
    if er < min_er:
        direction = 0
    return {"direction": direction, "score": round(er, 3)}


def pick_uncorrelated(scores: dict[str, dict], returns: pd.DataFrame, max_corr: float) -> dict[str, dict]:
    """Among pairs that move together, keep only the cleanest trend (avoid doubling one USD bet)."""
    corr = returns.corr()
    chosen: list[str] = []
    for sym in sorted(scores, key=lambda s: scores[s]["score"], reverse=True):
        if scores[sym]["direction"] == 0:
            continue
        if all(abs(corr.loc[sym, other]) < max_corr for other in chosen):
            chosen.append(sym)
        else:
            scores[sym] = {**scores[sym], "direction": 0, "blocked_by_correlation": True}
    return scores


# ------------------------------------------------------------------------ output
def common_dir() -> Path:
    override = os.getenv("TLME_COMMON_DIR")
    if override:
        return Path(override)
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "TLME"
    return Path("logs") / "TLME"


def write_scan(scores: dict[str, dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    lines = [f"{sym.replace('/', '')},{s['direction']},{s['score']}" for sym, s in scores.items()]
    tmp.write_text("\n".join(lines) + "\n", encoding="ascii")
    tmp.replace(path)  # atomic: the EA never reads a half-written file


def run_once(args: argparse.Namespace, api_key: str) -> dict[str, dict]:
    frames: dict[str, pd.DataFrame] = {}
    for i, sym in enumerate(args.symbols):
        if i:
            time.sleep(args.pause)  # free plan: 8 requests/minute
        try:
            frames[sym] = fetch(sym, args.interval, args.bars, api_key)
        except Exception as exc:  # one bad symbol must not kill the scan
            print(f"skip {sym}: {exc}", file=sys.stderr)
    if not frames:
        raise SystemExit("No data returned; scan file not written.")

    scores = {s: score_symbol(df, args.er_window, args.ema, args.slope_bars, args.min_er) for s, df in frames.items()}
    returns = pd.DataFrame({s: np.log(df["close"]).diff() for s, df in frames.items()}).dropna()
    scores = pick_uncorrelated(scores, returns, args.max_corr)

    write_scan(scores, common_dir() / "scan.csv")
    print(f"{'symbol':<9}{'dir':>4}{'trend':>7}")
    for sym, s in sorted(scores.items(), key=lambda kv: -kv[1]["score"]):
        flag = "  (correlated, skipped)" if s.get("blocked_by_correlation") else ""
        print(f"{sym:<9}{s['direction']:>4}{s['score']:>7.2f}{flag}")
    print("\ncorrelation of returns:\n", returns.corr().round(2).to_string())
    return scores


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--interval", default="15min")
    p.add_argument("--bars", type=int, default=200)
    p.add_argument("--er-window", type=int, default=20)
    p.add_argument("--ema", type=int, default=50)
    p.add_argument("--slope-bars", type=int, default=3)
    p.add_argument("--min-er", type=float, default=0.25, help="below this a pair counts as choppy")
    p.add_argument("--max-corr", type=float, default=0.8)
    p.add_argument("--pause", type=float, default=8.0)
    p.add_argument("--loop", type=float, default=0, help="rescan every N minutes (0 = once)")
    args = p.parse_args()

    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        raise SystemExit("Set TWELVEDATA_API_KEY (environment or .env).")
    while True:
        run_once(args, api_key)
        if not args.loop:
            break
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    main()
