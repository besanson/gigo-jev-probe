"""S2 (prereg/p6-v1.1.md §3; F6): monotonicity of the S1 bound for NESTED sensed-field sets.

Exhaustive on the finite models of `_common`: for every model, every pair of nested sensed-field
sets F' within F within the contract, every true tuple and every admitted vector over F (the
readings of F' are the same readings, restricted), the pointwise bound terms of F' do not
exceed those of F, so by linearity the S1 bound of F' does not exceed that of F under any
joint distribution. It also records why S2 is limited to nested sets: a non-nested pair where
the set with fewer sensed fields has the larger bound, so "fewest sensed fields" is not the
objective; the registered objective, the estimated bound, orders the pair correctly.
"""

from __future__ import annotations

import sys
from collections import Counter

from checkers._common import ROOT, admitted_vectors, finite_models, out_dir_from_argv, sensed_sets, write_output
from sensed_authority.bound import s1_bound
from sensed_authority.selection import select

NAME = "s2_check"
SCOPE = "finite-models:B12,B3,T2;nested-sets-only"
STATEMENT = "S2: for nested sensed-field sets, removing a sensed field does not increase the S1 bound"
INPUTS = [ROOT / "checkers" / "s2_check.py", ROOT / "src" / "sensed_authority" / "selection.py"]


def _terms(t: dict, o: dict, fields: tuple[str, ...]) -> tuple[int, int]:
    wrong = sum(1 for f in fields if o[f] is not None and o[f] != t[f])
    unknown = sum(1 for f in fields if o[f] is None)
    return wrong + unknown, wrong


def run() -> dict:
    checks, violations = Counter(), Counter()
    for fm in finite_models():
        m = fm.model
        for larger in sensed_sets(m.contract):
            subsets = [s for s in sensed_sets(larger)]
            for t in m.reachable:
                for o in admitted_vectors(m, larger):
                    big = _terms(t, o, larger)
                    for smaller in subsets:
                        small = _terms(t, o, smaller)
                        checks[fm.family] += 1
                        if small[0] > big[0] or small[1] > big[1]:
                            violations[fm.family] += 1
    rates = {"a": (0.20, 0.0), "b": (0.001, 0.0), "c": (0.001, 0.0)}
    non_nested = {
        "sets": {"one_field": ["a"], "two_fields": ["b", "c"]},
        "rates": {k: list(v) for k, v in rates.items()},
        "bound_one_field": s1_bound({"a": rates["a"]}).change,
        "bound_two_fields": s1_bound({"b": rates["b"], "c": rates["c"]}).change,
        "fewest_sensed_fields_picks": "one_field",
        "registered_objective_picks": select({"one_field": ["a"], "two_fields": ["b", "c"]}, rates),
    }
    return {
        "scope": SCOPE,
        "argument": "pointwise at every vertex; the readings of the smaller set are the restriction of the larger",
        "pointwise_checks": dict(sorted(checks.items())),
        "violations": dict(sorted(violations.items())),
        "non_nested_counterexample": non_nested,
        "holds": sum(violations.values()) == 0 and non_nested["registered_objective_picks"] == "two_fields",
    }


def main() -> int:
    result = run()
    write_output(NAME, STATEMENT, INPUTS, result, out_dir_from_argv())
    return 0 if result["holds"] else 1

if __name__ == "__main__":
    sys.exit(main())
