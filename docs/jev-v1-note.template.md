# jev-v1 results note: Jev as an advisory critic under external governance

> Filled by `python -m jev_probe.note` from `results/jev-v1.slots.json`. Every number is a named slot; none is typed by hand. Full results: `results/jev-v1.md`. Registration: `prereg/jev-v1.md` (tag `prereg-jev-v1`).

## Claim

Jev (`{{run.requested_model}}`, returned as `{{run.model_versions}}`) read GIGO-Bench evidence as an advisory critic over {{run.n_calls}} cached calls on {{run.items_complete}} items, with run status {{run.status}}. With metadata in view it detected metadata-borne defects that the payload alone hides, but its scores were not calibrated probabilities. The results provide evidence that the SARC control boundary is not specific to generative LLMs: the same external-governance pattern applies to a typed probabilistic model such as Jev. The pattern is that the model advises and a deterministic gate decides.

## Invariant

Jev was an advisory critic. Its answers never admitted, blocked, repaired or substituted evidence. Predicates remain the gate.

## Results

Primary family, two-sided, Holm-adjusted over H1, H2 and H3.

| hypothesis | estimate | interval | Holm p | verdict |
|---|---|---|---|---|
| H1: metadata-borne detection above chance (PM) | d = {{H1.PM.pooled.d}} vs chance {{H1.PM.pooled.chance}}; difference {{H1.PM.pooled.estimate}} | [{{H1.PM.pooled.ci_lo}}, {{H1.PM.pooled.ci_hi}}] | {{H1.PM.pooled.p_adj}} | {{H1.PM.pooled.verdict}} |
| H2: calibration (PM, all questions) | Spiegelhalter Z = {{H2.PM.z}}; BSS = {{H2.PM.bss}} | BSS [{{H2.PM.bss_lo}}, {{H2.PM.bss_hi}}] | {{H2.PM.p_adj}} | {{H2.PM.verdict}} |
| H3: PM beats P on metadata-borne classes | PM {{H3.meta.pm_rate}} vs P {{H3.meta.p_rate}}; difference {{H3.meta.estimate}} (b = {{H3.meta.b}}, c = {{H3.meta.c}}) | [{{H3.meta.ci_lo}}, {{H3.meta.ci_hi}}] | {{H3.meta.p_adj}} | {{H3.meta.verdict}} |

H3 guard: the clean false-positive rate on `Q0_valid` moved from {{H3.meta.fpr_P}} (P) to {{H3.meta.fpr_PM}} (PM); guard {{H3.meta.guard}}.

Per-class detection, condition PM (majority of repeats, Wilson intervals). The predicate column is the deterministic baseline; `uncovered` means no constraint targets the class.

| class | channel | own class question = yes | `Q0_valid` = no | predicate |
|---|---|---|---|---|
| stale_master_data | metadata | {{detect.PM.stale_master_data.Q_stale_master_data.rate}} [{{detect.PM.stale_master_data.Q_stale_master_data.lo}}, {{detect.PM.stale_master_data.Q_stale_master_data.hi}}] ({{detect.PM.stale_master_data.Q_stale_master_data.k}}/{{detect.PM.stale_master_data.Q_stale_master_data.n}}) | {{detect.PM.stale_master_data.Q0_valid.rate}} [{{detect.PM.stale_master_data.Q0_valid.lo}}, {{detect.PM.stale_master_data.Q0_valid.hi}}] ({{detect.PM.stale_master_data.Q0_valid.k}}/{{detect.PM.stale_master_data.Q0_valid.n}}) | {{baseline.predicate.stale_master_data.Q_stale_master_data.rate}} |
| superseded_golden_record | metadata | {{detect.PM.superseded_golden_record.Q_superseded_golden_record.rate}} [{{detect.PM.superseded_golden_record.Q_superseded_golden_record.lo}}, {{detect.PM.superseded_golden_record.Q_superseded_golden_record.hi}}] ({{detect.PM.superseded_golden_record.Q_superseded_golden_record.k}}/{{detect.PM.superseded_golden_record.Q_superseded_golden_record.n}}) | {{detect.PM.superseded_golden_record.Q0_valid.rate}} [{{detect.PM.superseded_golden_record.Q0_valid.lo}}, {{detect.PM.superseded_golden_record.Q0_valid.hi}}] ({{detect.PM.superseded_golden_record.Q0_valid.k}}/{{detect.PM.superseded_golden_record.Q0_valid.n}}) | {{baseline.predicate.superseded_golden_record.Q_superseded_golden_record.rate}} |
| silent_unit_change | metadata | {{detect.PM.silent_unit_change.Q_silent_unit_change.rate}} [{{detect.PM.silent_unit_change.Q_silent_unit_change.lo}}, {{detect.PM.silent_unit_change.Q_silent_unit_change.hi}}] ({{detect.PM.silent_unit_change.Q_silent_unit_change.k}}/{{detect.PM.silent_unit_change.Q_silent_unit_change.n}}) | {{detect.PM.silent_unit_change.Q0_valid.rate}} [{{detect.PM.silent_unit_change.Q0_valid.lo}}, {{detect.PM.silent_unit_change.Q0_valid.hi}}] ({{detect.PM.silent_unit_change.Q0_valid.k}}/{{detect.PM.silent_unit_change.Q0_valid.n}}) | {{baseline.predicate.silent_unit_change.Q_silent_unit_change.rate}} |
| plausible_outlier | metadata | {{detect.PM.plausible_outlier.Q_plausible_outlier.rate}} [{{detect.PM.plausible_outlier.Q_plausible_outlier.lo}}, {{detect.PM.plausible_outlier.Q_plausible_outlier.hi}}] ({{detect.PM.plausible_outlier.Q_plausible_outlier.k}}/{{detect.PM.plausible_outlier.Q_plausible_outlier.n}}) | {{detect.PM.plausible_outlier.Q0_valid.rate}} [{{detect.PM.plausible_outlier.Q0_valid.lo}}, {{detect.PM.plausible_outlier.Q0_valid.hi}}] ({{detect.PM.plausible_outlier.Q0_valid.k}}/{{detect.PM.plausible_outlier.Q0_valid.n}}) | {{baseline.predicate.plausible_outlier.Q_plausible_outlier.rate}} |
| duplicate_vendor_conflicting_terms | payload | {{detect.PM.duplicate_vendor_conflicting_terms.Q_duplicate_vendor_conflicting_terms.rate}} [{{detect.PM.duplicate_vendor_conflicting_terms.Q_duplicate_vendor_conflicting_terms.lo}}, {{detect.PM.duplicate_vendor_conflicting_terms.Q_duplicate_vendor_conflicting_terms.hi}}] ({{detect.PM.duplicate_vendor_conflicting_terms.Q_duplicate_vendor_conflicting_terms.k}}/{{detect.PM.duplicate_vendor_conflicting_terms.Q_duplicate_vendor_conflicting_terms.n}}) | {{detect.PM.duplicate_vendor_conflicting_terms.Q0_valid.rate}} [{{detect.PM.duplicate_vendor_conflicting_terms.Q0_valid.lo}}, {{detect.PM.duplicate_vendor_conflicting_terms.Q0_valid.hi}}] ({{detect.PM.duplicate_vendor_conflicting_terms.Q0_valid.k}}/{{detect.PM.duplicate_vendor_conflicting_terms.Q0_valid.n}}) | {{baseline.predicate.duplicate_vendor_conflicting_terms.Q_duplicate_vendor_conflicting_terms.rate}} |
| cross_source_contradiction | payload | {{detect.PM.cross_source_contradiction.Q_cross_source_contradiction.rate}} [{{detect.PM.cross_source_contradiction.Q_cross_source_contradiction.lo}}, {{detect.PM.cross_source_contradiction.Q_cross_source_contradiction.hi}}] ({{detect.PM.cross_source_contradiction.Q_cross_source_contradiction.k}}/{{detect.PM.cross_source_contradiction.Q_cross_source_contradiction.n}}) | {{detect.PM.cross_source_contradiction.Q0_valid.rate}} [{{detect.PM.cross_source_contradiction.Q0_valid.lo}}, {{detect.PM.cross_source_contradiction.Q0_valid.hi}}] ({{detect.PM.cross_source_contradiction.Q0_valid.k}}/{{detect.PM.cross_source_contradiction.Q0_valid.n}}) | {{baseline.predicate.cross_source_contradiction.Q_cross_source_contradiction.rate}} |
| schema_drift | payload | {{detect.PM.schema_drift.Q_schema_drift.rate}} [{{detect.PM.schema_drift.Q_schema_drift.lo}}, {{detect.PM.schema_drift.Q_schema_drift.hi}}] ({{detect.PM.schema_drift.Q_schema_drift.k}}/{{detect.PM.schema_drift.Q_schema_drift.n}}) | {{detect.PM.schema_drift.Q0_valid.rate}} [{{detect.PM.schema_drift.Q0_valid.lo}}, {{detect.PM.schema_drift.Q0_valid.hi}}] ({{detect.PM.schema_drift.Q0_valid.k}}/{{detect.PM.schema_drift.Q0_valid.n}}) | {{baseline.predicate.schema_drift.Q_schema_drift.rate}} |
| missing_mandatory_field | payload | {{detect.PM.missing_mandatory_field.Q_missing_mandatory_field.rate}} [{{detect.PM.missing_mandatory_field.Q_missing_mandatory_field.lo}}, {{detect.PM.missing_mandatory_field.Q_missing_mandatory_field.hi}}] ({{detect.PM.missing_mandatory_field.Q_missing_mandatory_field.k}}/{{detect.PM.missing_mandatory_field.Q_missing_mandatory_field.n}}) | {{detect.PM.missing_mandatory_field.Q0_valid.rate}} [{{detect.PM.missing_mandatory_field.Q0_valid.lo}}, {{detect.PM.missing_mandatory_field.Q0_valid.hi}}] ({{detect.PM.missing_mandatory_field.Q0_valid.k}}/{{detect.PM.missing_mandatory_field.Q0_valid.n}}) | {{baseline.predicate.missing_mandatory_field.Q_missing_mandatory_field.rate}} |

Clean false-positive rates ({{fpr.PM.Q0_valid.n}} clean items):

| question | P | PM | predicate |
|---|---|---|---|
| `Q0_valid` majority no | {{fpr.P.Q0_valid.rate}} [{{fpr.P.Q0_valid.lo}}, {{fpr.P.Q0_valid.hi}}] ({{fpr.P.Q0_valid.k}}/{{fpr.P.Q0_valid.n}}) | {{fpr.PM.Q0_valid.rate}} [{{fpr.PM.Q0_valid.lo}}, {{fpr.PM.Q0_valid.hi}}] ({{fpr.PM.Q0_valid.k}}/{{fpr.PM.Q0_valid.n}}) | {{baseline.predicate.fpr.Q0_valid.rate}} |
| `Q_missing_mandatory_field` majority yes | {{fpr.P.Q_missing_mandatory_field.rate}} [{{fpr.P.Q_missing_mandatory_field.lo}}, {{fpr.P.Q_missing_mandatory_field.hi}}] ({{fpr.P.Q_missing_mandatory_field.k}}/{{fpr.P.Q_missing_mandatory_field.n}}) | {{fpr.PM.Q_missing_mandatory_field.rate}} [{{fpr.PM.Q_missing_mandatory_field.lo}}, {{fpr.PM.Q_missing_mandatory_field.hi}}] ({{fpr.PM.Q_missing_mandatory_field.k}}/{{fpr.PM.Q_missing_mandatory_field.n}}) | {{baseline.predicate.fpr.Q_missing_mandatory_field.rate}} |
| any class question majority yes | {{fpr.P.any_class.rate}} [{{fpr.P.any_class.lo}}, {{fpr.P.any_class.hi}}] ({{fpr.P.any_class.k}}/{{fpr.P.any_class.n}}) | {{fpr.PM.any_class.rate}} [{{fpr.PM.any_class.lo}}, {{fpr.PM.any_class.hi}}] ({{fpr.PM.any_class.k}}/{{fpr.PM.any_class.n}}) | |

Cost and latency. Total spend USD {{cost.total.usd}} for {{cost.total.input_tokens}} input tokens (USD {{cost.total.usd_per_call}} per call, USD {{cost.total.usd_per_item}} per item), at USD {{cost.price_usd_per_1e9_input}} per billion input tokens with output free. Latency per call including backoff: median {{latency.P.call.median}} s and p90 {{latency.P.call.p90}} s in P; median {{latency.PM.call.median}} s and p90 {{latency.PM.call.p90}} s in PM. Adapter retries: {{run.n_retries}}. Invalid answer rate: {{invalid.P}} (P), {{invalid.PM}} (PM).

## Limitations

(a) Condition P showed a three-field payload with no schema declared. The P false-positive rates on `Q_missing_mandatory_field` ({{fpr.P.Q_missing_mandatory_field.rate}}) and `Q0_valid` ({{fpr.P.Q0_valid.rate}}) are therefore a probe design limit, not a property of the model: without a declared schema, "mandatory" and "valid" have no reference.

(b) In PM, Jev judged all {{detect.PM.schema_drift.Q0_valid.n}} schema-drift records valid to act on (`Q0_valid` = no on {{detect.PM.schema_drift.Q0_valid.k}} of {{detect.PM.schema_drift.Q0_valid.n}}; `Q_schema_drift` = yes on {{detect.PM.schema_drift.Q_schema_drift.k}} of {{detect.PM.schema_drift.Q_schema_drift.n}}). The predicate baseline detected this class at {{baseline.predicate.schema_drift.Q_schema_drift.rate}}.

## Calibration consequence

H2 was {{H2.PM.verdict}}, so a Jev score is a score, not a probability. Any downstream use must set an admission threshold τ empirically on a held-out split with a stated false-positive ceiling, and the gate consumes true / false / unknown, never the raw score. The threshold is a property of the deployment, fixed before the test data are seen; the score itself carries no licence to act.

## Taxonomy of Jev tests

- SARC-DQ: is the evidence fit to use?
- Authority Derivation: what must the gate observe?
- SARC: given those observations, what action is authorised?
- Green SARC: are the resource consequences of the action and its control path acceptable?
