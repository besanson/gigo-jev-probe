# jev-v1 results note: Jev as an advisory critic under external governance

> Filled by `python -m jev_probe.note` from `results/jev-v1.slots.json`. Every number is a named slot; none is typed by hand. Full results: `results/jev-v1.md`. Registration: `prereg/jev-v1.md` (tag `prereg-jev-v1`).

## Claim

Jev (`jev-latest`, returned as `jev-1.13.0`) read GIGO-Bench evidence as an advisory critic over 1800 cached calls on 300 items, with run status COMPLETE. With metadata in view it detected metadata-borne defects that the payload alone hides, but its scores were not calibrated probabilities. The results provide evidence that the SARC control boundary is not specific to generative LLMs: the same external-governance pattern applies to a typed probabilistic model such as Jev. The pattern is that the model advises and a deterministic gate decides.

## Invariant

Jev was an advisory critic. Its answers never admitted, blocked, repaired or substituted evidence. Predicates remain the gate.

## Results

Primary family, two-sided, Holm-adjusted over H1, H2 and H3.

| hypothesis | estimate | interval | Holm p | verdict |
|---|---|---|---|---|
| H1: metadata-borne detection above chance (PM) | d = 0.5000 vs chance 0.0000; difference 0.5000 | [0.4000, 0.6000] | 1.00e-04 | supported: detection above chance |
| H2: calibration (PM, all questions) | Spiegelhalter Z = -15.0268; BSS = 0.0447 | BSS [-0.0044, 0.0860] | 1.47e-50 | refuted |
| H3: PM beats P on metadata-borne classes | PM 0.5000 vs P 0.0000; difference 0.5000 (b = 50, c = 0) | [0.4000, 0.6000] | 3.55e-15 | supported: PM detects more than P |

H3 guard: the clean false-positive rate on `Q0_valid` moved from 0.8300 (P) to 0.0900 (PM); guard not tripped.

Per-class detection, condition PM (majority of repeats, Wilson intervals). The predicate column is the deterministic baseline; `uncovered` means no constraint targets the class.

| class | channel | own class question = yes | `Q0_valid` = no | predicate |
|---|---|---|---|---|
| stale_master_data | metadata | 1.0000 [0.8668, 1.0000] (25/25) | 1.0000 [0.8668, 1.0000] (25/25) | 1.0000 |
| superseded_golden_record | metadata | 1.0000 [0.8668, 1.0000] (25/25) | 1.0000 [0.8668, 1.0000] (25/25) | 1.0000 |
| silent_unit_change | metadata | 0.0000 [0.0000, 0.1332] (0/25) | 0.0800 [0.0222, 0.2497] (2/25) | uncovered |
| plausible_outlier | metadata | 0.0000 [0.0000, 0.1332] (0/25) | 0.0000 [0.0000, 0.1332] (0/25) | uncovered |
| duplicate_vendor_conflicting_terms | payload | 0.0000 [0.0000, 0.1332] (0/25) | 1.0000 [0.8668, 1.0000] (25/25) | uncovered |
| cross_source_contradiction | payload | 1.0000 [0.8668, 1.0000] (25/25) | 1.0000 [0.8668, 1.0000] (25/25) | 1.0000 |
| schema_drift | payload | 0.0000 [0.0000, 0.1332] (0/25) | 0.0000 [0.0000, 0.1332] (0/25) | 1.0000 |
| missing_mandatory_field | payload | 1.0000 [0.8668, 1.0000] (25/25) | 1.0000 [0.8668, 1.0000] (25/25) | 1.0000 |

Clean false-positive rates (100 clean items):

| question | P | PM | predicate |
|---|---|---|---|
| `Q0_valid` majority no | 0.8300 [0.7445, 0.8911] (83/100) | 0.0900 [0.0481, 0.1623] (9/100) | 0.0000 |
| `Q_missing_mandatory_field` majority yes | 1.0000 [0.9630, 1.0000] (100/100) | 0.0000 [0.0000, 0.0370] (0/100) | 0.0000 |
| any class question majority yes | 1.0000 [0.9630, 1.0000] (100/100) | 0.0000 [0.0000, 0.0370] (0/100) | |

Cost and latency. Total spend USD 0.045017 for 1071825 input tokens (USD 0.00002501 per call, USD 0.00015006 per item), at USD 42.00 per billion input tokens with output free. Latency per call including backoff: median 0.195 s and p90 0.232 s in P; median 0.195 s and p90 0.234 s in PM. Adapter retries: 0. Invalid answer rate: 0.0000 (P), 0.0000 (PM).

## Limitations

(a) Condition P showed a three-field payload with no schema declared. The P false-positive rates on `Q_missing_mandatory_field` (1.0000) and `Q0_valid` (0.8300) are therefore a probe design limit, not a property of the model: without a declared schema, "mandatory" and "valid" have no reference.

(b) In PM, Jev judged all 25 schema-drift records valid to act on (`Q0_valid` = no on 0 of 25; `Q_schema_drift` = yes on 0 of 25). The predicate baseline detected this class at 1.0000.

## Calibration consequence

H2 was refuted, so a Jev score is a score, not a probability. Any downstream use must set an admission threshold τ empirically on a held-out split with a stated false-positive ceiling, and the gate consumes true / false / unknown, never the raw score. The threshold is a property of the deployment, fixed before the test data are seen; the score itself carries no licence to act.

## Taxonomy of Jev tests

- SARC-DQ: is the evidence fit to use?
- Authority Derivation: what must the gate observe?
- SARC: given those observations, what action is authorised?
- Green SARC: are the resource consequences of the action and its control path acceptable?
