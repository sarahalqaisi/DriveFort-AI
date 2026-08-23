# Changelog

Notable changes to DriveFort AI are recorded here. The project follows the
structure of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses
version numbers for documented releases.

Historical source changelogs are preserved under [docs/changelog/](docs/changelog/).
Their verification counts describe those historical snapshots, not the current
repository.

## Unreleased

### Changed

- Refactored the V3 feature layer into modular threat-fusion, benchmark,
  recovery, fleet, OTA, and reporting services while retaining
  `DriveFortV3Features` as the backward-compatible facade.
- Moved PDF rendering and request validation into dedicated V3 modules.
- Redesigned the README around the connected-vehicle cybersecurity and resilient
  defense portfolio narrative.
- Added a maintainable architecture diagram, grouped capability presentation,
  concise demo path, and explicit validation boundaries.

### Security

- Added explicit synthetic-versus-measured benchmark provenance, deterministic
  scenario identifiers, and bounded evidence records.
- Hardened OTA hash, signature, version, secret, and demonstration-signing
  validation.
- Sanitized client-visible V3 engine errors while retaining server-side
  diagnostics.
- Added no-cache and content-type security headers to V3 API responses.

### Documentation

- Added `docs/BENCHMARK_METHODOLOGY.md` with formulas, assumptions,
  reproducibility details, CARLA measurement requirements, and limitations.
- Archived historical validation snapshots so stale counts are no longer
  presented as current root-level results.

## [3.1.0] - 2026-07-18

### Added

- Official synthetic simulation mode that runs without CARLA.
- Clear CARLA-optional and synthetic-runtime-ready interface states.
- Complete Time Machine lifecycle recording:
  `DETECTED → MITIGATING → RECOVERING → RECOVERED`.
- Ghost digital-twin path prediction and collision-exposure estimates.
- Dynamic steering, throttle, and brake safety envelopes.
- Five-source threat-confidence fusion, explainable decisions, and Copilot
  responses.
- ECU integrity mapping with quarantine and virtual backup states.
- Protected/unprotected counterfactual benchmarking.
- Attack chains, adaptive attacker planning, and stealth attack mode.
- Recovery playbooks, incident storyboard, attack graph, Mission Control, and
  Scenario Director.
- Fleet Command Center, V2V threat sharing, OTA verification, and three-level
  JSON/PDF reports.
- Dashboard screenshot and regression/UI-contract coverage for synthetic mode.

### Changed

- Added `src/v3/advanced_features.py` as the lock-protected V3 orchestration
  layer.
- Added `src/v3/api.py` as the explicit V3 Flask blueprint.
- Added conditional dependency tracks for legacy Python 3.7/CARLA and modern
  Python/Docker development.
- Vendored dashboard libraries, fonts, and icons for offline operation.
- Upgraded GitHub Actions to Node.js 24-compatible action versions.

### Fixed

- Closed SQLite connections after polling to prevent leaked handles.

### Compatibility

- Preserved the stabilized simulation core and did not add new monkey patches
  to `SimulationEngine` or `carla_bridge.py`.
- Retained the legacy CARLA 0.9.13/Python 3.7 path alongside the modern runtime.

## [2.0.0]

### Added

- DriveFort AI identity assets and centralized brand configuration.
- Platform metadata and lifecycle data in snapshots.
- Health and configuration API endpoints.
- Regression coverage for critical dashboard controls.
- Configurable incident database and command secret.

### Changed

- Updated report/export names and titles to DriveFort AI.
- Adopted the deep navy, electric cyan, emerald, and silver dashboard palette.
- Moved historical root-level patch notes under `docs/legacy/`.

### Fixed

- Added a missing `time` import that had caused console actions to return HTTP
  500.
- Corrected invalid frontend identifiers introduced during the initial rebrand.
- Removed a duplicate unreachable return from a CARLA control helper.

### Compatibility

- Retained legacy lowercase API fields and method names during the V2
  transition.
