# DriveFort AI V3 Benchmark Methodology

## Evidence categories

DriveFort V3 uses two distinct benchmark sources:

| Source | `source` | `measured` | Meaning |
|---|---|---:|---|
| Analytical counterfactual model | `synthetic` | `false` | Deterministic estimates produced from documented formulas. No simulator telemetry is measured. |
| Instrumented CARLA run | `carla` | `true` | Metrics derived from recorded CARLA timestamps, vehicle transforms, controls, and ECU/security events. |

The current `POST /api/v3/benchmark/run` endpoint produces only synthetic
analytical estimates. Collision probability, lateral deviation, detection
latency, stabilization time, and trust loss from this endpoint must not be
described as observed or measured CARLA results.

Every completed benchmark includes:

- `source`: `synthetic` or `carla`
- `measured`: whether metrics came from simulator observations
- `model_version`: the analytical model or measurement-pipeline version
- `scenario_id`: stable identifier for the scenario inputs
- `scenario_seed`: deterministic seed for synthetic reproducibility
- `generated_at`: creation time
- `metadata.metric_semantics`: explicit estimate/measurement label
- `evidence`: normalized attack, intensity, latency, deviation,
  stabilization, trust-loss, and outcome fields

Existing `unprotected`, `protected`, `improvement`, and `replay` fields
remain available for backward compatibility.

## Synthetic counterfactual model

Model version: `synthetic-counterfactual-v1.0`.

Let:

- `I` be the requested attack intensity, clamped to `[0.05, 1.0]`.
- `A` be the attack severity coefficient from `ATTACK_SEVERITY`.
- `S = A × I` be the scenario severity.

The model computes the following estimates.

### Unprotected outcome

- Maximum lateral deviation (m): `0.8 + 3.4S`
- Collision probability (%): `min(99, 38 + 61S)`
- ECU trust loss (%): `42 + 51S`
- Detection latency: unavailable because no defense is modeled
- Stabilization time: unavailable because no recovery is modeled
- Outcome: `COLLISION LIKELY` when `S >= 0.72`; otherwise
  `UNSAFE DEVIATION`

### Protected outcome

- Detection latency (ms): `round(145 + 210(1 - S))`
- Maximum lateral deviation (m): `max(0.12, 0.62 - 0.22S)`
- Collision probability (%): `max(1.8, 16 - 9S)`
- Stabilization time (s): `0.9 + 1.15S`
- ECU trust loss (%): `8 + 14S`
- Outcome: `CONTAINED`

### Improvement fields

- Deviation reduction (%):
  `(1 - protected_deviation / unprotected_deviation) × 100`
- Collision-risk reduction (percentage points):
  `unprotected_probability - protected_probability`
- Trust preserved (percentage points):
  `unprotected_trust_loss - protected_trust_loss`

Rounding follows the API implementation: deviations and stabilization time use
two decimals; percentages generally use one decimal.

## Reproducibility

Synthetic results do not currently use random sampling. A deterministic seed is
still assigned so future stochastic extensions can reproduce the same scenario.
The seed is the first 32 bits of SHA-256 over:

```text
attack_type | intensity_to_four_decimals | model_version
```

The `scenario_id` combines the attack type and hexadecimal seed. Repeating the
same attack, intensity, and model version therefore yields the same scenario ID,
seed, estimates, evidence, and replay. Only `generated_at` changes.

## CARLA measurement requirements

A future result may use `source: carla` and `measured: true` only when an
instrumented run records enough evidence to calculate:

1. attack injection timestamp and attack parameters;
2. defense detection timestamp;
3. vehicle transform/lane displacement over the complete scenario;
4. recovery/stable-state timestamp and stability criteria;
5. ECU trust values before, during, and after the attack;
6. protected or unprotected configuration and final outcome;
7. CARLA version, map, vehicle, sensors, synchronous-mode settings, fixed delta,
   weather, traffic, and scenario seed.

Detection latency is the elapsed time from injection to the first qualifying
defense detection. Maximum deviation is the maximum observed displacement from
the defined reference trajectory. Stabilization time is measured from detection
or mitigation start to the documented stable-state threshold. Trust loss is the
difference between baseline and minimum recorded trust.

CARLA measurements should be repeated across multiple seeds and report sample
count and dispersion. A single run is evidence for that run, not a general
safety guarantee.

## Limitations

- Synthetic results are comparative analytical estimates, not physical proof.
- The formulas intentionally simplify vehicle dynamics, environmental
  conditions, sensor noise, traffic, and actuator latency.
- Estimated collision probability is a model output, not a calibrated real-world
  crash probability.
- Live CARLA validation requires the repository's supported CARLA 0.9.13 and
  legacy Python 3.7 compatibility path.
- Real-vehicle safety claims require separate controlled testing, calibrated
  instrumentation, and an appropriate safety assurance process.
