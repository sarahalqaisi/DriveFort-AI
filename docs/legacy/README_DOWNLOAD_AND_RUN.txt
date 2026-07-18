ZoneGuard EV - Tabs Working CARLA Commands Build

1) Start CARLA first:
   D:\Downloads\CarlaSimulator\WindowsNoEditor\CarlaUE4.exe

2) Open this folder and run:
   run_carla_windows.bat

3) In the dashboard use:
   Connect + Spawn
   or Start Normal Drive

This build uses a hard CARLA command hotfix:
- destroys stale ZoneGuard/Tesla ego actor only
- respawns a clean EV actor on a valid CARLA road spawn point
- enables Traffic Manager autopilot
- starts the CARLA tick loop
- sends attacker commands directly to CARLA with visible control hold

If CARLA still does not move, check the CMD log for POST /api/carla/force_respawn_drive and send the red error toast or CMD traceback.
