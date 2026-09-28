# Preregistration jev-v1: Jev as an advisory data-quality critic on GIGO-Bench

| field | value |
|---|---|
| registration id | `jev-v1` |
| registered | 2026-09-28, in the commit tagged `prereg-jev-v1` |
| model under test | TypeSafe AI's Jev, reached at `JEV_BASE_URL` |
| benchmark | GIGO-Bench, frozen spec `benchmarks/gigo/SPEC.md` in the pinned sibling |
| engine pin | `besanson/dqSarc` @ `db6c396128a4df7fe12d13be163b1e7d32087177` (`engines.lock`) |
| status | registered. No experiment code has been written and no model call has been made. |

This document fixes the design, the analysis and the decision rules before any
data exist. Everything in it is binding for jev-v1. A change after the tag counts
as a deviation and is handled under §12.

## 1. Question and invariant

The question is whether Jev, used as a critic that only reads the evidence an
agent would act on, can detect the data defects GIGO-Bench injects. It also asks
whether Jev's stated confidence is calibrated, and whether giving it the records'
metadata improves detection over giving it the payload alone.

**Invariant:** the probe measures Jev as an **advisory critic**. Its answers are
recorded and scored. They are never used to admit, block, repair or substitute
evidence, and no result from this probe is presented as a replacement for the
deterministic predicates. Those predicates remain the enforcement mechanism and
serve here as a baseline (§7).

## 2. Items: selection from the frozen benchmark

All item construction uses only functions of the pinned engine:
`sarc_dq.substrate.episode_seed` and `make_episode`,
`Episode.clean_price_record`, and the classes in
`sarc_dq.taxonomy.classes.TAXONOMY_V0`.

1. **Seeds.** `base_seed = 20260707`, as in the frozen spec. For episode index `i`,
   `seed(i) = episode_seed(20260707, i)`.
2. **Split.** Only held-out **test**-split episodes are eligible. An episode is in
   the test split when `seed(i) % 3 == 2`, the frozen `split_of` rule. At the pin
   the eligible indices are `i = 0, 3, 6, …` (every third index).
3. **Frame.** The first **300** eligible indices in ascending order, which are
   `i = 0, 3, …, 897`. Write `j = 0 … 299` for the position of an index in this
   list.
4. **Assignment.**
   - `j = 0 … 99`: **clean** items. The evidence set is `(clean_price_record(),)`.
   - `j = 100 … 299`: **corrupted** items. The class is
     `TAXONOMY_V0[(j − 100) mod 8]` in declared order, which gives **exactly 25
     items per class**. The evidence set is
     `cls.inject(clean_price_record(), episode, random.Random(seed(i) + 1)).evidence_set()`.
     This follows the spec's rule that the injection draw derives from `seed + 1`.
     Injection is forced for the item's class, because this probe does not draw a
     corruption rate.
5. **Sample size: 300 items** (100 clean, and 200 corrupted at 25 for each of 8
   classes). With 2 conditions × 3 repeats that makes **1,800 model calls**. No
   item is added, dropped or replaced after the tag. If an item fails to construct
   at the pin, the run is aborted before any model call (§12).
6. **Ground truth** comes from the injector's `ground_truth` tag. It is never shown
   to the model.
7. **Channels** follow the pinned taxonomy.
   - Metadata-borne: `stale_master_data`, `superseded_golden_record`,
     `silent_unit_change`, `plausible_outlier`.
   - Payload-visible: `duplicate_vendor_conflicting_terms`,
     `cross_source_contradiction`, `schema_drift`, `missing_mandatory_field`.

   Declared in advance: at the pin, `silent_unit_change` and `plausible_outlier`
   leave the metadata unchanged, so neither view carries a discriminating signal
   for them. The registered expectation for both classes is detection at chance in
   both conditions. They stay in the metadata-borne pool as registered and are not
   removed after the fact.

## 3. Conditions

Each item is shown to the model in both conditions, and the evidence set is
rendered in `evidence_set()` order.

| condition | id | what the model sees |
|---|---|---|
| payload only | `P` | a JSON list containing `EvidenceRecord.payload_view()` for each record |
| payload plus metadata | `PM` | a JSON list containing `EvidenceRecord.full_view()` for each record (the payload, plus source, as_of_day, retrieved_day, age_days, version and lineage) |

The two conditions use the same system prompt, question set, output schema and
decoding settings, and differ only in the view. The system prompt says that the
records are unit-price evidence retrieved for a replenishment order decision, and
that the model is reviewing them before the decision is made. It names no defect
class beyond the questions themselves and gives no examples. The exact prompt text
is committed in Phase B before the first call, and its SHA-256 is recorded in the
run manifest. A prompt that deviates from this description is a deviation under
§12.

## 4. Question set

Every call asks all 9 questions below about one evidence set. Each answer is
typed:

```json
{"id": "<question id>", "answer": "yes" | "no", "confidence": <number in [0.5, 1.0]>}
```

`confidence` is the model's probability that its own answer is correct. From it,
`p_yes = confidence` when the answer is `yes`, and `1 − confidence` when the answer
is `no`. A response that fails the schema is re-requested **once**, with the same
prompt. If the second response also fails, every answer in the call is scored
`invalid`, which counts as not detected and not a false positive. The invalid rate
is reported for each condition.

| id | question (verbatim) | true answer is "yes" iff |
|---|---|---|
| `Q0_valid` | Is this evidence free of data-quality defects, so that it is valid to act on as-is? | item is clean |
| `Q_stale_master_data` | Is the price value stale, that is, no longer current as of the day it was retrieved? | class = stale_master_data |
| `Q_superseded_golden_record` | Is the evidence relying on a record version that has been superseded by a newer version of the same record? | class = superseded_golden_record |
| `Q_silent_unit_change` | Is the price expressed in a different unit of measure than intended, without the change being declared? | class = silent_unit_change |
| `Q_duplicate_vendor_conflicting_terms` | Are there duplicate vendor records for the same item carrying conflicting terms? | class = duplicate_vendor_conflicting_terms |
| `Q_cross_source_contradiction` | Do two or more sources disagree on the same value by more than a small tolerance? | class = cross_source_contradiction |
| `Q_schema_drift` | Has a field been renamed or changed type relative to the expected record schema? | class = schema_drift |
| `Q_missing_mandatory_field` | Is a mandatory field missing from the evidence? | class = missing_mandatory_field |
| `Q_plausible_outlier` | Is a value wrong even though it lies within a plausible range? | class = plausible_outlier |

`Q0_valid` detects a defect when its answer is `no`. Each class question detects
its class when its answer is `yes`. Questions are presented in the order listed.

## 5. Repeats and aggregation

Each (item, condition) pair is called **3 times** as independent requests with no
shared conversation state, for 1,800 calls in total. Decoding uses
`temperature = 1.0` if the endpoint accepts it; otherwise the provider default is
used and recorded. For binary endpoints, the **item-level outcome is the majority
of the 3 repeats**, with invalid answers counted as non-detections. Calibration
uses every individual answer. Agreement across repeats (Fleiss' κ for each
question) is reported descriptively.

## 6. Metrics

All metrics are computed per condition.

- **Per-class detection rate.** For class `c`, the fraction of its 25 items where
  `Q_c` has a majority `yes`. It is reported for both `Q_c` and `Q0_valid = no`,
  with Wilson 95% intervals.
- **Clean false-positive rate.** The fraction of the 100 clean items where
  `Q0_valid` has a majority `no`. Also reported: the fraction where any class
  question has a majority `yes`, and the rate for each class question on clean
  items.
- **Calibration.**
  - The Brier score over all (item, repeat, question) answers, using `p_yes`
    against the true answer, reported overall, per question, and per channel.
  - A **reliability table** with 10 equal-width bins of `p_yes` over [0, 1]. For
    each bin it gives the count, mean `p_yes`, observed frequency of `yes`, and a
    Wilson 95% interval.
  - The Brier skill score against a constant predictor at the empirical base rate
    for each question. ECE is reported descriptively.
- **Latency.** Wall-clock time per call from request sent to response parsed:
  median, P90, P99 and maximum, per condition. Retries are included and flagged.
- **Cost.** Input and output tokens per call as reported by the endpoint, and USD
  at the provider's list price. That price is recorded in the run manifest before
  the first call. Totals are given per call, per item and per condition.

## 7. Baselines

1. **Deterministic predicates, recomputed from the sibling.** For every item's
   evidence set, `sarc_dq.dq_spec.load_spec()` is evaluated with `verif="PAG"` at
   the pin. For class `c`, the predicate detects when any constraint whose
   `targets` include `c` fails. For `Q0_valid`, it detects when any constraint
   fails. Per-class detection and clean false-positive rate are computed exactly as
   in §6. This is deterministic, costs $0, and is not a model condition. Classes
   with no predicate at the pin (`silent_unit_change`,
   `duplicate_vendor_conflicting_terms`, `plausible_outlier`) are reported as
   uncovered and are not counted as misses by a predicate.
2. **Flat Ladder, as published in the sibling's paper.** These values are quoted
   from `paper/data/h1-ladder/reference_summary.json` and `paper/generated/*.tex`
   at the pin, without recomputation. Across haiku-4-5, sonnet-5, opus-4-8 and
   fable-5:
   - metadata-borne ADR is 0.605, 0.615, 0.6175 and 0.6175;
   - the explicit data-quality flag fraction is **0.0** at every rung;
   - the behavioral marker AUC is ≤ 0.50;
   - the endpoint difference is 0.0125, with 95% CI [−0.0551, 0.0801], and the
     trend is 0.0040 per tier.

   The companion payload-only critic results from
   `paper/data/h2-detection/reference_summary.json` are quoted as well. Critic
   detection per class was 1.0 for cross_source_contradiction, 0.0 for
   duplicate_vendor_conflicting_terms, 0.72 for missing_mandatory_field, 0.0 for
   plausible_outlier, 0.0 for schema_drift, 0.0 for silent_unit_change, 0.0 for
   stale_master_data and 1.0 for superseded_golden_record, with a metadata-borne
   channel mean of 0.25.

   These figures come from a different protocol: agents acting on the evidence, and
   a different critic prompt. They are shown side by side for context only. No
   hypothesis test is run against them.

## 8. Hypotheses

All tests are **two-sided** with α = 0.05. The three primary tests are
Holm-corrected as a family.

**H1: detection above chance on metadata-borne classes (condition PM).**
- Let `d` be the pooled fraction of the 100 metadata-borne corrupted items where
  their own class question has a majority `yes`.
- Chance is the model's own base rate: the pooled fraction, over those same four
  class questions, of majority `yes` on the 100 clean items (400 item-question
  pairs), clustered by item.
- Test: a two-proportion comparison with an item-clustered bootstrap (10,000
  resamples, seed 20260928). H0: `d = chance`.
- H1 is supported when the Holm-adjusted p < 0.05 and `d > chance`. A significant
  result in the other direction is reported as detection **below** chance.
- Secondary: the same test for each of the four classes (Holm within the four),
  and the same pooled test in condition P.

**H2: confidence is calibrated (condition PM, all 9 questions).**
- Test: Spiegelhalter's Z on `p_yes`, with item-clustered bootstrap standard
  errors. H0: calibrated.
- Brier skill score against the base-rate predictor, with a bootstrap 95% CI.
- H2 is **supported** when Spiegelhalter's test does not reject (Holm-adjusted)
  **and** the BSS CI lies entirely above 0.
- H2 is **refuted** when Spiegelhalter's test rejects, **or** the BSS CI lies
  entirely below 0.
- Otherwise the result is **inconclusive**.
- Secondary: the same analysis in condition P, and per channel.

**H3: metadata beats payload-only (metadata-borne classes).**
- For each of the 100 metadata-borne corrupted items, the paired item-level
  outcomes of its own class question in PM and in P.
- Test: exact McNemar, two-sided. H0: no difference.
- H3 is supported when the Holm-adjusted p < 0.05 and PM detects more items. A
  significant result favouring P is reported as such.
- Guard: H3 is not called supported if the clean false-positive rate on `Q0_valid`
  rises by more than 10 percentage points from P to PM. When that happens, the
  result is reported as "detection gain confounded by false positives".
- Secondary: the same test over all 200 corrupted items and on `Q0_valid`.

Everything outside §8 is descriptive.

## 9. Spending cap

- **Hard cap: USD 40.00** for the whole run, retries included.
- Before each call the adapter computes committed spend plus the worst-case cost
  of that call (input tokens plus the `max_tokens` output ceiling of 1,024, at list
  price). It refuses the call if the total would exceed the cap.
- If the list price cannot be established before the first call, the cap becomes
  **4,000,000 total tokens** instead.
- When the cap stops a run, the run is marked `CAP_TRUNCATED`. Descriptive metrics
  are reported for the completed items. Hypothesis verdicts are reported only if
  every item received all 3 repeats in both conditions; otherwise H1–H3 are
  reported as not evaluated.
- Calls run in a fixed registered order: item `j` ascending, then condition P
  before PM, then repeat 1 → 3. Truncation therefore removes whole trailing items
  instead of biasing one condition.

## 10. Data handling: raw cache and slots

- **Raw response cache.** Every raw response is appended, before parsing, to an
  append-only JSONL store under `responses/`, which is committed. Each record
  contains:
  - item `j`, episode index `i`, condition, repeat, and attempt number;
  - the request body without headers;
  - the raw response body;
  - a UTC timestamp for when the request was sent and one for when the response
    was received;
  - the model identifier and version string exactly as returned by the endpoint
    (or `unreported`);
  - the token counts and the latency.

  No credential, header or environment value is ever written. The run is flagged
  `MODEL_VERSION_CHANGED` if the returned version changes during the run. Analysis
  reads only from this cache, so re-running the analysis never calls the model.
- **Slots.** Results are written **only through slots**. `results/jev-v1.md` is a
  template whose every number is a named slot, for example
  `{{H1.PM.pooled.d}}` or `{{brier.PM.all}}`. The analysis fills these slots from
  the cache with a single command. No number in a results document is entered by
  hand. The registered slot families are:
  - `detect.<cond>.<class>.<question>`
  - `fpr.<cond>.<question>`
  - `brier.<cond>.<scope>`
  - `bss.<cond>.<scope>`
  - `reliability.<cond>.<bin>.*`
  - `latency.<cond>.*`
  - `cost.*`
  - `invalid.<cond>`
  - `kappa.<cond>.<question>`
  - `baseline.predicate.*`
  - `baseline.ladder.*`
  - `H1.*`, `H2.*`, `H3.*` (estimate, CI, p, adjusted p, verdict)
  - `run.*` (status, spend, model version, prompt SHA-256, engine pin)

## 11. Reproduction

1. Clone `besanson/dqSarc` beside this repository and check out the commit in
   `engines.lock`.
2. Run `python preflight.py`, which checks the key's presence, the base URL and the
   pin.
3. Run the probe (Phase B code, committed after the tag and before the first call).
4. Run the analysis, which fills the slots from `responses/`.

A reproduction that reads the committed cache is exact. A fresh live run is a
replication.

## 12. Deviations

Any departure from this document is logged in `prereg/DEVIATIONS.md` with the date,
the reason and the expected impact, before the affected data are analysed.
Examples include an item that fails to construct, an endpoint that rejects the
schema or `temperature`, or a change of engine pin. The registered analysis is
still reported, and any alternative is labelled exploratory.
