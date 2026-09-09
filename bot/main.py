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
    parser = argparse.ArgumentParser(description="TL-ME multi-market intraday engine")
    parser.add_argument("--mode", choices=("pipeline", "acquire", "backtest", "validate", "signal", "demo", "live"), default="backtest")
    parser.add_argument("--data", type=Path, help="UTC CSV: time,open,high,low,close")
    parser.add_argument("--days", type=int, default=730, help="MT5 history window")
    parser.add_argument("--output-dir", type=Path, default=Path("data/exness"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.mode == "demo":
        from bot.service import run_service
        run_service()
        return
    if args.mode in {"pipeline", "acquire"}:
        from core.mt5_client import MT5Gateway
        from data_pipeline import acquire_universe_and_validate, acquire_exness_history
        gateway = MT5Gateway()
        result = (acquire_universe_and_validate(gateway, settings, args.output_dir, args.report_dir, args.days)
                  if args.mode == "pipeline"
                  else acquire_exness_history(gateway, settings, args.output_dir, args.days))
        print(result)
        return
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
