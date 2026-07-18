# ZoneGuard EV - Real CARLA Only Mode

This build is configured to avoid fake dashboard values when CARLA is not connected.

## What changed

- Attack dropdown labels now show English + Arabic.
- Normal drive, full demo, owner-visible attacks, and force attack refuse to generate fake telemetry/damage without a live CARLA vehicle actor.
- If CARLA is not linked, the dashboard stays in Waiting for CARLA state and attack endpoints return an error message.
- When CARLA is ready, attacks are applied through the live `CarlaBridge.apply_direct_attack(...)` path to the simulator vehicle controls.

## Required runtime

- CARLA 0.9.13
- Python 3.7.x 64-bit for the CARLA Python package
- A running CARLA server on localhost:2000, or set `CARLA_EXE_PATH`/`CARLA_ROOT` as described in the existing CARLA docs.

## Validation

`pytest -q` passes: 14 tests.
