# Kaizen Trading Desk Upgrade Blueprint

## Baseline
This package starts from the user's pre-update build. Trading/scanner logic is intentionally preserved during the responsiveness phase so results can be compared against the baseline.

## Phase 1 — Responsive desktop architecture (implemented in this package)
- Move `scanner.run_scan()` and its network/API work off Tkinter's main thread.
- Return results through a thread-safe queue and update widgets only on the Tkinter thread.
- Prevent overlapping scans with `scan_in_progress`.
- Coalesce repeated requests during a scan into one `pending_rescan`.
- Keep Add/Remove controls responsive while a scan is running.
- Add visible `Scanning / queued / ready / error` status.
- Disable only the Run Scan button while a worker is active; the rest of the GUI remains interactive.
- Apply state checkboxes to the last completed DataFrame immediately instead of making another API scan.
- Add horizontal/vertical table scrolling and enlarge the default workspace.

## Phase 2 — GUI 2.0
- Replace the single crowded surface with a master/detail trading desk.
- Main opportunity table: Symbol, Signal/State, Lifecycle, Price, Gain%, RVOL, Float Turnover, Radar Score/Score, Action.
- Selected-symbol detail panel: VWAP, extension, ORB range, float, market cap, ATR, continuation, entry/stop/targets, discovery timestamps and catalyst data.
- Dedicated watchlist/manual-radar panel with instant add/remove and visible pending/loading state.
- Event feed for Radar, Ignition, ORB/HOD, Extended and errors.
- Market/scan health strip: market state, auto-refresh, scan duration, candidate count, API/cache status.

## Phase 3 — Market Radar module
Create `market_radar.py` as a module inside the same application, not a separate program.
- Persistent candidate pool.
- First/last seen and observation count.
- Price, percent-change, rank and volume acceleration.
- Re-entry tracking and threshold-crossing events.
- Provider-neutral normalized event model so Alpaca can later be supplemented/replaced without rewriting strategy logic.

## Phase 4 — Momentum engine refinement
Use historical examples (QCLS, VBIO, USDE) as regression cases.
- Radar Acceleration = attention signal, not an entry recommendation.
- Momentum Ignition = unusual acceleration/participation confirmation.
- Vertical Expansion / Extended = anti-chase warning.
- Halt Resume = later dedicated event/setup logic.

## Phase 5 — Persistence and web/homelab readiness
- Replace growing CSV/in-memory state with SQLite initially.
- Separate data-provider, analytics, strategy, persistence and presentation layers.
- Preserve a clean path toward the planned homelab-hosted web dashboard.

## Validation checklist
1. App opens and remains responsive during a full Combined scan.
2. Window can be moved/resized while scanning.
3. Manual ticker can be typed/added/removed while scanning.
4. Repeated Run Scan clicks do not create overlapping workers.
5. Auto refresh does not create duplicate refresh loops.
6. State filter changes are instant and do not call APIs.
7. Scanner results match the pre-update build for the same market/data inputs.
8. Alerts continue to be generated only from completed scan results on the UI thread.
9. Syntax/import checks pass before packaging.

## Rollback
`dashboard_pre_gui2.py` is the exact dashboard copy made before the Phase 1 edits in this working package.
