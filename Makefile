.PHONY: formal mutate run6 paper release-check

PY ?= python

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

run6 paper release-check:
	@echo "$@: not yet registered (paper 6, Phase C onward; see prereg/p6-v1.1.md)" >&2; exit 2
