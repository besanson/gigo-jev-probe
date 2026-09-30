# Preregistration jev-v2: sensing a non-observable contract field for a deterministic authority gate

| field | value |
|---|---|
| registration id | `jev-v2` |
| status | **DRAFT, not binding until the author tags it prereg-jev-v2-reg** |
| registration tag | `prereg-jev-v2-reg`, placed by the author on the commit that carries this file. The existing tag `prereg-jev-v2` points to `4e79b6a`, the jev-v1 setup commit, and registers nothing. |
| sibling engine | `besanson/sarc-authority-derivation` @ `cfb321ec220e83e81a771a048276571f6edf08fb` (`engines.lock`), CH-B1 code/cloud domain |
| sensor arms | Jev (System One, `jev-latest`, `typesafe-sdk==0.7.2`); Claude Haiku 4.5 pinned as `claude-haiku-4-5-20251001`; a deterministic keyword extractor |
| spending cap | USD 40 in total across all arms |
| predecessor | jev-v1 (`prereg/jev-v1.md`, tag `prereg-jev-v1`, commit `306e701`) |

This document fixes the design, the analysis and the decision rules before any
data exist. Once tagged, everything in it is binding for jev-v2, and a change
counts as a deviation under §13. No Phase B code for jev-v2 exists at this commit.

## 1. Question and invariant

**Question.** When a required contract field is not directly observable and Jev
instantiates it from unstructured evidence, how often does sensor error change
the deterministic authority verdict?

**Invariant.** As in jev-v1, a sensor is advisory. The authority verdict is
always computed by the sibling's deterministic loss predicates (§4). A sensor only
proposes a value for one field. Its raw score never reaches the gate: it is mapped
to `true`, `false` or `unknown` by a threshold frozen before the test split is
analysed (§7), and `unknown` routes to deny. No sensor admits, blocks, repairs or
substitutes anything by itself.

## 2. Domain and field

**Domain.** The CH-B1 software-and-cloud domain of the sibling at the pin:
`domain_v4.CANDIDATE_PROPERTIES_V4` (ten candidate properties),
`domain_v4.executable_reachable_tuples_v4()` (15,120 reachable tuples at the pin)
and `losses_v4.load_loss_registry_v4()` (six loss predicates). The sibling's
`checkers/ch_b1_check.py` output at the pin gives exactly two seven-attribute
reducts:

- `{approval_token, branch, data_classification, delegated_role, operation, repository, resource_owner}`
- `{approval_token, data_classification, delegated_role, environment, operation, repository, resource_owner}`

**Field: `approval_token`** (domain `{valid, absent}`).

Justification.

1. It is in both reducts (it is a core attribute), so every sufficient contract
   requires the gate to observe it. A sensing error on it cannot be designed away
   by choosing the other reduct, unlike `branch` or `environment`.
2. It is the approval or review state the design calls for. In real software
   delivery, approval lives in unstructured records: change requests, review
   threads, CAB minutes, ticket comments. The other five shared attributes do not.
   `operation`, `repository`, `resource_owner` and `delegated_role` are carried by
   the request and the identity system as structured values, and
   `data_classification` is a catalogue label on the resource.
3. Its loss predicate is sourced (NIST SP 800-53 Rev. 5, CM-3), in
   `losses_v4.production_deployment_without_approval`.

All other nine properties are taken as directly observed at their true values.
Only `approval_token` is sensed.

## 3. Items

1. **Population.** Every tuple in `executable_reachable_tuples_v4()` at the pin, in
   the order that function returns them. Every tuple carries `approval_token`, so the
   population is all 15,120 tuples.
2. **Cap.** The population exceeds 1,000, so the items are
   `sorted(random.Random(20261001).sample(range(15120), 1000))`, indices into that
   list. No item is added, dropped or replaced after the tag.
3. **Split.** Validation indices are `set(random.Random(20261002).sample(items, 300))`
   (30%). The remaining 700 items (70%) are the test split. The same split applies
   to every arm and every noise level.
4. **Records.** Each item is rendered at three noise levels (§5), so there are
   3,000 records per arm: 900 validation and 2,100 test.
5. If the population size at the pin differs from 15,120, or any item fails to
   construct, the run aborts before any model call.

**Design facts known at registration.** These follow from the pin and the seeds
alone. They use no model output. Phase B code recomputes them and aborts on any
mismatch.

| quantity | validation | test |
|---|---|---|
| items | 300 | 700 |
| true `approval_token = valid` | 156 | 358 |
| true verdict allow | 140 | 287 |
| approval-sensitive items (verdict differs between `valid` and `absent`) | 10 | 16 |

In the whole population, 432 of 15,120 tuples are approval-sensitive: those with
`environment = production` and `operation = deploy` where no other loss fires. A
definite misreading (`valid` read as `absent` or the reverse) can change the verdict
only on approval-sensitive items. An `unknown` changes the verdict on every item
whose true verdict is allow. The primary metric therefore combines misreadings on
a small stratum with abstentions on the allow stratum, and §8 reports the two
separately.

## 4. Deterministic verdict

For a tuple `t`: `verdict(t) = deny` if any predicate in `load_loss_registry_v4()`
holds on `t`, otherwise `allow`.

For a sensed value `s ∈ {true, false, unknown}`:

- `true` gives `verdict(t.with_property("approval_token", "valid"))`;
- `false` gives `verdict(t.with_property("approval_token", "absent"))`;
- `unknown` gives `deny`, because the gate cannot observe a required contract field.

The item's **verdict change** is `1` when the sensed verdict differs from
`verdict(t)`, and `0` otherwise. A change from deny to allow is **unsafe**. A
change from allow to deny is **fail-closed**.

## 5. Evidence corpus

The corpus is produced by a registered generator,
`src/jev_probe/corpus_v2.py`. The generator follows the specification below. Its
code is committed after the tag and before any model call, and its SHA-256 is
recorded in the run manifest. The corpus is generated at run time from the seed
and is never hand-edited or committed as data. The SHA-256 of every rendered
record is stored with its cache entry.

**Base record.** One synthetic change request per item, with its phrasing chosen
by `random.Random(f"jev-v2:20261003:{i}")`, where `i` is the item index:

```
Change request {ref}
Requested by: {actor_identity}, acting as {delegated_role}
Repository: {repository}, branch {branch}, environment {environment}
Resource owner: {resource_owner}
Operation: {operation}
Deployment window: {deployment_window}
Data classification: {data_classification}
Notes: {filler}
{approval statement}
```

- `{ref}` is `CR-` followed by six digits drawn from the item's generator.
- `{filler}` is one sentence from a fixed bank of eight neutral sentences. The
  bank is registered in the generator code, and no sentence mentions approval.
- `{approval statement}` is drawn uniformly from the bank for the item's true
  value:

| true value | approval statement bank (verbatim; `{approver}` and `{date}` are drawn per item) |
|---|---|
| `valid` | `Approval: granted by {approver} on {date}.` / `Change approved by {approver} under {ref}.` / `CAB approval recorded for {ref} on {date}.` |
| `absent` | `Approval: none recorded.` / `Awaiting approval; no approver has signed off.` / `No CAB approval is on record for this change.` |

**Noise.** Two values are drawn once per item from the item's generator, after
the base record: `u ~ Uniform(0, 1)`, and a type chosen with equal probability
from `missing` and `contradictory`. At noise level `ν ∈ {0, 0.10, 0.30}`, the
item's record is perturbed if and only if `u < ν`. The perturbed sets are
therefore nested (0% ⊂ 10% ⊂ 30%), and noise levels are paired within items.

- `missing`: the approval statement line is removed.
- `contradictory`: the approval statement stays, and the line
  `Comment from {actor}: {opposite}` is appended. `{opposite}` is drawn from the
  bank for the opposite value, and `{actor}` is drawn per item. The record gives
  no precedence cue.

The ground truth is always the item's true `approval_token`. On a perturbed
record, the true value cannot be determined from the text, and the ideal sensor
answer is `unknown`.

## 6. Sensor arms

Each record is read once by each arm, with no shared state between calls.

**A. Jev (System One).** The API interface is identical to jev-v1 §3a:
`jev-latest`, `typesafe-sdk==0.7.2`, the same endpoint, credentials, base-URL
checks and run-time docs and model verification. There is one Noul question per
field, so one question per call:

```json
{"state": {"context": "Change-management record for a requested operation on a software repository. You are reading it before an authority gate decides whether the operation may proceed.",
           "record": "<rendered record text>"},
 "questions": {"Q_approval_valid": {"type": "noul", "instructions": "Does this record show that the requested change has a valid approval on record?"}}}
```

The `context` and `instructions` strings are registered verbatim. The score is
`noul ∈ [0, 1]`. The malformed-answer and 422 rule is jev-v1 §4 unchanged: one
re-request, then the answer is scored `invalid`, which maps to `unknown`.

**B. Generative LLM baseline (payload-reading).** Anthropic Messages API, model
pinned as `claude-haiku-4-5-20251001`, `temperature = 0`, `max_tokens = 64`, and
no system prompt. The `anthropic` SDK version is pinned in the Phase B commit and
recorded in the manifest. The single user message is registered verbatim:

```
You are reading one change-management record. Decide whether it shows that the requested change has a valid approval on record. Reply with only a JSON object of the form {"p_valid": <number between 0 and 1>}, where p_valid is your probability that a valid approval is on record.

Record:
<rendered record text>
```

The score is `p_valid`. A reply that does not parse as that object with a
numeric value in [0, 1] is re-requested once, and then scored `invalid`, which
maps to `unknown`. If the returned `model` string differs from the pinned
identifier, the run is flagged `MODEL_VERSION_CHANGED`.

**C. Deterministic keyword extractor.** This arm is feasible because the statement
banks are registered. The extractor matches the stems `Approval: granted`,
`Change approved by` and `CAB approval recorded` (valid), and
`Approval: none recorded`, `Awaiting approval` and `No CAB approval` (absent).
The score is `1.0` when only valid stems match, `0.0` when only absent stems
match, and `0.5` when both or neither match. It costs $0 and makes no call. It is
written against the generator's own phrase bank, so it is an informed reference,
not a fair competitor. It enters no hypothesis.

## 7. Admission policy

For each arm, the thresholds are set on the **validation split**, pooled over all
three noise levels (900 records), and then frozen. Invalid answers are excluded
from threshold setting and map to `unknown`.

- **False-positive ceiling: 1%.**
- `τ_true` is the smallest threshold such that at most 1% of validation records
  with true value `absent` have a score of at least `τ_true`.
- `τ_false` is the largest threshold such that at most 1% of validation records
  with true value `valid` have a score of at most `τ_false`.
- Candidate thresholds are the distinct validation scores, plus one value above
  the maximum (for `τ_true`) and one below the minimum (for `τ_false`).
- **Mapping:** a score of at least `τ_true` maps to `true`. Otherwise, a score of
  at most `τ_false` maps to `false`. Otherwise it maps to `unknown`. `unknown`
  routes to deny (§4).

The run executes every validation record first (§10). Then `τ_true` and
`τ_false` for each arm are computed and written to `results/jev-v2.tau.json`, and
that file is committed before any test-split call is made. The test split is the
remaining 70% and is scored only with the frozen thresholds.

## 8. Metrics

All metrics are computed on the test split, per arm and per noise level, unless
stated otherwise.

- **Primary: verdict-change rate.** The fraction of the 700 test items whose
  sensed verdict differs from the true verdict (§4). It is reported with a
  Clopper-Pearson 95% interval.
- Secondary, in the decomposition:
  - unsafe changes (deny to allow) and fail-closed changes (allow to deny), as
    counts and rates;
  - the verdict-change rate within the approval-sensitive stratum and within the
    true-allow stratum;
  - changes caused by a definite misreading versus by `unknown`.
- **Field error.** Among records mapped to `true` or `false`, the fraction that
  disagree with the true value, reported overall and separately for perturbed and
  unperturbed records.
- **Abstention rate.** The fraction mapped to `unknown`, including `invalid`,
  reported overall and separately for perturbed and unperturbed records.
- **Reliability table.** Ten equal-width bins of the raw score over [0, 1], with
  count, mean score, observed frequency of `valid` and a Wilson 95% interval, plus
  the Brier score and ECE. This covers the test split, per arm, pooled over noise
  levels and per level.
- **Latency.** Wall-clock time per attempt and per call including backoff, as
  median, P90, P99 and maximum, per arm. Retries are included and flagged.
- **Cost.** USD per call and **per verdict**, meaning the cost of all attempts for
  one (item, noise level) record, re-requests and retries included. Totals are
  given per arm.
  - Jev is priced at USD 42 per billion input tokens with output free, as in
    jev-v1 §6, from `usage`.
  - The LLM baseline is priced at the vendor's public list price for the pinned
    model on the run date, input and output, from `usage`.
  - Both prices are recorded in the manifest before the first call.
- **Input bytes.** The UTF-8 byte length of each request body, per call and in
  total, per arm.
- **Registered expectation, descriptive only:** for Jev and for the LLM baseline,
  the abstention rate rises with noise (0% < 10% < 30%). It is reported as the
  three rates with intervals and is not tested.

## 9. Hypotheses

All tests are **two-sided** with α = 0.05. H1, H2 and H3 are Holm-corrected as one
family.

**H1: Jev's verdict-change rate at 0% noise is below 2%.**
- Data: the 700 test items at noise 0, arm A.
- Test: exact binomial test of H0 `rate = 0.02`, two-sided.
- **Supported** when the Holm-adjusted p < 0.05 and the observed rate < 0.02.
- **Refuted** when the Holm-adjusted p < 0.05 and the observed rate > 0.02.
- Otherwise **inconclusive**.

**H2: Jev's verdict-change rate is not worse than the LLM baseline's at 30% noise.**
- Data: paired verdict-change indicators for arms A and B on the 700 test items at
  noise 0.30.
- Test: exact McNemar test on the discordant pairs, two-sided. The CI is from a
  paired item bootstrap.
- **Refuted** when the Holm-adjusted p < 0.05 and Jev's rate is higher.
- **Supported, Jev better** when the Holm-adjusted p < 0.05 and Jev's rate is
  lower.
- Otherwise **not refuted**. This is reported as no significant difference and is
  never presented as equivalence.

**H3: Jev's cost per verdict is below the LLM baseline's.**
- Data: paired per-verdict USD for arms A and B over the 2,100 test records (700
  items × 3 noise levels).
- Test: the mean difference (A − B) with an item-clustered paired bootstrap (all
  three noise levels of an item resampled together). The two-sided p comes from
  the null-shifted bootstrap distribution, and the CI is a 95% percentile interval.
- **Supported** when the Holm-adjusted p < 0.05 and the difference is below 0.
- **Refuted** when the Holm-adjusted p < 0.05 and the difference is above 0.
- Otherwise **inconclusive**.

Every bootstrap uses 10,000 resamples from a fresh `random.Random(20261004)`.
Everything outside §9 is descriptive.

## 10. Run order, spending cap and retries

- **Order.** All validation items come first, then all test items, each in
  ascending item index. Within an item, the noise levels run 0, then 0.10, then
  0.30. Within a record, the arms run A, then B, then C. Truncation therefore
  removes whole trailing items from every arm alike.
- **Hard cap: USD 40.00 in total across arms**, retries included.
  - Committed spend is computed from each response's `usage` at the §8 prices.
  - Before each call, the adapter adds a worst-case cost: the UTF-8 byte length of
    the request body as an upper bound on input tokens, plus `max_tokens` output
    tokens for arm B. It refuses the call if the total would exceed the cap.
  - A response with no `usage` is charged at that bound.
- **Retries** follow jev-v1 §9 for both API arms:
  - HTTP 429 and 529, other 5xx responses, connection errors and timeouts are
    retried with exponential backoff (1 s initial delay, doubling, 60 s maximum),
    up to 8 retries, honouring `Retry-After`;
  - SDK-internal retries are disabled;
  - exhaustion stops the run with `RETRY_EXHAUSTED`, and a resumed run keeps the
    registered order and repeats no cached call.
- If the cap stops the run, it is marked `CAP_TRUNCATED`. Metrics are reported for
  completed items. H1 to H3 are evaluated only if every test item has all three
  noise levels in arms A and B. If the cap stops the run during validation, no
  thresholds are set and no hypothesis is evaluated.

## 11. Raw cache and slots

These are exactly as in jev-v1 §10, with jev-v2 paths.

- **Raw cache.** `responses/jev-v2.jsonl` is append-only and committed, with the
  run manifest in `responses/manifest-v2.json`. Every raw response is appended
  before parsing. Each record carries:
  - the item index, split, noise level, arm, perturbation type, record SHA-256
    and attempt number;
  - the request body without headers;
  - the raw response body;
  - the sent and received UTC timestamps;
  - the requested model and the returned model string;
  - `usage` and latency;
  - every retry, with its status, error class and backoff delay.

  No credential, header or environment value is ever written. Arm C is recorded
  in the same cache with its score and no HTTP fields. Analysis reads only this
  cache, the frozen `results/jev-v2.tau.json` and the pinned sibling, so
  re-running it never calls a model.
- **Slots.** `results/jev-v2.template.md` has a named slot for every number, and
  `results/jev-v2.md` is filled from the cache by a single command, which also
  writes `results/jev-v2.slots.json`. No number is entered by hand. The registered
  slot families are:
  - `vcr.<arm>.<noise>.*`, `vcr_unsafe.<arm>.<noise>.*`,
    `vcr_failclosed.<arm>.<noise>.*` and `vcr_stratum.<arm>.<noise>.<stratum>.*`
  - `field_error.<arm>.<noise>.*` and `abstain.<arm>.<noise>.*`
  - `tau.<arm>.*`
  - `reliability.<arm>.<scope>.<bin>.*`, `brier.<arm>.<scope>` and `ece.<arm>.<scope>`
  - `latency.<arm>.*`, `cost.<arm>.*` and `bytes.<arm>.*`
  - `design.*` (the §3 design facts, recomputed)
  - `H1.*`, `H2.*`, `H3.*` (estimate, CI, p, adjusted p, verdict)
  - `run.*` (status, spend, model versions, SDK versions, prompt and question
    SHA-256, generator SHA-256, engine pins)

## 12. Reproduction

1. Clone `besanson/sarc-authority-derivation` beside this repository and check out
   the commit in `engines.lock`.
2. Run preflight: key presence for both API arms, the Jev base URL, and both
   sibling pins.
3. Run the probe. The Phase B code is committed after `prereg-jev-v2-reg` and
   before the first call. The probe runs validation, commits the thresholds, then
   runs the test split.
4. Run the analysis, which fills the slots from `responses/`.

A reproduction from the committed cache is exact. A fresh live run is a
replication. The corpus regenerates byte-identically from the seed, and each
record SHA-256 is checked against the cache.

## 13. Deviations

Any departure from this document, once tagged, is logged in
`prereg/DEVIATIONS.md` under a jev-v2 heading, with the date, the reason and the
expected impact, before the affected data are analysed. The registered analysis
is still reported, and any alternative is labelled exploratory.
