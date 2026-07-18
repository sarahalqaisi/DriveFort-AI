# ZoneGuard EV - Severe CARLA Impact Mode

This version strengthens the 9 adopted graduation attacks so their effect is visually obvious inside CARLA while still avoiding fake telemetry.

## What changed

- Each adopted attack creates a real CARLA impact scene before applying control.
- The scene includes a primary target such as a vehicle, pedestrian, or roadside/static barrier.
- A secondary collateral actor is spawned where possible so the demonstration clearly shows risk to traffic participants.
- The ego vehicle receives aggressive but bounded CARLA controls and a target velocity so the effect is visible even from a standing start.
- If contact does not happen quickly, the already-spawned target actor is moved closer to the ego path. The result is still not marked as verified unless the CARLA collision sensor fires.
- Collision severity is calculated from CARLA normal impulse and reported as minor, moderate, severe, or critical.

## Adopted attacks covered

1. Steering Manipulation
2. Brake Override
3. Acceleration Injection
4. Sensor Spoofing
5. GPS Spoofing
6. CAN Bus Injection
7. Denial of Service (DoS)
8. Lane Drift Attack
9. Pedestrian Detection Attack

## Verification

Start CARLA first, then run:

```bat
py -3.7 verify_adopted_carla_attacks.py
```

The script fails closed. It exits with a non-zero code unless all 9 adopted attacks are applied to a live CARLA vehicle and verified by the collision sensor.

## Important limitation

CARLA can verify collisions and show physical motion, vehicles, pedestrians, and obstacles. It does not always render detailed crumpled body deformation for every vehicle model. Therefore the dashboard reports severe/critical damage through verified collision impulse, impacted actor type, and affected systems.
