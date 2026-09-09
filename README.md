# TL-ME-AI-BOT

Focused Exness/MT5 XAUUSD intraday engine. The default package combines an
opening-range breakout, higher-timeframe trend, momentum/volatility filters,
and objective FVG/IFVG/BOS/liquidity features. It targets fast session trades,
not swings.

## Capability

The engine reads closed MT5 candles, builds DST-aware London and New York
opening ranges, follows the H1 regime, confirms M15 breakouts, calculates an
ATR stop and fixed-R target, rejects unaffordable minimum-lot trades, limits
daily activity and losses, and records cost-adjusted results. MT5 submission
and emergency closing exist behind three independent safety flags.

No strategy is assumed profitable. Real Exness history must pass the validation
gate before demo-forward trading; demo must pass before any live activation.

## Strategy package

- Instrument: XAUUSD (the configured MT5 symbol or suffix)
- Signal timeframe: M15
- Regime: H1 EMA 20/50
- Sessions: London 08:00 and New York 08:30 local time, DST-aware
- Trigger: confirmed close outside the first 60-minute range
- Confirmations: displacement, BOS, FVG/IFVG, or liquidity sweep score
- Initial stop: 1.25 ATR
- Target: 1.75R
- Break-even management: 1R
- Time stop: 16 M15 bars (4 hours)
- Limit: 2 trades/day; stop after 3 consecutive losses or 1% daily loss
- Risk: 0.25% of equity per trade

## Commands

```bash
python -m bot.main --mode pipeline --days 730
python -m bot.main --mode backtest --data data/XAUUSD_M15.csv
python -m bot.main --mode validate --data data/XAUUSD_M15.csv
python -m bot.main --mode signal --data data/XAUUSD_M15.csv
```

`pipeline` is the preferred Windows command. With an Exness MT5 terminal open
and logged in, it resolves the account's actual XAUUSD symbol/suffix, exports
M1 and M15 history plus contract specifications, and writes the validation
result to `reports/<symbol>_validation.json`. Login credentials are read by the
terminal itself and are never written to the repository.

The CSV timestamps must be UTC and columns must include
`time,open,high,low,close`. Backtests include configurable spread and slippage.

## Validation gate

The untouched last 30% of history must have at least 50 trades, positive
expectancy, profit factor of at least 1.20, at least 80% profitable bootstrap
samples, and 95th-percentile Monte Carlo drawdown no worse than 10R. These are
minimum research gates, not a profit guarantee.

## Safety

- No DOM/browser automation
- No martingale or averaging down
- No forced minimum-lot trade when account risk is too small
- No credentials in Git
- Live submission requires `LIVE_TRADING=true`,
  `ENABLE_ORDER_SUBMISSION=true`, and `VALIDATION_PASSED=true`
