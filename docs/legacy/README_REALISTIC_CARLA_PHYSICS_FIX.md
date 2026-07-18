# Realistic CARLA Physics Fix

This patch fixes the issue where CARLA attacks made the ego vehicle behave unrealistically, jump, slide violently, or fly.

## Root cause
The previous live-impact path repeatedly used `set_target_velocity()` during attack execution. In CARLA, this can inject external velocity impulses into the actor every tick. When combined with high steering, close targets, handbrake-locked vehicles, or collision physics, the vehicle may behave acrobatically instead of realistically.

## What changed
- Removed active velocity injection during attack execution.
- Attack execution now relies on normal `VehicleControl` only: throttle, brake, steer.
- Added smooth control ramping during the first second of an attack.
- Clamped steering/throttle to realistic demo ranges.
- Prepared the ego vehicle before attacks by clearing autopilot/reverse/handbrake conflict.
- Kept stationary targets stationary without teleporting them during the run.
- Static/pedestrian targets avoid unnecessary physics simulation to reduce bounce.
- Target vehicles are stopped with brake instead of handbrake locking.

## Expected behavior
- Acceleration injection: ego vehicle accelerates forward naturally.
- Steering manipulation: ego vehicle drifts/turns without jumping.
- Lane drift/GPS/sensor attacks: gradual visible deviation.
- Pedestrian/target actors stay stationary; any collision must come from the ego vehicle motion and CARLA collision sensor.

## If the vehicle still behaves oddly
Use synchronous mode at 20 FPS and restart the scenario after recovery:

```bash
CarlaUE4.exe -windowed -ResX=800 -ResY=600 -quality-level=Low -carla-rpc-port=2000 -dx11
```

Then run the dashboard and press Recover/Reset before applying a new attack.
