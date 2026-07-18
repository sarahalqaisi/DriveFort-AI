# ZoneGuard UI Fixed Clean Build

Fixes the dashboard JavaScript/toast issue:

- Prevents empty CSS class tokens from crashing the UI.
- Toast notifications no longer block clicks on buttons behind them.
- Adds safe class fallback handling for attack/status rendering.
- Keeps CARLA attack, recovery, and evidence logic unchanged.

Run:

```bat
run_carla_windows.bat
```

Recommended flow:

```text
Connect + Spawn -> Start Normal Drive -> Apply to CARLA -> Recover Vehicle
```
