# Preregistration jev-v3: re-run of the LLM baseline arm of jev-v2

| field | value |
|---|---|
| registration id | `jev-v3` |
| status | **DRAFT, not binding until the author tags it prereg-jev-v3** |
| registration tag | `prereg-jev-v3`, placed by the author on the commit that carries this file |
| predecessor | jev-v2 (`prereg/jev-v2.md`, tag `prereg-jev-v2-reg` on `ab2a4da`); results `results/jev-v2.md`; known issue KI-1 in `prereg/DEVIATIONS.md` |
| sibling engine | `besanson/sarc-authority-derivation` @ `cfb321ec220e83e81a771a048276571f6edf08fb` (`engines.lock`), unchanged from jev-v2 |
| arm re-run | B only: Claude Haiku 4.5, pinned as `claude-haiku-4-5-20251001` |
| arm carried | A: Jev, carried unchanged from the jev-v2 cache; no Jev call is made |
| spending cap | USD 5 for this run |

This document fixes the design, the analysis and the decision rules before any
jev-v3 data exist. Once tagged, everything in it is binding for jev-v3, and a
change counts as a deviation under §10. No jev-v3 run code exists at this commit.

## 1. Why this run exists

In jev-v2 every Claude Haiku 4.5 reply (6,000 of 6,000, including the one
registered re-request) wrapped the requested JSON object in a Markdown code fence.
The registered parser accepted bare JSON only. All 3,000 LLM records were scored
`invalid`, the thresholds fell back to ±inf, and every LLM reading mapped to
`unknown`, and so to deny. H2 and H3 in jev-v2 are therefore uninformative about
Haiku (KI-1). jev-v3 re-runs arm B with a request and a parser that remove this
failure, and adds an arm-health rule that stops a run before the test split if an
arm is not producing valid answers.

**Disclosure.** The request and parser changes below were chosen after the jev-v2
LLM replies were seen, and an exploratory lenient re-score of those replies
exists (`results/jev-v2-exploratory.md`, post hoc). jev-v3 uses the same items,
so it is a confirmatory re-run of arm B, not an independent replication. The
exploratory thresholds are not reused: arm B's thresholds are refitted on the
jev-v3 validation replies (§5).

## 2. What is unchanged from jev-v2

Everything not listed in §3 is jev-v2 unchanged, by reference to `prereg/jev-v2.md`:

- §1 question and invariant; §2 domain and field (`approval_token`);
- §3 items, seeds, splits (validation 300 items, test 700 items) and noise levels
  (0, 0.10, 0.30); the corpus regenerates byte-identically and each record SHA-256
  is checked against the jev-v2 cache before any call;
- §4 deterministic verdict; §5 evidence corpus;
- §7 admission policy: false-positive ceiling 1%, the same candidate thresholds,
  the same mapping, `unknown` routes to deny;
- §8 metrics and prices;
- §10 run order (validation, then test; items ascending; noise 0, 0.10, 0.30),
  retry rules and the worst-case pre-call cost bound;
- §11 raw-cache fields and the slot rule (every number is a named slot, filled by
  one command from the cache).

**Arm A (Jev) is carried, not re-run.** Its scores, its frozen thresholds
(`results/jev-v2.tau.json`: `tau_true = 0.49`, `tau_false = 0.05`), its
verdict-change indicators and its per-verdict costs are read from
`responses/jev-v2.jsonl` exactly as jev-v2's registered analysis read them. The
Jev values that enter the hypotheses are therefore fixed before this run:

- H2: Jev verdict-change rate at 30% noise, 68/700 = 0.0971, with the per-item
  indicators from the jev-v2 cache;
- H3: Jev per-verdict USD over the 2,100 test records, mean 0.00001730, with the
  per-record costs from the jev-v2 cache.

Arm C (keyword extractor) enters no hypothesis and is not re-run.

## 3. What changes (arm B only)

### 3a. Request

Anthropic Messages API, model `claude-haiku-4-5-20251001`, `temperature = 0`,
**`max_tokens = 32`**, no system prompt. The messages are registered verbatim:

1. user:

```
You are reading one change-management record. Decide whether it shows that the requested change has a valid approval on record. Reply with only a JSON object of the form {"p_valid": <number between 0 and 1>}, where p_valid is your probability that a valid approval is on record. No code fences. No text after the object.

Record:
<rendered record text>
```

2. assistant (prefill): `{`

The only differences from jev-v2 §6 B are the added sentence
`No code fences. No text after the object.`, the assistant prefill `{`, and
`max_tokens` 32 instead of 64. The returned `model` string is checked as in
jev-v2 (`MODEL_VERSION_CHANGED`).

If the API rejects the request shape (for example an HTTP 4xx on the prefill),
the run stops with that status before any further call. That is a stop, not an
amendment: a changed request needs a new registration.

### 3b. Parser

1. The reply text is the concatenation of the reply's text blocks, **prefixed with
   the prefill `{`**.
2. Markdown code fences (```` ``` ```` with an optional language tag) are removed.
3. The first JSON object in what remains is decoded. Any text after it is ignored.
4. The score is its `p_valid` if that is a number (not a boolean) in [0, 1].
5. Anything else is `invalid`. A `refusal` stop reason is `invalid`.

As in jev-v2, an invalid reply is re-requested once, and the record is then
scored `invalid`, which maps to `unknown`.

### 3c. Arm health rule (hard stops)

- **Smoke check before the validation split.** The first 20 arm-B records of the
  validation split, in registered order, are run first. They are cached and count
  as validation records; they are not repeated. If more than 2 of the 20 end
  `invalid` (after the one re-request), the run stops with status `ARM_INVALID`
  before any further call.
- **Health check after the validation split.** When all 900 validation records are
  cached, if more than 5% of them (more than 45) are `invalid`, the run stops with
  status `ARM_INVALID`. No thresholds are written and no test-split call is made.
- Both stops are logged in the run manifest (`responses/manifest-v3.json`) with
  the invalid count, the denominator and the check that fired. Neither is
  resumable: an `ARM_INVALID` run ends jev-v3, and any fix needs a new
  registration.

### 3d. Spending cap

**USD 5.00 in total for this run**, retries and re-requests included, enforced
with the jev-v2 §10 pre-call worst-case bound (UTF-8 request bytes as input
tokens, plus 32 output tokens). A cap stop is `CAP_TRUNCATED` with the jev-v2 §10
consequences.

### 3e. Paths

Raw cache `responses/jev-v3.jsonl`, manifest `responses/manifest-v3.json`, arm-B
thresholds `results/jev-v3.tau.json` (committed before any test-split call),
results `results/jev-v3.md` from `results/jev-v3.template.md`, slots
`results/jev-v3.slots.json`. The jev-v2 files are read, never written.

## 4. Run order

1. Preflight: Anthropic key present; sibling at the pin; the jev-v2 cache present
   and complete for arm A; corpus record SHA-256s match the jev-v2 cache.
2. Smoke check (§3c): the first 20 arm-B validation records.
3. The remaining 880 validation records.
4. Health check (§3c).
5. Fit arm-B thresholds (§5), write and commit `results/jev-v3.tau.json`.
6. The 2,100 test records.
7. Analysis from the caches.

## 5. Thresholds

Arm B's `tau_true` and `tau_false` are fitted on the 900 jev-v3 validation records
by jev-v2 §7 unchanged (1% ceiling; invalid answers excluded). Arm A keeps its
frozen jev-v2 thresholds.

## 6. Hypotheses

The numbering and decision rules are jev-v2 §9 unchanged. H1 was evaluated in
jev-v2, is unaffected by KI-1, and is not re-tested here.

**H2: Jev's verdict-change rate is not worse than the LLM baseline's at 30% noise.**
Paired indicators on the 700 test items at noise 0.30: arm A from the jev-v2
cache, arm B from the jev-v3 cache. Exact McNemar test, two-sided; CI from a
paired item bootstrap. Verdicts as in jev-v2 §9.

**H3: Jev's cost per verdict is below the LLM baseline's.**
Paired per-verdict USD over the 2,100 test records: arm A from the jev-v2 cache,
arm B from the jev-v3 cache. Item-clustered paired bootstrap, two-sided,
null-shifted p, 95% percentile CI. Verdicts as in jev-v2 §9.

H2 and H3 are Holm-corrected as one family of two, α = 0.05. Every bootstrap uses
10,000 resamples from a fresh `random.Random(20261004)`. H2 and H3 are evaluated
only if the run ends `COMPLETE`. After an `ARM_INVALID` or `CAP_TRUNCATED` stop,
they are reported as not evaluated.

## 7. Reporting

`results/jev-v3.md` reports H2 and H3, arm B's thresholds, the smoke and health
check counts, the invalid rate, the truncation count (`stop_reason = max_tokens`),
and the jev-v2 §8 descriptive metrics for arm B. It restates the carried arm-A
values with their source. The jev-v2 registered results stand as the record of
jev-v2, with the KI-1 caveat; jev-v3 does not overwrite them.

## 8. Reproduction

As jev-v2 §12, with `responses/jev-v3.jsonl` for arm B and `responses/jev-v2.jsonl`
for arm A. A reproduction from the two committed caches is exact and never calls
a model.

## 9. Code

The jev-v3 run and analysis code is committed after `prereg-jev-v3` and before
the first call. It reuses the jev-v2 corpus, threshold, verdict and statistics
code unchanged. It adds only the §3 request, parser, health rule and cap, and
the carried-arm reader.

## 10. Deviations

Any departure from this document, once tagged, is logged in
`prereg/DEVIATIONS.md` under a jev-v3 heading, with the date, the reason and the
expected impact, before the affected data are analysed. The registered analysis
is still reported, and any alternative is labelled exploratory.
