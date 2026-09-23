# TL-ME-AI-BOT

Focused Exness/MT5 multi-market intraday engine. It continuously scans liquid
FX majors and XAUUSD, ranks qualified setups, and acts on the strongest closed-
candle decision. It targets fast session trades, not swings.

## Capability

The research pipeline reads closed MT5 candles across the configured universe. The
execution service follows an explicit `BOT_QUALIFIED_SYMBOLS` allowlist, so a market
cannot become tradable merely because it is available in MT5. By default that
allowlist contains all seven configured markets: EURUSD, GBPUSD, USDJPY, AUDUSD,
USDCAD, USDCHF and XAUUSD. The engine follows aligned H1/H4 regimes, confirms M15
momentum breakouts, calculates an ATR stop and fixed-R target, ranks simultaneous
edges across the qualified pool, and records cost-adjusted results. MT5 submission
and emergency closing exist behind three independent safety flags.

The deployment runner processes completed M15 candles exactly once, refuses a
non-demo account in demo mode, prevents duplicate positions, sizes from broker
contract specifications, places broker-side stop-loss/take-profit exits, and
enforces the same three-hour time exit used by the backtest.

No strategy is assumed profitable. Real Exness history must pass the validation
gate before demo-forward trading; demo must pass before any live activation.

## Strategy package

- Universe: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF and XAUUSD by default
- Execution pool: all seven configured markets by default; `BOT_QUALIFIED_SYMBOLS`
  can explicitly restrict the tradable allowlist without changing the research universe
- Signal timeframe: M15
- Regime: aligned H1 EMA 20/50 and H4 EMA 12/30
- Active window: 06:00-16:59 UTC
- Trigger: close outside the previous 20-bar Donchian channel
- Confirmation: candle body of at least 0.40 ATR and normal volatility
- Initial stop: 1.50 ATR
- Target: 1.75R
- Time stop: 12 M15 bars (3 hours)
- Signal rearm: first qualified breakout per symbol/day; other symbols keep scanning
- Candidate selection: rank simultaneous valid setups and act on the strongest edge
- Micro mode: 0.01 volume per configured $10 equity step below the scaling threshold
- Scaling mode: proportional broker-aware sizing above the threshold
- No daily-loss or consecutive-loss shutdown in `micro_aggressive` mode

## Commands

```bash
python -m bot.main --mode pipeline --days 730
python -m bot.main --mode backtest --data data/XAUUSD_M15.csv
python -m bot.main --mode validate --data data/XAUUSD_M15.csv
python -m bot.main --mode signal --data data/XAUUSD_M15.csv
uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
python -m bot.main --mode demo
```

Open `http://localhost:8000` for the responsive GOLIDE control panel. It reads
validation, account, market, position and journal state. It can pause/resume
demo monitoring and request an emergency stop. It has no live-unlock endpoint.

`pipeline` is the preferred Windows command. With an Exness MT5 terminal open
and logged in, it resolves broker symbol suffixes, exports M15 history and
contract specifications for every configured market, and writes individual
reports plus `reports/universe_validation.json`. Login credentials are read by the
terminal itself and are never written to the repository.

## Windows VPS deployment

Open PowerShell in the repository on the VPS and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\windows\Install-Golide.ps1
```

Edit `.env`, generate a long random `DASHBOARD_TOKEN`, and retain
`EXECUTION_MODE=disabled` and `ENABLE_ORDER_SUBMISSION=false` until readiness
and MT5 demo smoke tests are complete. The installer creates restartable tasks
at Windows logon. `Start-Golide.ps1`, `Stop-Golide.ps1`, and
`Test-Readiness.ps1` provide operational controls. The panel binds to localhost;
remote publication requires a separate authenticated HTTPS tunnel.

The CSV timestamps must be UTC and columns must include
`time,open,high,low,close`. Backtests include configurable spread and slippage.

## Validation gate

The untouched last 30% of history must have at least 50 trades, positive
expectancy, profit factor of at least 1.20, at least 80% profitable bootstrap
samples, and 95th-percentile Monte Carlo drawdown no worse than 10R. These are
minimum research gates, not a profit guarantee.

Validation additionally requires at least four profitable chronological folds
out of five and positive performance when recorded spreads increase by 50% and
configured slippage doubles.

## Safety

- No DOM/browser automation
- No martingale or averaging down
- Micro mode deliberately uses minimum volume and records its estimated stop loss
- No credentials in Git
- Live submission requires `LIVE_TRADING=true`,
  `ENABLE_ORDER_SUBMISSION=true`, and `VALIDATION_PASSED=true`
