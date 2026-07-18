# Migration from ZoneGuard to DriveFort AI

## Public identity

| Previous | V2 |
|---|---|
| ZoneGuard EV | DriveFort AI |
| AI Cyber-Physical Defense | Secure Intelligence for Electric Mobility |
| Detect · Protect · Recover | Protect · Detect · Twin · Recover |
| zoneguard incident report | drivefort_ai incident report |

## Compatibility policy

The V2 UI, reports, documentation, configuration endpoints, and new state fields use DriveFort naming. A small number of lowercase legacy Python methods, JSON keys, CARLA role names, and environment fallbacks are retained to avoid breaking the current dashboard and CARLA integration during the refactor.

New clients should prefer:

- `drivefort_console` instead of `zoneguard_console`.
- `blocked_by_drivefort` instead of `blocked_by_zoneguard`.
- `DRIVEFORT_*` environment variables.

## Next refactor boundary

The next engineering phase will replace legacy monkey-patched engine behavior with explicit services for attacks, detection, digital-twin evaluation, defense, recovery, and evidence storage. Compatibility aliases can then be removed in a major-version release.
