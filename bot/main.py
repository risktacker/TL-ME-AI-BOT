"""CLI for backtest, validation, signal inspection, and locked live mode."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from backtest import run_backtest
from config import Settings
from strategy import generate_signal
from validation import validate_strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="TL-ME XAUUSD intraday engine")
    parser.add_argument("--mode", choices=("backtest", "validate", "signal", "live"), default="backtest")
    parser.add_argument("--data", type=Path, help="UTC CSV: time,open,high,low,close")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.mode == "live":
        if not (settings.live_trading and settings.enable_order_submission and settings.validation_passed):
            raise SystemExit("Live mode is locked by three independent safety flags.")
        raise SystemExit("Connect the Exness MT5 terminal and run the deployment loop on a Windows host.")
    if args.data is None:
        raise SystemExit("--data is required")
    frame = pd.read_csv(args.data, parse_dates=["time"]).sort_values("time").reset_index(drop=True)
    if args.mode == "signal":
        print(generate_signal(frame, settings))
    elif args.mode == "validate":
        print(asdict(validate_strategy(frame, settings)))
    else:
        print(run_backtest(frame, settings).summary())


if __name__ == "__main__":
    main()

