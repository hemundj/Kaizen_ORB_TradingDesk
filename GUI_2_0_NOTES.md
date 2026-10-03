# Kaizen GUI 2.0 - Phase 1

This build changes the dashboard presentation while preserving the v3.1 scanner and asynchronous worker architecture.

## New layout
- Dark trading-desk theme and application header
- Compact Opportunities table focused on decision-critical fields
- Manual Radar sidebar with fast add/remove controls
- Market Pulse summary counts
- Selected-symbol detail panel for VWAP, float, market cap, ORB, ATR, entry/stop/targets, etc.
- Live Event Feed for state-transition alerts
- Existing display filters, scan modes, auto-refresh, alert logging, and background scan worker retained

## Deliberately unchanged
- Scanner strategy logic
- Alpaca/FMP integrations
- Alert CSV schema
- Discovery logging
- Market Radar scoring logic in scanner.py

## Test checklist
1. Copy your local config.py into the test folder (never commit it).
2. Run `python dashboard.py`.
3. Confirm the UI remains responsive during a Combined scan.
4. Confirm Opportunities populate and selecting a row updates the detail panel.
5. Add/remove a Manual Radar ticker during a scan.
6. Toggle state filters without causing a new API scan.
7. Confirm alerts.csv/discovery files continue updating.
8. Verify Auto Refresh performs one scan at a time.

Do not replace the v3.1 Git checkpoint until this build passes a live-market test.
