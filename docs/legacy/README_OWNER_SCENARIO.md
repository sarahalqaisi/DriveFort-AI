# ZoneGuard Owner Attack Scenario

This build adds a smooth CARLA owner-facing scenario:

1. Start CARLA `CarlaUE4.exe`.
2. Run `run_carla_windows.bat`.
3. Click **Start Normal Drive**. The The EV spawns, enables CARLA Traffic Manager autopilot, and the spectator camera follows smoothly.
4. Wait 10-20 seconds.
5. Click **Attack Vehicle Now**. The dashboard shows owner alerts, speed, CARLA map, coordinates, battery state, battery/motor temperature, affected modules, and recommended action.

New backend endpoints:

- `POST /api/carla/normal_drive`
- `POST /api/carla/attack_after_drive`

The attack is a simulation for demonstration and diagnosis. It shows how ZoneGuard detects and explains cyber-physical impact on vehicle modules.
