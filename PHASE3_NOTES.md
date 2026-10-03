# Kaizen Phase 3 — Market Radar

## What changed

Phase 3 separates **where market data comes from** from **how Kaizen interprets it**.

- `market_data_provider.py` — provider contract + current Alpaca implementation.
- `market_radar.py` — vendor-independent intraday memory, acceleration, scoring, lifecycle, and events.
- `scanner.py` — strategy/orchestration; delegates market-data calls to the provider and Radar behavior to `MarketRadar`.
- `dashboard.py` — displays Radar lifecycle, score, volume acceleration, Market Pulse counts, detail metrics, and Radar transitions.

## Radar lifecycle

`TRACKING → ACCELERATING → IGNITION → ACTIVE → EXTENDED → COOLING`

Radar is an **attention system**, not a buy signal. Existing ORB/VWAP/HOD/Momentum Ignition logic remains the trade-setup layer.

## Metrics tracked

- first/last seen
- observation count and mover-list persistence
- scan-to-scan price acceleration
- mover rank acceleration
- percent-change acceleration
- mover-list re-entry and re-entry improvement
- cumulative-volume delta and volume acceleration
- RVOL, VWAP relationship, VWAP extension, HOD distance
- Radar score/reasons/lifecycle

## New runtime logs

Both are ignored by the project's existing `*.csv` rule:

- `radar_timeline.csv` — one row per tracked mover per completed scan, suitable for later QCLS/USDE-style analysis.
- `radar_events.csv` — lifecycle transitions only.

## Provider independence

`KaizenScanner` accepts a provider through dependency injection:

```python
scanner = KaizenScanner(market_data_provider=my_provider)
```

A future provider implements `MarketDataProvider` methods:

- `get_movers(top=50)`
- `get_snapshots(symbols)`
- `get_bars(symbol, timeframe, limit)`
- `get_daily_bars(symbol, limit)`

The provider's `get_movers` output is normalized to:

```python
{
    "symbol": "QCLS",
    "rank": 12,
    "price": 0.58,
    "change": 0.13,
    "percent_change": 28.9,
    "source": "PROVIDER_NAME"
}
```

`MarketRadar` never imports Alpaca or knows its endpoint shape. That means a Massive/Finnhub/other adapter can be added without rewriting Radar scoring/lifecycle or the GUI.

## First live-session checks

1. Combined scan still returns the same technical setup rows.
2. GUI remains responsive while scanning.
3. Market Pulse begins counting Radar states after repeated mover scans.
4. Opportunity rows show `Radar`, `VolAccel`, and `RadarScore`.
5. Selecting a row shows acceleration/persistence metrics.
6. Live Event Feed shows Radar state transitions.
7. `radar_timeline.csv` and `radar_events.csv` populate.
8. Compare early Radar timestamps with later ORB/Momentum alerts before changing thresholds.

Do not tune Radar thresholds from a single session. Collect several live sessions first.
