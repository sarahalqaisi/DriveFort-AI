# DriveFort AI V2 Changelog

## 2.0.0 — Rebrand and stabilization baseline

### Added
- DriveFort AI identity assets and brand configuration.
- Platform metadata and lifecycle data in snapshots.
- Health and configuration API endpoints.
- Regression coverage for critical dashboard controls.
- Configurable incident database and command secret.

### Fixed
- Missing `time` import that caused several console actions to return HTTP 500.
- Invalid frontend identifiers introduced during the initial text rebrand.
- Duplicate unreachable `return` in CARLA control helper.

### Changed
- Reports and exports use DriveFort AI filenames and titles.
- Dashboard palette now follows deep navy, electric cyan, emerald, and silver.
- Historical root-level patch notes moved to `docs/legacy/`.

### Compatibility
- Legacy lowercase API fields and method names remain available during the V2 transition.
