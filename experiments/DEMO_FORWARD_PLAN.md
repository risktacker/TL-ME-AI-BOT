# Fast multi-market demo-forward profile — 25 September 2026

This is an explicitly order-enabled **demo** experiment. It does not change the
unchanged baseline results into a validation pass and cannot unlock live mode.

## Operating profile

- Exness Standard demo; the trader chooses the starting capital (currently USD 20).
- The bot captures that account's initial balance, starts at 0.01 lot and adds
  another 0.01 only for each full additional starting-balance unit earned.
- Python retains the existing M15/H1/H4 entry package and ranks candidates.
- Independent symbols may enter on the same completed bar. An already-open
  symbol is skipped; there is no arbitrary global two-position ceiling.
- A symbol rearms only after a completed bar returns inside its Donchian range.
- Every entry retains its broker SL/TP if either process disconnects.

## Tick lifecycle

The demo-only MQL5 manager checks all GOLIDE positions every 200 ms:

- close when price crosses back through the original breakout level plus a
  0.05R failure buffer;
- close after 60 seconds if maximum favorable movement never reaches 0.10R;
- close a trade whose edge reached 0.10R and then evaporated or whose positive
  movement has not made a new peak for 20 seconds;
- at 0.20R, ratchet the stop to +0.03R;
- from 0.35R, trail 0.18R behind maximum favorable excursion;
- force-close at 180 seconds as the final stale-position fallback.

These are forward-demo parameters, not a profitability claim. The EA writes
each exit reason to the terminal Common Files `GOLIDE/fast_manager_events.csv`.
Python refuses new orders if the manager heartbeat is older than three seconds.

## Friday window

The existing signal engine trades 06:00–16:59 UTC (08:00–18:59 Zambia time).
Use Friday only inside that window. Do not keep the test running into the weekly
market close, when spreads and execution conditions can become abnormal.
