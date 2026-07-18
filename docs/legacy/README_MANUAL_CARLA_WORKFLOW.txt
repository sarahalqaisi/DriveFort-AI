MANUAL CARLA WORKFLOW (FIXED)

1. Start CARLA yourself: CarlaUE4.exe -carla-rpc-port=2000
2. Confirm ports 2000 and 2001 are listening.
3. Start ZoneGuard: python app.py
4. Dashboard: Connect CARLA (connects only; never opens CarlaUE4.exe)
5. Dashboard: Spawn Vehicle (spawns the ego vehicle into the already-running CARLA world)
6. Dashboard: Apply attack.

The old automatic CARLA launcher endpoint is disabled in this build to prevent a second CARLA window/process.
