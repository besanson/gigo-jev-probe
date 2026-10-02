.PHONY: bootstrap formal mutate run6 paper gates release-check

PY ?= python

# R3-3: the README install sequence as one target. Clones both siblings beside this repository
# if absent, checks out their engines.lock pins, creates .venv, installs the dev extras and
# dqSarc, then runs the pin check and the paper toolchain preflight. Needs network access
# (git, pip). Activate .venv afterwards (`. .venv/bin/activate`) before the other targets.
BOOT_PY = .venv/bin/python
bootstrap:
	@set -e; for name in dqSarc sarc-authority-derivation; do \
	  url=$$(python3 -c "import tomllib,sys;print(tomllib.load(open('engines.lock','rb'))[sys.argv[1]]['url'])" $$name); \
	  commit=$$(python3 -c "import tomllib,sys;print(tomllib.load(open('engines.lock','rb'))[sys.argv[1]]['commit'])" $$name); \
	  [ -d ../$$name/.git ] || git clone $$url ../$$name; \
	  git -C ../$$name fetch -q origin $$commit 2>/dev/null || true; \
	  git -C ../$$name checkout -q --detach $$commit; \
	done
	[ -x $(BOOT_PY) ] || python3 -m venv .venv
	$(BOOT_PY) -m pip install -q -e ".[dev,live,live-v2]" -e ../dqSarc
	$(BOOT_PY) -c "import preflight,sys; e=preflight.check_pin(); print('bootstrap: ' + (e or 'both siblings at their pins')); sys.exit(2 if e else 0)"
	$(BOOT_PY) preflight.py --paper
	@echo "bootstrap: done. Activate with: . .venv/bin/activate"

# Paper 6 Phase B: run every checker twice and require byte-identical output, then install it.
formal:
	@set -e; tmp=$$(mktemp -d); \
	$(PY) -m checkers.run_all $$tmp/a; \
	$(PY) -m checkers.run_all $$tmp/b; \
	diff -r $$tmp/a $$tmp/b; \
	mkdir -p out/p6/checkers; cp $$tmp/a/*.json out/p6/checkers/; rm -rf $$tmp; \
	echo "formal: two runs byte-identical; outputs in out/p6/checkers/"

# Mutation gate on src/sensed_authority (kill score >= 0.85, no untested mutants).
mutate:
	rm -rf mutants
	$(PY) -m mutmut run
	$(PY) -m mutmut export-cicd-stats
	$(PY) -m checkers.mutation_gate --write

run6:
	@echo "$@: use python -m experiments.run_p6 E1|E2 (prereg/p6-v1.1.md section 7)" >&2; exit 2

# Paper 6 manuscript (Phase D): figure, slots, bibliography, main.tex, sidecars, PDF and arXiv
# tarball, all generated; nothing in paper-tex/ is hand-edited.
paper:
	$(PY) paper/figs/fig1_pipeline.py
	$(PY) paper/populate.py
	cd paper-tex && $(PY) generate_refs_bib.py
	$(PY) paper-tex/build_main_tex.py
	$(PY) paper-tex/make_sidecars.py
	cd paper-tex && SOURCE_DATE_EPOCH=1786609963 TZ=UTC tectonic --print main.tex > /dev/null
	cd paper-tex && $(PY) make_arxiv_tarball.py
	@echo "paper: paper-tex/main.pdf built"

# Release gates G1 to G9 plus the four lints (writes paper-tex/parity-report.json).
gates:
	$(PY) paper-tex/gates/run_gates.py

# Everything, from the committed caches; makes no inference call (R3-2). Tectonic needs its bundle
# (default_bundle_v33) already cached or network access to fetch it. Tracked files are regenerated
# in place and must come out byte-identical (git diff --exit-code). The document toolchain is
# declared (R3-1): Pandoc 3.1.3 and Tectonic 0.17.0; the first step refuses another Pandoc 3.x.
release-check:
	@echo "=== release-check: document toolchain (Pandoc 3.1, Tectonic) ==="
	$(PY) preflight.py --paper
	@echo "=== release-check: test suite ==="
	$(PY) -m pytest -q
	@echo "=== release-check: checkers, two runs byte-identical and equal to the committed outputs ==="
	@set -e; tmp=$$(mktemp -d); \
	$(PY) -m checkers.run_all $$tmp/a; \
	$(PY) -m checkers.run_all $$tmp/b; \
	diff -r $$tmp/a $$tmp/b; \
	$(PY) -c "import json,sys,pathlib; d=sys.argv[1]; s=lambda p: {k:v for k,v in json.loads(pathlib.Path(p).read_text()).items() if k!='generated_at_head_sha'}; bad=[p.name for p in sorted(pathlib.Path('out/p6/checkers').glob('*.json')) if s(p)!=s(pathlib.Path(d)/p.name)]; print('checkers: committed outputs current' if not bad else f'checkers: stale {bad}'); sys.exit(1 if bad else 0)" $$tmp/a; \
	rm -rf $$tmp
	$(PY) -m checkers.proof_status_lint
	@echo "=== release-check: mutation gate result current (inputs unchanged since the committed run) ==="
	$(PY) -c "import json,sys; from checkers import mutation_gate as m; c=json.load(open('out/p6/mutation.json')); now=m.stamped({})['inputs_hash']; ok=c['passes'] and c['inputs_hash']==now; print('mutation: kill score %.3f, inputs %s' % (c['kill_score'], 'unchanged' if c['inputs_hash']==now else 'CHANGED, rerun make mutate')); sys.exit(0 if ok else 1)"
	@echo "=== release-check: results and flips regenerate byte-identically from the caches ==="
	$(PY) -m experiments.analysis_p6
	git diff --exit-code results/p6.md results/p6.slots.json
	$(PY) -m experiments.flips_p6 --check
	@echo "=== release-check: manuscript, figure, sidecars and bibliography are current ==="
	$(PY) paper/figs/fig1_pipeline.py --check
	$(PY) paper/populate.py --check
	$(PY) paper-tex/make_sidecars.py --check
	$(PY) paper-tex/citation_check.py > /dev/null
	$(PY) paper-tex/build_main_tex.py
	git diff --exit-code paper-tex/main.tex paper-tex/fig1-pipeline.pdf
	@echo "=== release-check: lints ==="
	$(PY) -m lint.terminology
	$(PY) -m lint.typed_numerals
	@echo "=== release-check: release gates G1 to G9 and lints ==="
	$(PY) paper-tex/gates/run_gates.py
	cd paper-tex && $(PY) make_arxiv_tarball.py
	git diff --exit-code paper-tex/main.pdf paper-tex/arxiv.tar.gz
	@echo "release-check: ALL CHECKS PASS"
