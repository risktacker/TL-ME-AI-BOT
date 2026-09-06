"""TL-ME-AI-BOT entry point.

Live trading is deliberately disabled unless both LIVE_TRADING=true and
ENABLE_ORDER_SUBMISSION=true are set. Start with --mode backtest.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

from config import Settings
from strategy import generate_signal
from backtest import run_backtest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("backtest", "signal", "live"), default="backtest")
    parser.add_argument("--data", type=Path, help="CSV with time,open,high,low,close columns")
    args = parser.parse_args()
    settings = Settings.from_env()

    if args.mode == "live":
        if not settings.live_trading or not settings.enable_order_submission:
            raise SystemExit("Live trading is locked. Set both safety flags explicitly after testing.")
        from execution import LiveExecutor
        LiveExecutor(settings).run()
        return

    if args.data is None:
        raise SystemExit("--data is required for backtest and signal modes")
    frame = pd.read_csv(args.data, parse_dates=["time"]).sort_values("time").reset_index(drop=True)

    if args.mode == "signal":
        print(generate_signal(frame, settings))
    else:
        result = run_backtest(frame, settings)
        print(result.summary())


if __name__ == "__main__":
    main()
