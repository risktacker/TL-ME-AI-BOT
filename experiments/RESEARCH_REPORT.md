# TL-ME lifecycle investigation — 24 September 2026

## Decision

No winning multi-market bot has been demonstrated. No experimental exit or
multi-position strategy is approved for production. Existing entry features,
dashboard, MT5 execution, SL/TP, emergency close and safety locks are retained.
The delivered improvements are measured scanner speed, corrected FX point units,
current-spread rejection, broker-native monetary stop valuation, an optional
structural risk ceiling, stronger validation, and reproducible lifecycle research.

Base branch: `rebuild/mt5-xauusd-core` at
`4371ae461dbc1d110de8b55d0fb673cec3c6f559`.

## Evidence and research protocol

Recovered seven broker M15 exports covering approximately 10 September 2025 to
10 September 2026: 23,627 gold bars and approximately 24,863 bars per FX market.
These exports were already used in previous research. The final 30% below is a
**reused chronological comparison**, not untouched out-of-sample evidence.
Nothing in this report establishes future profitability.

18 predeclared policies were tested per market, including the baseline (126
market-policy evaluations; two markets have zero eligible trades). The first
70% was used for selection with five chronological evaluation folds. A new policy
had to improve development expectancy, not increase drawdown, have PF >=1.2,
at least 50 development trades and four positive development folds. None passed.
The runner's selection expression uses development results only; later-period
metrics are diagnostic. No combinations were selected after seeing later results.
No rolling parameter optimization is performed; these are fixed-policy temporal
stability tests rather than fitted walk-forward optimization.

The original backtester was run before code changes. The new harness reproduces
its baseline trade counts and net R to four decimals on all seven exports. It
also models adverse stop gaps without capping them at -1R. Stops update only
after a completed bar and become active next bar. Invalidation exits fill at
next open, not retrospectively at the close used to generate the decision.
Ambiguous intrabar stop/target touches choose the stop first.

Separate 1.5x spread, 2x slippage and combined stress are recorded. Costs use
broker point units, recorded M15 spreads and one-way slippage equal to 25% of
median spread, matching the existing acquisition pipeline. These remain
simplified price-cost assumptions: no historical bid/ask ticks, commission
schedule, intrabar spread spikes, latency measurements, margin-call simulation,
or mark-to-market portfolio drawdown. M15 results cannot validate tick scalping.

Metrics include expectancy, PF, wins/losses, payoff, realized R drawdown,
five-trade circular block-bootstrap 95% drawdown and profitable fraction,
daily-R Sharpe proxy, holding time, summed position minutes, session/regime
breakdowns and constant-budget portfolio slots. Daily-R Sharpe is not a broker
cash-equity Sharpe. Snapshot tick values are approximate for historical currency
conversion. Final production evaluation needs these missing execution inputs.

## Actual baseline

| Market | Trades | Net R | Expectancy R | PF | Max realized DD R |
|---|---:|---:|---:|---:|---:|
| AUDUSDm | 29 | -8.8359 | -0.3047 | 0.5709 | 9.3607 |
| EURUSDm | 85 | -9.7729 | -0.1150 | 0.8081 | 19.2236 |
| GBPUSDm | 91 | -3.0234 | -0.0332 | 0.9431 | 19.9034 |
| USDCADm | 0 | 0 | 0 | 0 | 0 |
| USDCHFm | 0 | 0 | 0 | 0 | 0 |
| USDJPYm | 105 | -37.5104 | -0.3572 | 0.4681 | 37.5104 |
| XAUUSDm | 145 | +35.6446 | +0.2458 | 1.5333 | 8.5464 |

Zero-trade markets were not forced through filters. The exit ceiling is three
hours, but baseline gold holds average about 94 minutes. The first-breakout-per-
day rearm rule also limits frequency. BOS/FVG/IFVG influence ranking; they are
not each mandatory independent entry gates in this branch. H1/H4 features are
preserved as implemented.

## Gold exit comparisons

All rows below have 39 trades in the later 30%, except rearm (65).

| Policy | Expectancy R | PF | DD R | Mean minutes |
|---|---:|---:|---:|---:|
| Baseline 1.75R / 12 bars | 0.2915 | 1.6422 | 5.1527 | 95.77 |
| 1R target | 0.0798 | 1.1847 | 6.0152 | 70.77 |
| Four-bar time exit | 0.3272 | 2.2728 | 2.8304 | 47.31 |
| Eight-bar time exit | 0.2556 | 1.6011 | 6.1264 | 76.54 |
| Cost-covered BE at 0.75R close | 0.2381 | 1.5373 | 6.8749 | 91.15 |
| Cost-covered BE at 1R close | 0.2715 | 1.5982 | 5.1527 | 94.23 |
| ATR trailing | 0.2212 | 1.4860 | 6.5534 | 93.08 |
| Chandelier trailing | 0.2813 | 1.6198 | 5.1527 | 94.62 |
| Three-bar structure trailing | 0.2331 | 1.5136 | 6.2640 | 91.15 |
| 50% profit retracement | 0.1901 | 1.4188 | 7.7328 | 85.38 |
| Failed breakout: close inside original level | 0.4160 | 2.3223 | 2.3012 | 65.77 |
| Momentum decay | 0.2746 | 1.8168 | 4.4596 | 60.77 |
| Time decay: no 0.5R excursion by bar 4 | 0.3854 | 2.1348 | 3.5217 | 79.23 |
| Reset/rearm after return inside rolling channel | 0.1363 | 1.2713 | 4.3279 | 93.00 |

Regime failure, opposite raw signal and volatility contraction did not change
gold's later-period results under the tested thresholds. Opposite BOS is in the
machine-readable results. Failed-breakout exits remain a research candidate:
development expectancy fell from 0.2290R to 0.1602R and only three of five folds
were positive. Selecting them because the later period looks good would violate
the requested workflow. Early break-even reduced development expectancy to
0.0903R and increased DD from 8.55R to 14.80R. Rearming increased opportunities
but reduced development expectancy to 0.0763R and increased DD to 19.17R.

Gold's baseline later-period stress expectancy is 0.2714R. That is encouraging
historical evidence, but its 39 observations are below the 50-trade gate. The
updated production validator also rejects gold for full-sample Monte Carlo DD
above 10R. The previously displayed fractional drawdown was not meaningful for
the micro-lot ladder; it now returns null instead of a misleading percentage.

## Controlled concurrency

The event-ordered comparison ranks simultaneous signals and allows at most one
position per symbol. One total initial risk unit is split across slots; adding
slots does not silently triple the risk budget.

| Slots | Development trades | Development net budget R | Later trades | Later net budget R | Later max positions |
|---|---:|---:|---:|---:|---:|
| 1 | 280 | -15.3688 | 82 | 13.4809 | 1 |
| 2 | 355 | -17.0203 | 88 | 7.2349 | 2 |
| 3 | 366 | -13.2043 | 88 | 4.8233 | 2 |

Every development portfolio loses. Concurrency is rejected for promotion.
This is an opportunity/slot study, not a replay of the production scanner or a
broker-feasible equity simulation. It does not measure intratrade portfolio DD.
Same-symbol pyramids, partial exits, basket-money/R exits and profit-funded adds
have **not** been empirically validated or implemented in this delivery. At a
0.01 minimum and step, splitting a 0.01 trade or decreasing its add size is
impossible. Floating profit must not be counted as spendable protection; a
future pyramid must confirm every stop change and assess aggregate cash loss,
margin and gap reserves before adding. Equal-minimum adds can be considered
only within that aggregate risk constraint. No grid/martingale was added.

## Micro-account feasibility

Median cash exposure at the original ATR stop, using exported minimum lots:

| Market with baseline trades | 0.01-lot median stop loss | Fraction of $10 |
|---|---:|---:|
| AUDUSD | $1.22 | 12.2% |
| EURUSD | $1.09 | 10.9% |
| GBPUSD | $1.40 | 14.0% |
| USDJPY | $1.06 | 10.6% |
| XAUUSD | $13.18 | 131.8% |

Gold's 95th percentile is $27.17 before execution overruns. None of the observed
minimum-lot trades fit a 5% budget on $10. This is a contract-size constraint,
not a loss-streak stop or arbitrary minimum-account rule. Maximum leverage
does not reduce price-to-stop cash loss. The optional cap rounds affordable
volume down and skips only a setup that cannot fit the broker minimum. Live
valuation now calls MT5 `order_calc_profit` in account currency. Commission,
slippage and gaps can still exceed the modeled stop amount.

`MAX_STOP_RISK_PCT=0` retains the previous uncapped ladder for backward
compatibility; it is **not** endorsed as controlled risk. The disabled reference
preset sets 0.05 as an explicit ceiling, not a profitability-selected parameter.
No account setting or trading flag was changed externally.

## Mechanism/evidence matrix

Sources demonstrate implementations, not independently audited profitability.
Commercial availability is not proof of successful returns. Independent source
families include EarnForex, QuantConnect/LEAN, separate MQL5 authors, MetaQuotes
documentation, and the Leung/Zhang research paper.

| Mechanism repeatedly implemented | Primary sources | TL-ME relevance and decision |
|---|---|---|
| Profit activation before stop ratcheting | [EarnForex profit trail](https://www.earnforex.com/metatrader-expert-advisors/Trailing-Stop-on-Profit/), [MQL5 trailing implementation](https://www.mql5.com/en/articles/134) | Missing live; tested close-bar BE/trails fail promotion. Stops must never loosen. |
| Volatility-sized trailing | [EarnForex ATR EA](https://www.earnforex.com/metatrader-expert-advisors/atr-trailing-stop/), [MQL5 trailing classes](https://www.mql5.com/en/articles/14862) | ATR/chandelier tested independently; no surviving enhancement. |
| Profit retracement / portfolio drawdown | [LEAN risk models](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/supported-models), [Account Protector](https://www.earnforex.com/metatrader-expert-advisors/Account-Protector/) | Peak tracking and cash basket limits relevant; retracement tested; basket execution deferred. |
| Gold session breakout with volatility, BE and partial exits | [London Gold Breakout](https://www.mql5.com/en/market/product/176885), [Gold Highest BreakOut](https://www.mql5.com/en/market/product/155821) | Product descriptions confirm deployed feature sets only. Existing trend/ATR/session filters retained; no marketing returns used. |
| Scalping versus momentum/swing operating modes | [Dynamic Multi-Pair part 5](https://www.mql5.com/en/articles/19989) | Timeframe-specific risk/exit logic exists; faster exits alone are not a new entry edge. No automatic M1 migration. |
| Spread-aware market routing | [Dynamic Multi-Pair part 6](https://www.mql5.com/en/articles/20371), [Market robot checks](https://www.mql5.com/en/articles/2555) | Fix per-symbol point conversion and check current spread before submission. Slippage is stressed, not assumed capped by deviation. |
| Partial profits | [Partial position closing implementation](https://www.mql5.com/en/articles/19682), London Gold Breakout above | Broker lot-step feasibility required; impossible to split minimum 0.01 position. Deferred, not assigned synthetic profits. |
| Winner-only pyramids with coordinated stops | [CPyramidEngine](https://www.mql5.com/en/articles/22187) | Useful architecture: state recovery, ticket identity, confirmed modifications, decreasing risk. Its claims of risk-free outcomes are rejected because gaps/costs exist. |
| Basket exposure and risk attribution | [Basket Risk implementation](https://www.mql5.com/en/articles/24331), Account Protector above | Aggregate money risk and position counts useful; floating P/L alone is insufficient. No production basket trigger. |
| Trailing stop plus fixed profit limit | [Leung and Zhang](https://arxiv.org/abs/1701.03960) | Model-dependent optimal stopping result, not evidence for an arbitrary tight trailing distance on gold. Test target and trail jointly only after independent qualification. |
| News exclusions | [MQL5 calendar](https://www.mql5.com/en/docs/calendar), London Gold Breakout above | TL-ME has an unwired external-CSV helper. Historical point-in-time news is absent, so no fabricated news-filter backtest. Server timezone requires conversion. |
| Broker account-currency risk | [MT5 order_calc_profit](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py), [EarnForex Position Sizer](https://www.earnforex.com/metatrader-expert-advisors/Position-Sizer/) | Implemented valuation plus optional risk ceiling. Minimum lots are not equal risk across symbols. |

Fast invalidation is based on completed structural/price evidence, never simply
negative floating P/L. A spread spike is a reason to restrict new entries, not
automatically liquidate into bad liquidity; live spike-exit tests require ticks.
Grid, averaging-down and loss-multiplier production changes are rejected without
a positive independent edge and explicit tail-risk model. No claim is made that
these experiments or a chosen win rate eliminate ruin.

## Python / EA / VPS architecture

| Architecture | Strength | Limitation | Decision |
|---|---|---|---|
| Existing Python + MT5 | Keeps research, ranking and dashboard; smallest operational change | Nominal 15-second polling plus work/network time can miss intrabar protection triggers | Retain now; server-side SL/TP already operate independently of Python polling |
| Full MQL5 EA | Native events and Strategy Tester | Duplicates research stack, large migration and parity risk | Reject full port without evidence |
| Python + lightweight MQL5 manager | Python closed-bar decisions; terminal-side protection and transaction reconciliation | Additional state/ownership and communication failure modes | Preferred future architecture if tick tests demonstrate exit benefit |

For uniformly timed arrivals, a 15-second polling interval implies roughly 7.5
seconds average waiting before processing, plus computation and broker latency;
this is an estimate, not a measured fill benchmark. Local 800-bar signal work
fell from 77.38ms to 46.07ms per call over ten repetitions (~40.5%), with exact
signal/rank parity. It does not remove the poll delay.

[OnTick documentation](https://www.mql5.com/en/docs/event_handlers/ontick) states
events are chart-symbol-specific and duplicate pending/processing NewTick events
are not queued. A multi-market EA therefore needs per-symbol handling or a short
timer with fresh quote checks; one chart's ticks are insufficient. Keep handlers
short. Python remains responsible for research and ranking. A future EA should
own stop changes/exits exclusively, retain broker SL on disconnect, persist
initial R, acknowledge idempotent commands, reconcile through OnTradeTransaction,
validate tick/volume/stops/freeze levels, and distinguish netting from hedging.
Do not run competing Python and EA managers on the same tickets.

Use the existing Windows VPS with MT5 and Python on the same host, restart
supervision and the authenticated dashboard. No new hosting target is needed.
No EA was written or compiled because no exit policy qualified and this Linux
environment has no Windows MT5 terminal for integration/tick validation.

## Exact delivered changes and readiness

- `strategy/engine.py`: score only nonzero signal rows; exact parity verified.
- `bot/service.py`: broker point units per symbol; current-spread gate; final
  broker-native stop exposure and optional ceiling enforcement.
- `core/mt5_client.py`: fail-closed `order_calc_profit` stop valuation.
- `risk/risk_engine.py`, `config.py`: validate micro metadata and expose optional
  `MAX_STOP_RISK_PCT`; retain existing daily/streak behavior.
- `validation.py`: enforce documented holdout count, PF, bootstrap and DD gates;
  do not translate micro R drawdown into fictitious fixed-fraction percentages.
- `experiments/lifecycle.py`, `run_lifecycle.py`: isolated policies, stress,
  temporal evaluation, sizing diagnostics and fixed-budget concurrency study.
- `tests/test_lifecycle*.py`, `test_validation_holdout.py`: regression tests for
  gap/ambiguity, short symmetry, next-bar protection, next-open invalidation,
  risk budgets, symbol units, scoring parity and validation rejection.

Final surviving production strategy configuration is the unchanged baseline:
M15, H1 EMA20/50, H4 EMA12/30, Donchian20, displacement0.40ATR, stop1.50ATR,
target1.75R, maximum12 bars, first daily breakout, one open position. This is a
comparison reference, not an approved winning configuration. All seven markets
remain available for research. `demo_candidate.env` deliberately contains no
execution-qualified symbols and disabled submission flags.

Readiness: offline research/replay ready; Exness order-enabled demo-forward trial
**not ready**. Missing gates: fresh untouched data, enough independent trades,
tick/bid-ask costs and stop sequencing, cash/margin-aware portfolio replay,
Windows MT5 smoke test and broker acknowledgment/restart tests. This delivery
does not complete those unavailable tests, pyramiding/basket/partial studies,
or a hybrid EA deployment. No orders were sent and no live locks were opened.

Reproduce with:

```bash
python -m pytest -q
python -m experiments.run_lifecycle --data-dir PATH_TO_EXPORTED_UNIVERSE --output reports/lifecycle
```

The result bundle includes every policy's metrics, session/regime breakdown,
stress results, trade ledger, data hashes/specifications, and gold validation.
Data account identifiers and credentials are excluded.
