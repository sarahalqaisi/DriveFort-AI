IMPORTANT FIX
The diagnostics endpoint previously appeared after app.run(), so Flask never registered it while the server was running. It has been moved above app.run().

Run:
1) Start CARLA.
2) Double-click run_fixed_windows.bat.
3) Open http://127.0.0.1:5000/api/carla/attack_diagnostics

Expected: JSON output, not 404.

CARLA API compatibility fix: diagnostics now uses local tracked autopilot state; it does not call the unsupported Vehicle.is_autopilot_enabled() method.
