# TL-ME-AI-BOT

Focused MT5/XAUUSD research system. The first strategy hypothesis is a
trend-regime Donchian breakout with ATR-normalised stops and fixed-fractional
risk. It is not claimed profitable until it passes reproducible historical,
out-of-sample, walk-forward, and demo-forward tests.

## Safety status

Live trading is disabled by default. The current executor refuses order
submission and emergency-close is still unimplemented. Do not add credentials
to the repository.

## First workflow

1. Export broker-quality XAUUSD OHLC data with closed candles.
2. Run: python -m bot.main --mode backtest --data data/XAUUSD_M15.csv
3. Inspect trade count, expectancy, drawdown, and regime stability.
4. Add realistic spread, slippage, and commission modelling before comparing variants.
5. Only after validation, implement and test MT5 order submission on demo.

## Design rules

- No browser automation or DOM selectors.
- No martingale or loss-chasing.
- Price action defines the event; EMA and ATR measure regime and volatility.
- Risk is sized from stop distance, not from a fixed stake.
- Every live action must pass an explicit safety gate.
