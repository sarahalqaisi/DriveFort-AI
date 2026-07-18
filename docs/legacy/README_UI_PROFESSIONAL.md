# ZoneGuard Professional UI

This build replaces the older dashboard with a compact high-end cockpit UI:

- One-click CARLA connect + spawn.
- Normal driving flow before attack injection.
- Smooth camera visualization panel.
- Live map with coordinates and route status.
- Speed, battery, battery temperature, motor temperature, risk score.
- Owner alerts and damaged internal component prototype.
- Clickable component labels and professional toast notifications.
- Report export buttons.

Recommended run order:

```bat
py -3.7 check_carla_python_compat.py
run_carla_windows.bat
```

Then open `http://127.0.0.1:5000` and use:

1. Connect + Spawn
2. Start Normal Drive
3. Attack Vehicle Now
4. Reset Demo to recover


## Added Executive Demo Features

- **Run Full Demo** button: one click performs normal driving baseline, injects the attack, updates owner diagnostics, and stores before/after evidence.
- **Incident Report PDF**: downloads a concise report with threat level, risk score, before/after telemetry, damaged components, root cause, defense strategy, and event timeline.
- **Before/After Metrics Panel**: shows speed, battery, thermal, lane and attack deltas directly in the dashboard.

Recommended demo flow: `Connect + Spawn -> Run Full Demo -> Download PDF`.
