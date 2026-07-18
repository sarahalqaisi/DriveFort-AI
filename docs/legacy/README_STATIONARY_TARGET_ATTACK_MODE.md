# Stationary Target Attack Mode

This build fixes the CARLA attack demonstrations so targets are never spawned on top of the ego vehicle and are never teleported/nudged into the ego vehicle during an attack.

## Rule

For every adopted attack:

1. The target vehicle, pedestrian, wall, or collateral actor is spawned ahead of the ego vehicle at a safe visible distance.
2. The target remains stationary during the attack window.
3. The visible effect must come from the ego vehicle itself through the attack control: steering manipulation, brake override, acceleration injection, CAN conflict, DoS loss-of-control, lane drift, or pedestrian detection failure.
4. Damage is verified only if the CARLA collision sensor reports a real collision.

## Why

This avoids fake-looking demonstrations where a target appears directly on the hood of the vehicle. It makes the demo clearer: the attack changes the ego vehicle behavior, and the ego vehicle creates the impact.

## Recommended demo

Use `Acceleration Injection` first. You should see the ego vehicle accelerate toward a stationary target placed ahead. Then test `Steering Manipulation`, `Brake Override`, and `Pedestrian Detection Attack`.
