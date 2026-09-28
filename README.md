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
| `engines.lock` | the pinned commit of the sibling engine `../dqSarc` |
| `preflight.py` | checks that the API key is present (`JEV_API_KEY`, or the SDK's `TYPESAFE_API_KEY`), that `JEV_BASE_URL` resolves to `https://api.typesafe.ai/v1/systemone`, and that the sibling is at its pin. It never prints the key. |
| `.env.example` | placeholder configuration. Real values live only in `.env`, which is git-ignored. |
| `tests/` | pytest suite |

## Reproduction path

```bash
# 1. Sibling engine, at the pin recorded in engines.lock
git clone https://github.com/besanson/dqSarc.git ../dqSarc
git -C ../dqSarc checkout "$(sed -n 's/^commit = "\(.*\)"/\1/p' engines.lock)"

# 2. Environment (Python 3.11+)
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,live]" -e ../dqSarc
pytest

# 3. Configuration: copy .env.example to .env, fill in real values, then load them
set -a; . ./.env; set +a
python preflight.py

# 4. Phase B, after the prereg-jev-v1 tag: run the probe, then fill the result slots from responses/
```

Analysis reads only the committed raw-response cache. Re-running it is therefore
exact and costs nothing, while a fresh live run counts as a replication.

## Status

**Phase A is complete: registration only.** This repository contains no
experiment code, and no model call has been made. Phase B begins after the
`prereg-jev-v1` tag exists.
