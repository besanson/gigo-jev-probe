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

*Probabilistic Sensing, Deterministic Authority: Admitting Model-Produced Observations into Sufficiency-Checked Governance Contracts.* Registered in [`prereg/p6-v1.1.md`](prereg/p6-v1.1.md) (superseding [`prereg/p6-v1.md`](prereg/p6-v1.md)); E1 and E2 are complete and every result is filled from the committed caches into [`results/p6.md`](results/p6.md). Claims and their status against the evidence: [`CLAIMS.md`](CLAIMS.md); prior-art fence: [`NOVELTY.md`](NOVELTY.md); departures: [`prereg/DEVIATIONS.md`](prereg/DEVIATIONS.md).

Manuscript v0.1: [`paper/paper6-draft-v0.1.md`](paper/paper6-draft-v0.1.md) holds every number as a `{{slot}}`; `python paper/populate.py` fills it from `results/p6.slots.json`, the checker outputs, the mutation result and the E0 slots at tag `jev-probes-final` into [`paper/paper6-draft-v0.1-populated.md`](paper/paper6-draft-v0.1-populated.md). The LaTeX release kit in [`paper-tex/`](paper-tex/) is ported with attribution from `sarc-authority-derivation` at its pin.

```bash
make bootstrap        # siblings at their pins, .venv, dev extras, pin check, toolchain preflight
make paper            # figure, populated draft, refs.bib, main.tex (pandoc), sidecars, PDF (Tectonic), arXiv tarball
make gates            # release gates G1 to G9 plus terminology, proof-status, typed-numerals and freshness lints
make release-check    # tests, checkers, results regeneration, lints and gates; no inference call
python paper-tex/verify_citations.py   # re-fetch and re-verify every citation (needs network)
```

**Canonical document toolchain** (round-three finding R3-1): **Pandoc 3.1.3** and **Tectonic 0.17.0**. Under these, `paper-tex/main.tex`, `main.pdf` and `arxiv.tar.gz` regenerate byte for byte. Other Pandoc writers produce a different `main.tex` (Pandoc 3.7.0.2, 2.19.2 and 2.17.1.1 were observed to), so `make release-check` starts with `python preflight.py --paper` and stops with a message naming Pandoc 3.1.3 when Pandoc's major.minor is not 3.1. A different Tectonic version is reported, not refused.

`release-check` makes no inference call (R3-2). It is not offline by default: Tectonic needs its TeX bundle, `default_bundle_v33`, either already in its cache or fetched over the network on the first build.

Tools beyond Python, all reported by `python preflight.py --paper`:

- a TeX engine: Tectonic 0.17.0 (canonical; it fetches `lmodern.sty` from its bundle) or `latexmk` with a TeX Live that provides `lmodern.sty` (found with `kpsewhich`);
- `pandoc` 3.1.3;
- `pdftotext` and `pdfinfo` (poppler-utils).

`make bootstrap` (R3-3) runs the install sequence of the Reproduction path above in one step: it clones both siblings at their `engines.lock` pins if absent, creates `.venv`, installs the dev extras and `dqSarc`, and runs the pin check and `preflight.py --paper`.

Figure 1 is drawn by `paper/figs/fig1_pipeline.py` with matplotlib (pinned in the `dev` extras), which writes both the SVG and the PDF with its bundled fonts and fixed metadata; no SVG converter is needed.

## Status

jev-v1, jev-v2 and jev-v3 complete. Results: [`docs/jev-note.md`](docs/jev-note.md).
