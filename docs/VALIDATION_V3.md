# DriveFort AI V3 Validation Guide

## What has been validated automatically

The packaged V3 version passed:

- 41 pytest tests.
- 33 standalone API verification checks.
- Python bytecode compilation.
- JavaScript syntax parsing with Node.js.
- Flask route registration and JSON response checks.
- Input normalization for invalid attacks, intensity values, and ECU identifiers.
- Valid and invalid OTA package verification.
- SHA-256 incident-chain verification.
- Three PDF report exports with valid PDF headers and trailers.
- Unique dashboard IDs and frontend-to-API binding checks.
- Existing DriveFort console verification: 27 controls and 19 legacy routes.

## Why live CARLA still needs a manual run

No automated test can prove actual CARLA actor movement, collision physics, sensor timing, map compatibility, or a local CARLA installation when the simulator is not running in the test environment.

Therefore, do not claim 100% physical validation until the following checklist passes on the presentation computer.

## Live CARLA checklist

1. Start the exact CARLA build used by the project.
2. Launch DriveFort AI with the Python interpreter that imports the matching CARLA wheel.
3. Connect CARLA and verify a world/map is returned.
4. Spawn or link the ego vehicle.
5. Confirm speed, steer, throttle, brake, position, and actor ID update from the live actor.
6. Run normal driving for at least 30 seconds.
7. Train the baseline.
8. Run each of the nine adopted attacks individually.
9. Confirm each live attack visibly changes the intended CARLA control or sensor state.
10. Confirm Emergency Stop applies braking to the live actor.
11. Confirm recovery restores a stable actor state.
12. Open the V3 Innovation Lab and verify twin drift changes during the attack.
13. Run the counterfactual benchmark and clearly label it as a digital-twin model.
14. Run the default attack chain one stage at a time.
15. Activate a virtual ECU and confirm the dashboard changes to `VIRTUAL_BACKUP_ACTIVE`.
16. Complete a recovery playbook.
17. Export all three PDF reports.
18. Verify the incident chain after the run.
19. Restart the application and confirm the SQLite database remains readable.
20. Record the CARLA version, map, vehicle blueprint, Python version, and test date.

## Acceptance rule

A feature is ready for the graduation demonstration when:

- Its automated contract passes.
- Its dashboard control responds without a JavaScript error.
- Its CARLA-dependent behavior passes the live checklist where applicable.
- The presentation language distinguishes measured CARLA values from counterfactual/model-derived values.
