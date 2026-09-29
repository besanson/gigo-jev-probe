# Jev under external governance: results of jev-v1, jev-v2 and jev-v3

> Filled by `python -m jev_probe.note_all` from `results/jev-v1.slots.json`, `results/jev-v2.slots.json`, `results/jev-v3.slots.json` and `results/jev-v2-exploratory.slots.json`. Every result is a named slot; none is typed by hand. The only literal figures are registered design parameters (noise levels and the false-positive ceiling).

Across two sensors, three noise levels and {{n_verdicts_total}} test verdicts, the admission policy never mapped a sensing error from deny to allow ({{unsafe_total}} of {{n_verdicts_total}}). Every verdict change was fail-closed.

## Claim

The results provide evidence that the SARC control boundary is not specific to generative LLMs: the same external-governance pattern applies to a typed probabilistic model such as Jev.

## Invariant

Sensors write observations, never verdicts. An admission threshold set on a held-out split at a 1% false-positive ceiling maps each score to true, false or unknown, and unknown denies. Authority stays with the deterministic contract.

## jev-v1: advisory critic on GIGO-Bench

Jev (`{{v1.run.requested_model}}`, returned as `{{v1.run.model_versions}}`) answered typed questions about GIGO-Bench evidence over {{v1.run.n_calls}} cached calls on {{v1.run.items_complete}} items (status {{v1.run.status}}). Primary family, two-sided, Holm-adjusted over H1, H2 and H3.

| hypothesis | estimate | interval | Holm p | verdict |
|---|---|---|---|---|
| H1: metadata-borne detection above chance (PM) | d = {{v1.H1.PM.pooled.d}} vs chance {{v1.H1.PM.pooled.chance}} | [{{v1.H1.PM.pooled.ci_lo}}, {{v1.H1.PM.pooled.ci_hi}}] | {{v1.H1.PM.pooled.p_adj}} | {{v1.H1.PM.pooled.verdict}} |
| H2: calibration (PM, all questions) | Spiegelhalter Z = {{v1.H2.PM.z}}; BSS = {{v1.H2.PM.bss}} | BSS [{{v1.H2.PM.bss_lo}}, {{v1.H2.PM.bss_hi}}] | {{v1.H2.PM.p_adj}} | {{v1.H2.PM.verdict}} |
| H3: PM beats P on metadata-borne classes | PM {{v1.H3.meta.pm_rate}} vs P {{v1.H3.meta.p_rate}} (b = {{v1.H3.meta.b}}, c = {{v1.H3.meta.c}}) | [{{v1.H3.meta.ci_lo}}, {{v1.H3.meta.ci_hi}}] | {{v1.H3.meta.p_adj}} | {{v1.H3.meta.verdict}} |

Per-class detection in condition PM (majority of repeats); the predicate column is the deterministic baseline.

| class | channel | own class question = yes | `Q0_valid` = no | predicate |
|---|---|---|---|---|
| stale_master_data | metadata | {{v1.detect.PM.stale_master_data.Q_stale_master_data.rate}} ({{v1.detect.PM.stale_master_data.Q_stale_master_data.k}}/{{v1.detect.PM.stale_master_data.Q_stale_master_data.n}}) | {{v1.detect.PM.stale_master_data.Q0_valid.rate}} ({{v1.detect.PM.stale_master_data.Q0_valid.k}}/{{v1.detect.PM.stale_master_data.Q0_valid.n}}) | {{v1.baseline.predicate.stale_master_data.Q_stale_master_data.rate}} |
| superseded_golden_record | metadata | {{v1.detect.PM.superseded_golden_record.Q_superseded_golden_record.rate}} ({{v1.detect.PM.superseded_golden_record.Q_superseded_golden_record.k}}/{{v1.detect.PM.superseded_golden_record.Q_superseded_golden_record.n}}) | {{v1.detect.PM.superseded_golden_record.Q0_valid.rate}} ({{v1.detect.PM.superseded_golden_record.Q0_valid.k}}/{{v1.detect.PM.superseded_golden_record.Q0_valid.n}}) | {{v1.baseline.predicate.superseded_golden_record.Q_superseded_golden_record.rate}} |
| silent_unit_change | metadata | {{v1.detect.PM.silent_unit_change.Q_silent_unit_change.rate}} ({{v1.detect.PM.silent_unit_change.Q_silent_unit_change.k}}/{{v1.detect.PM.silent_unit_change.Q_silent_unit_change.n}}) | {{v1.detect.PM.silent_unit_change.Q0_valid.rate}} ({{v1.detect.PM.silent_unit_change.Q0_valid.k}}/{{v1.detect.PM.silent_unit_change.Q0_valid.n}}) | {{v1.baseline.predicate.silent_unit_change.Q_silent_unit_change.rate}} |
| plausible_outlier | metadata | {{v1.detect.PM.plausible_outlier.Q_plausible_outlier.rate}} ({{v1.detect.PM.plausible_outlier.Q_plausible_outlier.k}}/{{v1.detect.PM.plausible_outlier.Q_plausible_outlier.n}}) | {{v1.detect.PM.plausible_outlier.Q0_valid.rate}} ({{v1.detect.PM.plausible_outlier.Q0_valid.k}}/{{v1.detect.PM.plausible_outlier.Q0_valid.n}}) | {{v1.baseline.predicate.plausible_outlier.Q_plausible_outlier.rate}} |
| duplicate_vendor_conflicting_terms | payload | {{v1.detect.PM.duplicate_vendor_conflicting_terms.Q_duplicate_vendor_conflicting_terms.rate}} ({{v1.detect.PM.duplicate_vendor_conflicting_terms.Q_duplicate_vendor_conflicting_terms.k}}/{{v1.detect.PM.duplicate_vendor_conflicting_terms.Q_duplicate_vendor_conflicting_terms.n}}) | {{v1.detect.PM.duplicate_vendor_conflicting_terms.Q0_valid.rate}} ({{v1.detect.PM.duplicate_vendor_conflicting_terms.Q0_valid.k}}/{{v1.detect.PM.duplicate_vendor_conflicting_terms.Q0_valid.n}}) | {{v1.baseline.predicate.duplicate_vendor_conflicting_terms.Q_duplicate_vendor_conflicting_terms.rate}} |
| cross_source_contradiction | payload | {{v1.detect.PM.cross_source_contradiction.Q_cross_source_contradiction.rate}} ({{v1.detect.PM.cross_source_contradiction.Q_cross_source_contradiction.k}}/{{v1.detect.PM.cross_source_contradiction.Q_cross_source_contradiction.n}}) | {{v1.detect.PM.cross_source_contradiction.Q0_valid.rate}} ({{v1.detect.PM.cross_source_contradiction.Q0_valid.k}}/{{v1.detect.PM.cross_source_contradiction.Q0_valid.n}}) | {{v1.baseline.predicate.cross_source_contradiction.Q_cross_source_contradiction.rate}} |
| schema_drift | payload | {{v1.detect.PM.schema_drift.Q_schema_drift.rate}} ({{v1.detect.PM.schema_drift.Q_schema_drift.k}}/{{v1.detect.PM.schema_drift.Q_schema_drift.n}}) | {{v1.detect.PM.schema_drift.Q0_valid.rate}} ({{v1.detect.PM.schema_drift.Q0_valid.k}}/{{v1.detect.PM.schema_drift.Q0_valid.n}}) | {{v1.baseline.predicate.schema_drift.Q_schema_drift.rate}} |
| missing_mandatory_field | payload | {{v1.detect.PM.missing_mandatory_field.Q_missing_mandatory_field.rate}} ({{v1.detect.PM.missing_mandatory_field.Q_missing_mandatory_field.k}}/{{v1.detect.PM.missing_mandatory_field.Q_missing_mandatory_field.n}}) | {{v1.detect.PM.missing_mandatory_field.Q0_valid.rate}} ({{v1.detect.PM.missing_mandatory_field.Q0_valid.k}}/{{v1.detect.PM.missing_mandatory_field.Q0_valid.n}}) | {{v1.baseline.predicate.missing_mandatory_field.Q_missing_mandatory_field.rate}} |

Clean false-positive rates ({{v1.fpr.PM.Q0_valid.n}} clean items): `Q0_valid` majority no, P {{v1.fpr.P.Q0_valid.rate}} and PM {{v1.fpr.PM.Q0_valid.rate}} (predicate {{v1.baseline.predicate.fpr.Q0_valid.rate}}); `Q_missing_mandatory_field` majority yes, P {{v1.fpr.P.Q_missing_mandatory_field.rate}} and PM {{v1.fpr.PM.Q_missing_mandatory_field.rate}} (predicate {{v1.baseline.predicate.fpr.Q_missing_mandatory_field.rate}}); any class question majority yes, P {{v1.fpr.P.any_class.rate}} and PM {{v1.fpr.PM.any_class.rate}}.

Cost: USD {{v1.cost.total.usd}} in total for {{v1.cost.total.input_tokens}} input tokens (USD {{v1.cost.total.usd_per_item}} per item).

Limitations, as stated in the jev-v1 note:

(a) Condition P showed a three-field payload with no schema declared. The P false-positive rates on `Q_missing_mandatory_field` ({{v1.fpr.P.Q_missing_mandatory_field.rate}}) and `Q0_valid` ({{v1.fpr.P.Q0_valid.rate}}) are therefore a probe design limit, not a property of the model: without a declared schema, "mandatory" and "valid" have no reference.

(b) In PM, Jev judged all {{v1.detect.PM.schema_drift.Q0_valid.n}} schema-drift records valid to act on (`Q0_valid` = no on {{v1.detect.PM.schema_drift.Q0_valid.k}} of {{v1.detect.PM.schema_drift.Q0_valid.n}}; `Q_schema_drift` = yes on {{v1.detect.PM.schema_drift.Q_schema_drift.k}} of {{v1.detect.PM.schema_drift.Q_schema_drift.n}}). The predicate baseline detected this class at {{v1.baseline.predicate.schema_drift.Q_schema_drift.rate}}.

## jev-v2 and jev-v3: semantic sensor on the CH-B1 field

Each sensor read a change-management record and proposed a value for `approval_token`; the score passed through the frozen thresholds and the sibling's loss predicates computed the verdict. Arm A (Jev) ran in jev-v2; arm B (Claude Haiku 4.5) is the registered jev-v3 re-run. Test split, Clopper-Pearson 95% intervals.

| sensor | noise | verdict-change rate | unsafe (deny to allow) | fail-closed (allow to deny) | abstention |
|---|---|---|---|---|---|
| Jev (jev-v2) | 0% | {{v2.vcr.jev.n00.rate}} [{{v2.vcr.jev.n00.lo}}, {{v2.vcr.jev.n00.hi}}] ({{v2.vcr.jev.n00.k}}/{{v2.vcr.jev.n00.n}}) | {{v2.vcr_unsafe.jev.n00.k}}/{{v2.vcr_unsafe.jev.n00.n}} | {{v2.vcr_failclosed.jev.n00.k}}/{{v2.vcr_failclosed.jev.n00.n}} | {{v2.abstain.jev.n00.all.rate}} |
| Jev (jev-v2) | 10% | {{v2.vcr.jev.n10.rate}} [{{v2.vcr.jev.n10.lo}}, {{v2.vcr.jev.n10.hi}}] ({{v2.vcr.jev.n10.k}}/{{v2.vcr.jev.n10.n}}) | {{v2.vcr_unsafe.jev.n10.k}}/{{v2.vcr_unsafe.jev.n10.n}} | {{v2.vcr_failclosed.jev.n10.k}}/{{v2.vcr_failclosed.jev.n10.n}} | {{v2.abstain.jev.n10.all.rate}} |
| Jev (jev-v2) | 30% | {{v2.vcr.jev.n30.rate}} [{{v2.vcr.jev.n30.lo}}, {{v2.vcr.jev.n30.hi}}] ({{v2.vcr.jev.n30.k}}/{{v2.vcr.jev.n30.n}}) | {{v2.vcr_unsafe.jev.n30.k}}/{{v2.vcr_unsafe.jev.n30.n}} | {{v2.vcr_failclosed.jev.n30.k}}/{{v2.vcr_failclosed.jev.n30.n}} | {{v2.abstain.jev.n30.all.rate}} |
| Haiku (jev-v3) | 0% | {{v3.vcr.llm.n00.rate}} [{{v3.vcr.llm.n00.lo}}, {{v3.vcr.llm.n00.hi}}] ({{v3.vcr.llm.n00.k}}/{{v3.vcr.llm.n00.n}}) | {{v3.vcr_unsafe.llm.n00.k}}/{{v3.vcr_unsafe.llm.n00.n}} | {{v3.vcr_failclosed.llm.n00.k}}/{{v3.vcr_failclosed.llm.n00.n}} | {{v3.abstain.llm.n00.rate}} |
| Haiku (jev-v3) | 10% | {{v3.vcr.llm.n10.rate}} [{{v3.vcr.llm.n10.lo}}, {{v3.vcr.llm.n10.hi}}] ({{v3.vcr.llm.n10.k}}/{{v3.vcr.llm.n10.n}}) | {{v3.vcr_unsafe.llm.n10.k}}/{{v3.vcr_unsafe.llm.n10.n}} | {{v3.vcr_failclosed.llm.n10.k}}/{{v3.vcr_failclosed.llm.n10.n}} | {{v3.abstain.llm.n10.rate}} |
| Haiku (jev-v3) | 30% | {{v3.vcr.llm.n30.rate}} [{{v3.vcr.llm.n30.lo}}, {{v3.vcr.llm.n30.hi}}] ({{v3.vcr.llm.n30.k}}/{{v3.vcr.llm.n30.n}}) | {{v3.vcr_unsafe.llm.n30.k}}/{{v3.vcr_unsafe.llm.n30.n}} | {{v3.vcr_failclosed.llm.n30.k}}/{{v3.vcr_failclosed.llm.n30.n}} | {{v3.abstain.llm.n30.rate}} |

| hypothesis | source | estimate | 95% CI | Holm-adjusted p | verdict |
|---|---|---|---|---|---|
| H1: Jev verdict-change rate at 0% noise below the registered bound | jev-v2 | {{v2.H1.estimate}} ({{v2.H1.k}}/{{v2.H1.n}}) | [{{v2.H1.ci_lo}}, {{v2.H1.ci_hi}}] | {{v2.H1.p_adj}} | {{v2.H1.verdict}} |
| H2: Jev not worse than Haiku at 30% noise | jev-v3 | Jev {{v3.H2.jev_rate}} vs Haiku {{v3.H2.llm_rate}}; difference {{v3.H2.estimate}} (b = {{v3.H2.b}}, c = {{v3.H2.c}}) | [{{v3.H2.ci_lo}}, {{v3.H2.ci_hi}}] | {{v3.H2.p_adj}} | {{v3.H2.verdict}} |
| H3: Jev cost per verdict below Haiku | jev-v3 | USD {{v3.H3.jev_usd}} vs USD {{v3.H3.llm_usd}} | [{{v3.H3.ci_lo}}, {{v3.H3.ci_hi}}] | {{v3.H3.p_adj}} | {{v3.H3.verdict}} |

H1 is Holm-adjusted within the jev-v2 family; H2 and H3 within the jev-v3 family of two.

Frozen thresholds: Jev τ_true = {{v2.tau.jev.true}} and τ_false = {{v2.tau.jev.false}} (jev-v2 validation split); Haiku τ_true = {{tau_true_llm}} and τ_false = {{v3.tau.llm.false}} (jev-v3 validation split, {{v3.tau.llm.n_scored}} of {{v3.tau.llm.n_validation}} records scored).

## Record of the LLM arm

In jev-v2, Haiku wrapped every reply in a Markdown code fence and the registered bare-JSON parser scored {{v2.invalid.llm}} of {{v2.run.n_calls.llm}} records invalid (rate {{v2.invalid.llm.rate}}), so its τ_true fell back to {{v2.tau.llm.true}} and every reading denied (known issue KI-1 in `prereg/DEVIATIONS.md`). jev-v3 re-ran that arm under a registered request fix and an arm health check, with {{v3.invalid.llm}} invalid records.

| Haiku verdict-change rate at 30% noise | value |
|---|---|
| jev-v2 exploratory lenient re-score (post hoc; different request configuration; the registered number is jev-v3) | {{xp.x.vcr.llm.n30.rate}} ({{xp.x.vcr.llm.n30.k}}/{{xp.x.vcr.llm.n30.n}}) |
| jev-v3 registered | {{v3.vcr.llm.n30.rate}} ({{v3.vcr.llm.n30.k}}/{{v3.vcr.llm.n30.n}}) |

## Caveats

(a) Haiku's threshold τ_true = {{tau_true_llm}} was forced by the 1% false-positive ceiling on a compressed score distribution; 'Jev better' means Jev's scores separate better under that ceiling, not that Haiku cannot read a record.

(b) All corpora are constructed. No prevalence claim is made.

## Standing rule

Every registration from jev-v3 onward includes an arm health check with a hard stop before the test split.

## Pointers

- Registrations: `prereg/jev-v1.md` (tag `prereg-jev-v1`), `prereg/jev-v2.md` (tag `prereg-jev-v2-reg`), `prereg/jev-v3.md` (tag `prereg-jev-v3`); departures in `prereg/DEVIATIONS.md`.
- Raw-response caches: `responses/jev-v1.jsonl`, `responses/jev-v2.jsonl`, `responses/jev-v3.jsonl`, with their run manifests.
- Full results: `results/jev-v1.md`, `results/jev-v2.md`, `results/jev-v3.md`, and the exploratory `results/jev-v2-exploratory.md`.
- Regenerate from the caches, with no model call: `python -m jev_probe.analysis`, `python -m jev_probe.analysis_v2`, `python -m jev_probe.exploratory_v2`, `python -m jev_probe.analysis_v3`, then `python -m jev_probe.note_all`.
