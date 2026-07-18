# DriveFort AI V3 Changelog

## New architecture

- Added `src/v3/advanced_features.py` as a lock-protected service layer.
- Added `src/v3/api.py` as an explicit Blueprint with V3 contracts.
- Kept the original V2 project untouched and created a separate V3 directory.
- Added no new monkey patches to `SimulationEngine` or `carla_bridge.py`.

## New capabilities

- Time-machine event recording with bounded history.
- Ghost digital-twin path prediction and collision exposure.
- Dynamic safety envelope for steering, throttle, and brake.
- Five-source threat confidence fusion.
- Explainable AI decision evidence and Copilot responses.
- Counterfactual protected/unprotected benchmark.
- ECU integrity map with quarantine and virtual backup states.
- Multi-stage attack chains, adaptive attacker planning, and low-and-slow mode.
- Recovery playbooks and incident storyboard.
- Attack graph and committee Mission Control mode.
- Scenario Director with five guided scenarios.
- Fleet Command Center, V2V threat sharing, and OTA verification.
- Executive, technical, and forensic JSON/PDF reports.

## Reliability and compatibility

- Fixed SQLite connection lifecycle to prevent leaked handles during polling.
- Added conditional dependency tracks for legacy Python 3.7 CARLA and modern Python/Docker.
- Vendored Chart.js, Leaflet, Space Grotesk, and Font Awesome locally so the dashboard does not depend on internet access.
- Updated brand and API version to 3.0.0.

## Verification

- 42 automated tests passing.
- 33 standalone V3 API checks passing.
- V3 feature-module coverage reached 88% during the development validation run.
- All V3 DOM IDs are unique and mutating controls are statically verified against their API routes.
