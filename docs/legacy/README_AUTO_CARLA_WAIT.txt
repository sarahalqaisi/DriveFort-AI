ZoneGuard EV Auto CARLA Launch + Wait

This version adds /api/carla/auto_launch_wait.
When you press Connect + Spawn or Start Normal Drive, the dashboard will:
1. Open CARLA automatically from D:\Downloads\CarlaSimulator\WindowsNoEditor\CarlaUE4.exe if needed.
2. Wait up to 90 seconds until the CARLA world/map is ready.
3. Force respawn the EV on a road spawn point.
4. Enable normal autonomous driving.

If your CARLA path is different, edit run_carla_windows.bat and set CARLA_EXE_PATH before running the app.
