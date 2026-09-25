# Final micro-account qualification — 24 September 2026

## Outcome

No candidate qualified for production or order-enabled demo. The selection was
frozen on development history before fresh prices were read. None of the three
bounded alternatives beat the baseline under the development gates. The fresh
period then produced only 0–7 trades per market, below the required 50-trade
out-of-sample gate. No parameters were retuned after reading fresh results.

## Broker feasibility at 0.01 lot

The Exness USD demo account used 1:2000 leverage. At the captured live quote,
all six FX markets could place the tested 0.75, 1.0 and 1.5 ATR stops with $10.
This proves current contract feasibility only, not profitability.

XAUUSD cash stop exposure was approximately:

| Stop | Cash loss | $10 | $12 | $15 |
|---|---:|---:|---:|---:|
| 0.75 ATR | $6.94 | fits | fits | fits |
| 1.00 ATR | $9.25 | fits narrowly | fits | fits |
| 1.50 ATR baseline | $13.87 | no | no | fits |

Spread and adverse execution can increase those losses. For a true $10 gold
minimum, only the 0.75 ATR candidate had useful headroom; it did not qualify as
a profitable replacement. The 1 ATR candidate remained below $10 in the fresh
replay, but development rejected it and its maximum captured entry exposure was
about $8.96 before stress and $9.17 under the defined cost stress.

## Fresh M1 replay

The fresh partition ran from 10 September to 24 September 2026. M15 signals
were replayed through M1 bars with stop-first ambiguity handling, adverse gap
fills and explicit spread/slippage costs.

| Market | Frozen candidate | Development passed | Fresh trades | Baseline expectancy | Candidate expectancy | Decision |
|---|---|---:|---:|---:|---:|---|
| AUDUSD | momentum, 1 ATR, 8 bars | no | 0 | 0 | 0 | reject |
| EURUSD | ranked, 1 ATR, 4 bars | no | 1 | +1.635R | +1.577R | reject |
| GBPUSD | ranked, 1 ATR, 4 bars | no | 3 | -0.188R | +0.676R | reject: only 3 trades |
| USDCAD | momentum, 1 ATR, 8 bars | no | 0 | 0 | 0 | reject |
| USDCHF | ranked, 1 ATR, 4 bars | no | 0 | 0 | 0 | reject |
| USDJPY | momentum, 1 ATR, 8 bars | no | 6 | -0.392R | -0.622R | reject |
| XAUUSD | ranked, 1 ATR, 4 bars | no | 6 | +0.586R | +0.157R | reject |

The GBPUSD result is interesting but statistically unusable. Selecting it now
would be fitting to three fresh observations. Gold's affordable candidate made
money in six trades but materially underperformed the baseline and had worse
drawdown. The baseline itself does not satisfy the $10 gold constraint.

## Final configuration and demo status

No production strategy parameters were changed. The existing baseline remains
the comparison reference, not a newly certified profitable configuration.
Order submission must remain disabled. The next permitted phase is monitor-only
demo-forward collection until each market/configuration reaches the predefined
sample requirement. A later decision must use the already-frozen candidates;
changing them would require a new untouched period.

Reproducibility code is in `experiments/qualify_micro.py`. Full machine-readable
outputs remain in the local `reports/micro_qualification` directory and contain
the frozen selection, hashes, normal/stressed metrics and trade ledgers.
