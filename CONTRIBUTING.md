# Contributing to DriveFort AI

1. Create a branch from `main`.
2. Keep changes focused and avoid adding new monkey patches to the legacy simulation engine.
3. Add or update tests for every behavior change.
4. Run `pytest -q` and `python verify_drivefort_v3.py` before opening a pull request.
5. Do not commit runtime databases, `.env` files, secrets, generated reports, or CARLA binaries.

Suggested branch names:

- `feature/<short-name>`
- `fix/<short-name>`
- `docs/<short-name>`

Pull requests should describe the change, test evidence, and whether live CARLA validation is required.
