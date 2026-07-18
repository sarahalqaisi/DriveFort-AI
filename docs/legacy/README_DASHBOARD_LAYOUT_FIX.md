# Dashboard Layout Fix

This patch fixes the ZoneGuard Defense/Roadmap panel overlap.

Root cause: the dynamically injected Roadmap Enhancement panel was inserted inside `.content-grid` without spanning all 12 grid columns, so it was squeezed into a single narrow column and all XAI/Digital Twin/Forensics/Metrics cards overlapped.

Fix applied:
- Forces `.roadmap-enhancement-panel` to use `grid-column: 1 / -1`.
- Adds responsive auto-fit grids for Roadmap cards and KPI metrics.
- Adds `min-width: 0` and overflow wrapping to prevent text/card overlap.
- Bumps CSS/JS cache version in `index.html`.
