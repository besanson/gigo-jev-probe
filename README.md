# gigo-jev-probe

A preregistered probe of **TypeSafe AI's Jev** model as an **advisory data-quality
critic** on **GIGO-Bench**, the frozen benchmark in
[`besanson/dqSarc`](https://github.com/besanson/dqSarc).

## Purpose

The probe asks whether Jev can detect the data defects GIGO-Bench injects when it
reads only the evidence an agent would act on. It also asks whether Jev's stated
confidence is calibrated, and whether seeing the records' metadata helps compared
with seeing the payload alone. The full design is registered in
[`prereg/jev-v1.md`](prereg/jev-v1.md), which covers:

- the items;
- the System One API interface (`jev-latest`, Noul questions, pinned SDK);
- two conditions, payload only and payload plus metadata;
- nine typed yes/no (Noul) questions;
- three repeats;
- metrics and baselines;
- two-sided hypotheses H1–H3;
- a USD 40 spending cap;
- the raw-cache and slot rules.

## Invariant

**This probe measures a model as an advisory critic. It never replaces the
deterministic predicates.** Jev's answers are recorded and scored. They are never
used to admit, block, repair or substitute evidence. The deterministic DQ
predicates of the pinned engine remain the enforcement mechanism. In this probe
they appear only as a baseline, recomputed from the sibling.

## Layout

| path | what |
|---|---|
| `prereg/jev-v1.md` | the registration (binding once tagged `prereg-jev-v1`) |
| `engines.lock` | the pinned commits of the sibling engines `../dqSarc` and `../sarc-authority-derivation` |
| `preflight.py` | checks that the API key is present (`JEV_API_KEY`, or the SDK's `TYPESAFE_API_KEY`), that `JEV_BASE_URL` resolves to `https://api.typesafe.ai/v1/systemone`, and that both siblings (`../dqSarc` and `../sarc-authority-derivation`) are at their pins. It never prints any key. |
| `.env.example` | placeholder configuration. Real values live only in `.env`, which is git-ignored. |
| `src/jev_probe/` | jev-v1: `items.py` (§2–3), `questions.py` (§4), `adapter.py` (§3a, §4, §9, §10), `run.py`, `analysis.py` (§6–8), `template.py` |
| `responses/` | append-only raw-response cache `jev-v1.jsonl` and the run manifest |
| `results/` | `jev-v1.template.md` (slots only) and the filled `jev-v1.md` |
| `tests/` | pytest suite (mock endpoint, no network) |
| `prereg/jev-v2.md` | jev-v2 registration (binding at tag `prereg-jev-v2-reg`) |
| `src/jev_probe/*_v2.py` | jev-v2: `corpus_v2.py` (registered generator, §3–§5), `adapter_v2.py` (§6, §10), `run_v2.py`, `analysis_v2.py` (§7–§9), `template_v2.py`, and the post-hoc `exploratory_v2.py` |
| `prereg/jev-v3.md`, `src/jev_probe/*_v3.py` | jev-v3 registration (tag `prereg-jev-v3`) and its arm-B re-run: `constants_v3.py`, `adapter_v3.py`, `run_v3.py`, `analysis_v3.py` |
| `docs/jev-note.md` | the combined results note for jev-v1 to jev-v3, filled from the slot files by `python -m jev_probe.note_all` |

## Reproduction path

```bash
# 1. Both sibling engines, at the pins recorded in engines.lock. The test suite and the
#    jev-v2/v3 analysis import both; pytest fails without them.
git clone https://github.com/besanson/dqSarc.git ../dqSarc
git -C ../dqSarc checkout db6c396128a4df7fe12d13be163b1e7d32087177
git clone https://github.com/besanson/sarc-authority-derivation.git ../sarc-authority-derivation
git -C ../sarc-authority-derivation checkout cfb321ec220e83e81a771a048276571f6edf08fb

# 2. Environment (Python 3.11+)
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,live,live-v2]" -e ../dqSarc
pytest

# 3. Configuration: copy .env.example to .env, fill in real values, then load them
set -a; . ./.env; set +a
python preflight.py

# 4. Regenerate every result and the note from the committed caches (no model call)
python -m jev_probe.analysis        # results/jev-v1.md
python -m jev_probe.analysis_v2     # results/jev-v2.md
python -m jev_probe.exploratory_v2  # results/jev-v2-exploratory.md (post hoc)
python -m jev_probe.analysis_v3     # results/jev-v3.md
python -m jev_probe.note_all        # docs/jev-note.md
```

A live replication runs `python -m jev_probe.run` (jev-v1), `python -m jev_probe.run_v2` and
`python -m jev_probe.run_v3`; the v2 and v3 runners stop with `TAU_WRITTEN` after the
validation split, and refuse the test split until `results/jev-v2.tau.json` or
`results/jev-v3.tau.json` is committed. jev-v2 and jev-v3 also need `ANTHROPIC_API_KEY`.

Analysis reads only the committed raw-response cache. Re-running it is therefore
exact and costs nothing, while a fresh live run counts as a replication.

## Standing policy

Every registration from jev-v3 onward includes an arm health check with a hard stop before the test split.

## Paper 6

*Probabilistic Sensing, Deterministic Authority* (working title). The paragraph below is the paper 6 brief's summary (§1); it states what the paper sets out to show. Its experiments are registered in [`prereg/p6-v1.md`](prereg/p6-v1.md) and not yet run. Claims and their status: [`CLAIMS.md`](CLAIMS.md); prior-art fence: [`NOVELTY.md`](NOVELTY.md).

> Papers 1 to 5 govern facts that were recorded. This paper governs facts that were read. When a field the authority contract needs exists only in unstructured evidence, a model may sense it and write an observation record with a score. An admission policy, set on held-out data at a declared false-positive ceiling, maps the score to true, false or unknown. Unknown denies. The deterministic contract decides. The paper proves that the probability a sensing error changes the verdict is bounded by a sum over sensed fields, so a minimal sufficient contract bounds exposure, and shows the bound holds on two constructed domains and two sensor families with zero deny-to-allow flips in 4,200 verdicts.

## Status

jev-v1, jev-v2 and jev-v3 complete. Results: [`docs/jev-note.md`](docs/jev-note.md).
