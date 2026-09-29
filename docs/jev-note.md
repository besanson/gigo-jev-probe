# Jev under external governance: results of jev-v1, jev-v2 and jev-v3

> Filled by `python -m jev_probe.note_all` from `results/jev-v1.slots.json`, `results/jev-v2.slots.json`, `results/jev-v3.slots.json` and `results/jev-v2-exploratory.slots.json`. Every result is a named slot; none is typed by hand. The only literal figures are registered design parameters (noise levels and the false-positive ceiling).

Across two sensors, three noise levels and 4200 test verdicts, the admission policy never mapped a sensing error from deny to allow (0 of 4200). Every verdict change was fail-closed.

## Claim

The results provide evidence that the SARC control boundary is not specific to generative LLMs: the same external-governance pattern applies to a typed probabilistic model such as Jev.

## Invariant

Sensors write observations, never verdicts. An admission threshold set on a held-out split at a 1% false-positive ceiling maps each score to true, false or unknown, and unknown denies. Authority stays with the deterministic contract.

## jev-v1: advisory critic on GIGO-Bench

Jev (`jev-latest`, returned as `jev-1.13.0`) answered typed questions about GIGO-Bench evidence over 1800 cached calls on 300 items (status COMPLETE). Primary family, two-sided, Holm-adjusted over H1, H2 and H3.

| hypothesis | estimate | interval | Holm p | verdict |
|---|---|---|---|---|
| H1: metadata-borne detection above chance (PM) | d = 0.5000 vs chance 0.0000 | [0.4000, 0.6000] | 1.00e-04 | supported: detection above chance |
| H2: calibration (PM, all questions) | Spiegelhalter Z = -15.0268; BSS = 0.0447 | BSS [-0.0044, 0.0860] | 1.47e-50 | refuted |
| H3: PM beats P on metadata-borne classes | PM 0.5000 vs P 0.0000 (b = 50, c = 0) | [0.4000, 0.6000] | 3.55e-15 | supported: PM detects more than P |

Per-class detection in condition PM (majority of repeats); the predicate column is the deterministic baseline.

| class | channel | own class question = yes | `Q0_valid` = no | predicate |
|---|---|---|---|---|
| stale_master_data | metadata | 1.0000 (25/25) | 1.0000 (25/25) | 1.0000 |
| superseded_golden_record | metadata | 1.0000 (25/25) | 1.0000 (25/25) | 1.0000 |
| silent_unit_change | metadata | 0.0000 (0/25) | 0.0800 (2/25) | uncovered |
| plausible_outlier | metadata | 0.0000 (0/25) | 0.0000 (0/25) | uncovered |
| duplicate_vendor_conflicting_terms | payload | 0.0000 (0/25) | 1.0000 (25/25) | uncovered |
| cross_source_contradiction | payload | 1.0000 (25/25) | 1.0000 (25/25) | 1.0000 |
| schema_drift | payload | 0.0000 (0/25) | 0.0000 (0/25) | 1.0000 |
| missing_mandatory_field | payload | 1.0000 (25/25) | 1.0000 (25/25) | 1.0000 |

Clean false-positive rates (100 clean items): `Q0_valid` majority no, P 0.8300 and PM 0.0900 (predicate 0.0000); `Q_missing_mandatory_field` majority yes, P 1.0000 and PM 0.0000 (predicate 0.0000); any class question majority yes, P 1.0000 and PM 0.0000.

Cost: USD 0.045017 in total for 1071825 input tokens (USD 0.00015006 per item).

Limitations, as stated in the jev-v1 note:

(a) Condition P showed a three-field payload with no schema declared. The P false-positive rates on `Q_missing_mandatory_field` (1.0000) and `Q0_valid` (0.8300) are therefore a probe design limit, not a property of the model: without a declared schema, "mandatory" and "valid" have no reference.

(b) In PM, Jev judged all 25 schema-drift records valid to act on (`Q0_valid` = no on 0 of 25; `Q_schema_drift` = yes on 0 of 25). The predicate baseline detected this class at 1.0000.

## jev-v2 and jev-v3: semantic sensor on the CH-B1 field

Each sensor read a change-management record and proposed a value for `approval_token`; the score passed through the frozen thresholds and the sibling's loss predicates computed the verdict. Arm A (Jev) ran in jev-v2; arm B (Claude Haiku 4.5) is the registered jev-v3 re-run. Test split, Clopper-Pearson 95% intervals.

| sensor | noise | verdict-change rate | unsafe (deny to allow) | fail-closed (allow to deny) | abstention |
|---|---|---|---|---|---|
| Jev (jev-v2) | 0% | 0.0000 [0.0000, 0.0053] (0/700) | 0/700 | 0/700 | 0.0000 |
| Jev (jev-v2) | 10% | 0.0286 [0.0175, 0.0438] (20/700) | 0/700 | 20/700 | 0.0814 |
| Jev (jev-v2) | 30% | 0.0971 [0.0762, 0.1215] (68/700) | 0/700 | 68/700 | 0.2657 |
| Haiku (jev-v3) | 0% | 0.1171 [0.0943, 0.1433] (82/700) | 0/700 | 82/700 | 0.2886 |
| Haiku (jev-v3) | 10% | 0.1429 [0.1178, 0.1710] (100/700) | 0/700 | 100/700 | 0.3614 |
| Haiku (jev-v3) | 30% | 0.2014 [0.1723, 0.2331] (141/700) | 0/700 | 141/700 | 0.5100 |

| hypothesis | source | estimate | 95% CI | Holm-adjusted p | verdict |
|---|---|---|---|---|---|
| H1: Jev verdict-change rate at 0% noise below the registered bound | jev-v2 | 0.0000 (0/700) | [0.0000, 0.0053] | 2.36e-06 | supported: below the 2% bound |
| H2: Jev not worse than Haiku at 30% noise | jev-v3 | Jev 0.0971 vs Haiku 0.2014; difference -0.1043 (b = 0, c = 73) | [-0.1271, -0.0829] | 4.24e-22 | supported: Jev better |
| H3: Jev cost per verdict below Haiku | jev-v3 | USD 0.00001730 vs USD 0.00025781 | [-0.00024099, -0.00024003] | 1.00e-04 | supported: Jev cheaper |

H1 is Holm-adjusted within the jev-v2 family; H2 and H3 within the jev-v3 family of two.

Frozen thresholds: Jev τ_true = 0.4900 and τ_false = 0.0500 (jev-v2 validation split); Haiku τ_true = 0.9200 and τ_false = 0.0500 (jev-v3 validation split, 900 of 900 records scored).

## Record of the LLM arm

In jev-v2, Haiku wrapped every reply in a Markdown code fence and the registered bare-JSON parser scored 3000 of 3000 records invalid (rate 1.0000), so its τ_true fell back to inf and every reading denied (known issue KI-1 in `prereg/DEVIATIONS.md`). jev-v3 re-ran that arm under a registered request fix and an arm health check, with 0 invalid records.

| Haiku verdict-change rate at 30% noise | value |
|---|---|
| jev-v2 exploratory lenient re-score (post hoc; different request configuration; the registered number is jev-v3) | 0.1357 (95/700) |
| jev-v3 registered | 0.2014 (141/700) |

## Caveats

(a) Haiku's threshold τ_true = 0.9200 was forced by the 1% false-positive ceiling on a compressed score distribution; 'Jev better' means Jev's scores separate better under that ceiling, not that Haiku cannot read a record.

(b) All corpora are constructed. No prevalence claim is made.

## Standing rule

Every registration from jev-v3 onward includes an arm health check with a hard stop before the test split.

## Pointers

- Registrations: `prereg/jev-v1.md` (tag `prereg-jev-v1`), `prereg/jev-v2.md` (tag `prereg-jev-v2-reg`), `prereg/jev-v3.md` (tag `prereg-jev-v3`); departures in `prereg/DEVIATIONS.md`.
- Raw-response caches: `responses/jev-v1.jsonl`, `responses/jev-v2.jsonl`, `responses/jev-v3.jsonl`, with their run manifests.
- Full results: `results/jev-v1.md`, `results/jev-v2.md`, `results/jev-v3.md`, and the exploratory `results/jev-v2-exploratory.md`.
- Regenerate from the caches, with no model call: `python -m jev_probe.analysis`, `python -m jev_probe.analysis_v2`, `python -m jev_probe.exploratory_v2`, `python -m jev_probe.analysis_v3`, then `python -m jev_probe.note_all`.
