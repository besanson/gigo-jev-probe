# Fresh-clone audit findings: gigo-jev-probe at 8d73b6b

Findings are ranked by severity. No repository source file was edited, no API key was supplied, and no model call was made.

## High: the declared build prerequisites do not identify a compatible Pandoc version

The README requires `pandoc` without a version constraint, and `python preflight.py --paper` passes with system Pandoc **3.7.0.2**. Nevertheless, `make release-check` fails at the generated-LaTeX comparison, before its release gates: that Pandoc changes `paper-tex/main.tex`, including introducing `\pandocbounded`, which the committed template does not define.

- **Observed initial result:** `make release-check` exits **2**. The generated `main.tex` differs from HEAD; the independent gate invocation under Tectonic then fails G1 with `! Undefined control sequence.` and produces no PDF.
- **Downstream gate results on that failed build:** G3, G4 and G6 also fail because there is no rendered PDF. G2, G5, G7, G8, G9 and all four lints report PASS; those passes do not establish a valid build.
- **Environment-only recovery:** Pandoc **3.1.3** reproduces the committed `main.tex` byte-for-byte. With that executable first on `PATH`, Tectonic **0.17.0** passes the full release-check and reproduces both the committed PDF and arXiv archive byte-for-byte.
- **Additional compatibility probes:** Pandoc **2.17.1.1** and **2.19.2** also fail the generated-LaTeX byte comparison. They were diagnostic generation probes, not full release-check runs.
- **Undeclared prerequisite:** A compatible Pandoc writer version is necessary for the advertised byte-identical release. Version 3.1.3 is verified here; this audit does not assert it is the only compatible version.

No template, filter, manuscript, Makefile or source-code correction was made to obtain the passing build.

## Medium: offline release requires a populated Tectonic bundle cache

The Makefile describes `release-check` as needing no network, but a freshly installed Tectonic executable is not sufficient for a cold offline build. With an empty `XDG_CACHE_HOME` and `--only-cached`, compilation exits **1** with `failed to open input file "tectonic-format-latex.tex"`.

- **Prerequisite:** Tectonic must have the required format, packages and fonts cached, or have network access to obtain them. The README notes that Tectonic fetches its bundle, but the no-network release-check statement does not state the warm-cache condition.
- **Verified bundle:** `default_bundle_v33`; cache identifier `6ffe055852f8faf66c0acbe1a7fb27f87b869a90bad1204f3bf4d9683f597c7c`.
- **Boundary:** Git cloning, dependency installation and build-tool downloads used network access. The formal, mutation, analysis, population and release-check Python processes were guarded against opening sockets; native Tectonic could obtain TeX resources. No inference endpoint was called.

## Low: there is no executable bootstrap entry point

The checkout has no bootstrap script or Makefile target. `make -n bootstrap` exits **2** with `No rule to make target 'bootstrap'`; the README’s documented virtual-environment and editable-install sequence succeeds and was used as bootstrap instead.

This is an absent convenience entry point, not a failed dependency installation. No additional Python dependency was needed beyond the README extras for the requested repository gates; SciPy was installed only in a separate environment for this audit’s independent arithmetic.

## Informational: every requested numerical table reproduces independently

**Numbers differing from the manuscript: none.** All **52 data rows** across **8 tables** are identical at the manuscript’s displayed precision, covering **313 distinct populated slots** and **328 slot occurrences**, including nonnumeric verdict and selection slots.

| Table audited | Data rows | Result |
|---|---:|---|
| E1 unsafe/change counts, rates, confidence intervals and registered bounds | 6 | PASS; no differing number |
| E1 marginal versus simultaneous bounds | 6 | PASS; no differing number |
| Global deny-ward configuration counts in the E1 section | 5 | PASS; no differing number |
| E1 per-field wrong-admission and unknown rates | 6 | PASS; no differing number |
| E2 estimated bounds and selected reducts | 4 | PASS; no differing number |
| E2 picked/other change rates, counts and unsafe counts | 12 | PASS; no differing number |
| E2 post hoc unsafe bounds and flips by reduct | 8 | PASS; no differing number |
| Hypotheses: H1 and four H2 comparisons | 5 | PASS; no differing number |

The audit script imports **none** of `experiments`, `jev_probe` or `sensed_authority`. It reads the committed raw response bodies, independently parses all **12,000 E1** and **24,000 E2** responses, verifies those parsed scores against the cached score records, applies the frozen admission thresholds, reconstructs the registered splits, and builds independent contract lookup tables from the pinned sibling’s domain and loss definitions.

It then recomputes split-B wrong/unknown counts, marginal and simultaneous bounds, all test outcomes, E2 picks, exact binomial tails, exact two-sided McNemar tests, Holm adjustment and the 10,000-resample item bootstrap with seed **20261104**. Clopper–Pearson limits use SciPy beta quantiles rather than repository statistics; the deny-ward counts use an independent grouping of reachable tuples by recorded-field values.

The frozen threshold JSON files are inputs, not refitted outputs of this audit. The sibling domain/loss definitions are the declared experimental specification, not an independently validated model of real-world policy; the paper-5 historical choice is checked against its pinned artifact and observation costs.

| Hypothesis | Independently recomputed estimate / discordance | 95% CI | Raw p | Holm p |
|---|---|---|---|---|
| H1 | 6-cell Bonferroni family | Not applicable | 1.0000 | 1.0000 |
| H2 Jev arm 1 | −0.1000; b=0, c=70, n=700 | [−0.1229, −0.0786] | 1.69e-21 | 6.78e-21 |
| H2 Jev arm 2 | −0.1029; b=0, c=72, n=700 | [−0.1257, −0.0814] | 4.24e-22 | 2.12e-21 |
| H2 Haiku arm 1 | −0.0657; b=0, c=46, n=700 | [−0.0843, −0.0486] | 2.84e-14 | 5.68e-14 |
| H2 Haiku arm 2 | −0.0743; b=0, c=52, n=700 | [−0.0943, −0.0557] | 4.44e-16 | 1.33e-15 |

There were **zero raw-body versus cached-score mismatches** and **zero invalid calls** in these two caches. The independently rebuilt table rows and underlying values are recorded in `independent-results.json`; these are not values obtained by importing the repository’s analysis or population script.

## Informational: all requested gates pass with the recovered toolchain

The final `make release-check` returned **exit code 0**. An earlier recovered-toolchain run also reached `release-check: ALL CHECKS PASS` in its persisted log, but its tool wrapper timed out; the final run removes that execution-status ambiguity.

### Gate outcomes

| Requested check | Status | Observed result |
|---|---|---|
| Bootstrap | PASS via README; literal target absent | Editable installation of `.[dev,live,live-v2]` and sibling `dqSarc` succeeds |
| `pytest` | PASS | **294 passed**, 292 deprecation warnings, 334.07 seconds |
| `make formal`, run 1 | PASS | S1, S2, S3 and N6 hold; its two internal runs byte-identical |
| `make formal`, run 2 | PASS | Same; installed output hashes also equal run 1 |
| `make mutate` | PASS | **544 killed, 31 survived, 575 total; 0 untested**; kill score **0.9460869565217391**, threshold 0.85 |
| Mutation ancillary statuses | PASS | 0 skipped, suspicious, timed out, interrupted or segfaulted mutants |
| `python -m experiments.analysis_p6`, run 1 | PASS | Writes 706 result slots |
| Same command, run 2 | PASS | Both output files byte-identical to run 1 and HEAD |
| `python paper/populate.py`, run 1 | PASS | Fills 558 distinct template slots |
| Same command, run 2 | PASS | Populated manuscript byte-identical to run 1 and HEAD |
| Release-check with system Pandoc 3.7.0.2 | FAIL | Generated-LaTeX diff; exit 2 |
| Release-check with Pandoc 3.1.3 / Tectonic 0.17.0 | PASS | Final exit 0; results, figures, manuscript, sidecars, bibliography, PDF and archive checks pass |
| Independent requested-table recomputation | PASS | 8 tables, 52 data rows; no differences |

The successful formal and mutation commands update only `generated_at_head_sha` in their five tracked JSON result files. All computational content is unchanged from HEAD; the formal checker stamps previously named `e3d5ed12518515398c866fd3a191691dbc908bf4`, and the mutation stamp named `120a13907b131d894ae5acc57d15921e0c186a20`; both now name the audited checkout.

### Release gates and lints under the passing toolchain

| Gate | Result | Gate | Result |
|---|---|---|---|
| G1 build | PASS | G2 token purity | PASS |
| G3 number parity | PASS | G4 prose parity | PASS |
| G5 structure parity | PASS | G6 disclosure and banners | PASS |
| G7 sidecar sync | PASS | G8 citation completeness | PASS |
| G9 bibliography quality | PASS | Terminology lint | PASS |
| Proof-status lint | PASS | Typed-numerals lint | PASS |
| Populated-manuscript freshness | PASS | | |

G1’s two clean builds each produce **22 pages**, with identical SHA-256, no missing characters, no unresolved PDF markers, and no overfull boxes above the gate’s 10-point threshold. These checks reproduce the repository’s stated gate scopes; they do not turn checked-scope-only or pending-human-review propositions into general proofs.

### PDF and byte-identity fingerprints

| Artifact | SHA-256 |
|---|---|
| `paper-tex/main.pdf`, committed and independently rebuilt | `76d57123ae7dd4813f741a988b2ea66ee5d8b126d8212edc5a9eeff25cc84864` |
| `paper-tex/arxiv.tar.gz`, committed and rebuilt | `d87d8b673f0a893a3110ef73b3b89d8b0497b51cdd9c0b55b207af7e1c26c011` |
| `results/p6.md`, both requested runs | `57471c788a66d7097b2672b762545664ef4064ded408f8ea5ea52f262570fd37` |
| `results/p6.slots.json`, both requested runs | `f4583adbabcf51f869035361e8e2435abce1084e87d157b836d5e2b9d0bae2f6` |
| Populated manuscript, both requested runs | `b7dd70d260bc69a6434b9bf8923da9f03740ba5b3aa500dc5e3754fb81e3d848` |

The PDF is **169,303 bytes**, **22 A4 pages**, PDF version **1.5**. The fixed build environment is `SOURCE_DATE_EPOCH=1786609963`, `TZ=UTC`.

### Environment

| Component | Verified value |
|---|---|
| OS / architecture | Ubuntu 26.04 LTS; Linux 6.1.155; x86_64; glibc 2.43 |
| Audit checkout | `8d73b6bad6a9e4f7c5ee19e1b716d51182b05d3c` |
| `dqSarc` sibling | `db6c396128a4df7fe12d13be163b1e7d32087177` |
| `sarc-authority-derivation` sibling | `cfb321ec220e83e81a771a048276571f6edf08fb` |
| Historical `[self]` pin, retained as history rather than current checkout | `e1fc75b6686beecd3f4abdd57241ffc46c96e019` |
| Runtime | CPython **3.12.13**, isolated virtual environment; pip **26.2.1** |
| Host default Python, not used for repository gates | 3.14.3 |
| Test / mutation / SAT | pytest **9.1.1**; Hypothesis **6.167.1**; mutmut **3.7.0**; python-sat **1.9.dev15** |
| Figure generation | matplotlib **3.9.2**; NumPy **2.5.3** |
| Installed SDKs, not called live | typesafe-sdk **0.7.2**; anthropic **1.9.0**; httpx2 **2.13.1** |
| Successful document toolchain | Pandoc **3.1.3**; Tectonic **0.17.0**, Linux musl binary |
| Other tools | Poppler `pdfinfo` / `pdftotext` **26.01.0**; GNU Make **4.4.1**; Git **2.53.0** |
| Independent arithmetic environment | Separate CPython **3.12.13** venv; SciPy **1.18.1**; NumPy **2.5.3** |

### Exact execution commands

The following records the commands used for setup and the requested checks, with log redirections retained. Commands ran under `/home/user/workspace/audit`; source files in all three checkouts remained unchanged.

```bash
mkdir -p /home/user/workspace/audit
git clone https://github.com/besanson/gigo-jev-probe.git /home/user/workspace/audit/gigo-jev-probe
git -C /home/user/workspace/audit/gigo-jev-probe checkout --detach 8d73b6b
git clone https://github.com/besanson/dqSarc.git /home/user/workspace/audit/dqSarc
git -C /home/user/workspace/audit/dqSarc checkout --detach db6c396128a4df7fe12d13be163b1e7d32087177
git clone https://github.com/besanson/sarc-authority-derivation.git /home/user/workspace/audit/sarc-authority-derivation
git -C /home/user/workspace/audit/sarc-authority-derivation checkout --detach cfb321ec220e83e81a771a048276571f6edf08fb

cd /home/user/workspace/audit/gigo-jev-probe
uv venv --python 3.12 --seed .venv
. .venv/bin/activate
pip install -e '.[dev,live,live-v2]' -e ../dqSarc > ../bootstrap.log 2>&1
unset JEV_API_KEY TYPESAFE_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY
pytest > ../pytest.log 2>&1

# External audit-only sitecustomize.py blocks Python socket connections.
# Its entire content is reproduced below this command block.
export PYTHONPATH=/home/user/workspace/audit/guard
make formal > ../formal-1.log 2>&1
sha256sum out/p6/checkers/*.json > ../formal-1.sha256
make formal > ../formal-2.log 2>&1
sha256sum out/p6/checkers/*.json > ../formal-2.sha256
diff -u ../formal-1.sha256 ../formal-2.sha256

make mutate > ../mutation.log 2>&1

python -m experiments.analysis_p6 > ../analysis-1.log 2>&1
sha256sum results/p6.md results/p6.slots.json > ../analysis-1.sha256
python -m experiments.analysis_p6 > ../analysis-2.log 2>&1
sha256sum results/p6.md results/p6.slots.json > ../analysis-2.sha256
diff -u ../analysis-1.sha256 ../analysis-2.sha256
git diff --exit-code -- results/p6.md results/p6.slots.json

python paper/populate.py > ../populate-1.log 2>&1
sha256sum paper/paper6-draft-v0.1-populated.md > ../populate-1.sha256
python paper/populate.py > ../populate-2.log 2>&1
sha256sum paper/paper6-draft-v0.1-populated.md > ../populate-2.sha256
diff -u ../populate-1.sha256 ../populate-2.sha256
git diff --exit-code -- paper/paper6-draft-v0.1-populated.md

cd /home/user/workspace/audit
mkdir -p bin
curl -fL https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-unknown-linux-musl.tar.gz -o tectonic.tar.gz
tar -xzf tectonic.tar.gz -C bin
export PATH=/home/user/workspace/audit/bin:$PATH
cd gigo-jev-probe
python preflight.py --paper > ../preflight-paper.log 2>&1
make release-check > ../release-check-1.log 2>&1

# Diagnostic gates on the Pandoc 3.7.0.2 output.
export SARC_LATEX_COMPILER=tectonic
python paper-tex/gates/run_gates.py > ../gates-pandoc3.log 2>&1
cp paper-tex/parity-report.json ../parity-pandoc3.json

# Two diagnostic Pandoc generation probes; neither reproduces HEAD.
cd /home/user/workspace/audit
curl -fL https://github.com/jgm/pandoc/releases/download/2.17.1.1/pandoc-2.17.1.1-linux-amd64.tar.gz -o pandoc.tar.gz
tar -xzf pandoc.tar.gz
cd gigo-jev-probe
export PATH=/home/user/workspace/audit/pandoc-2.17.1.1/bin:/home/user/workspace/audit/bin:$PATH
python paper-tex/build_main_tex.py
git diff --exit-code -- paper-tex/main.tex paper-tex/fig1-pipeline.pdf

cd /home/user/workspace/audit
curl -fL https://github.com/jgm/pandoc/releases/download/2.19.2/pandoc-2.19.2-linux-amd64.tar.gz -o pandoc-2.19.2.tar.gz
tar -xzf pandoc-2.19.2.tar.gz
cd gigo-jev-probe
export PATH=/home/user/workspace/audit/pandoc-2.19.2/bin:/home/user/workspace/audit/bin:$PATH
python paper-tex/build_main_tex.py
git diff --exit-code -- paper-tex/main.tex paper-tex/fig1-pipeline.pdf > ../pandoc-2.19.2.diff

# Environment-only recovery; byte-identical generation.
cd /home/user/workspace/audit
curl -fL https://github.com/jgm/pandoc/releases/download/3.1.3/pandoc-3.1.3-linux-amd64.tar.gz -o pandoc-3.1.3.tar.gz
tar -xzf pandoc-3.1.3.tar.gz
cd gigo-jev-probe
export PATH=/home/user/workspace/audit/pandoc-3.1.3/bin:/home/user/workspace/audit/bin:$PATH
python paper-tex/build_main_tex.py
git diff --exit-code -- paper-tex/main.tex paper-tex/fig1-pipeline.pdf > ../pandoc-3.1.3.diff
make release-check > ../release-check-2.log 2>&1

# Cold-cache offline diagnostic.
mkdir -p ../cold-cache
cd paper-tex
XDG_CACHE_HOME=/home/user/workspace/audit/cold-cache SOURCE_DATE_EPOCH=1786609963 TZ=UTC /home/user/workspace/audit/bin/tectonic --only-cached --print main.tex > ../../tectonic-cold-cache.log 2>&1
cd ..

# Final full run with explicit process-exit receipt.
make release-check > ../release-check-final.log 2>&1
code=$?
printf '%s\n' "$code" > ../release-check-final.exit
sha256sum paper-tex/main.pdf paper-tex/arxiv.tar.gz
pdfinfo paper-tex/main.pdf
git diff --exit-code -- paper-tex/main.pdf paper-tex/arxiv.tar.gz paper-tex/main.tex

# Independent arithmetic environment; no repository package is installed in it.
# These two installation commands ran in a separate shell with PYTHONPATH unset.
uv venv --python 3.12 --seed /home/user/workspace/audit/independent-venv
/home/user/workspace/audit/independent-venv/bin/pip install scipy > /home/user/workspace/audit/independent-install.log 2>&1
cd /home/user/workspace/audit
PYTHONPATH=/home/user/workspace/audit/guard independent-venv/bin/python independent_recompute.py > independent.log 2>&1

cd gigo-jev-probe
make -n bootstrap > ../bootstrap-target.log 2>&1
git diff --exit-code -- '*.py' '*.toml' Makefile README.md engines.lock 'prereg/*' paper/paper6-draft-v0.1.md paper-tex/template.tex 'paper-tex/filters/*'
git status --short
git -C ../dqSarc status --short
git -C ../sarc-authority-derivation status --short
```

The external Python network guard was created outside the checkout with the following content. The initial standalone pytest preceded this guard; the full test suite was subsequently rerun inside each guarded release-check.

```python
"""Audit-only guard: prevent Python processes from opening network connections."""
import socket

def blocked(*args, **kwargs):
    raise RuntimeError("AUDIT: network connection prohibited")

socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
```

The independent script’s SHA-256 is `ce746a96eded4d2f5862430b6cc5f982de93895843f2de04cbbd8c89c59435d1`; its successful result file’s SHA-256 is `dedcd3eadaec2016d4afcf17057b6274afaff30338f05b2fbc864bcb36a42c12`. The only remaining tracked changes are the five generated checker/mutation provenance stamps described above; the sibling checkouts are clean.
