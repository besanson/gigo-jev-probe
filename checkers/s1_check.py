"""S1 (prereg/p6-v1.1.md §3; F1, F5), exhaustive on the finite model families of `_common`.

For every model, sensed-field set, true tuple t and admitted vector o, checks pointwise:

    [verdict changed]   <= sum over sensed fields of [o_i wrong or unknown]
    [deny -> allow]     <= sum over sensed fields of [o_i wrong]

Both sides of each inequality are linear in the joint distribution of (t, o), and every such
distribution is a mixture of these point masses, so the pointwise check proves S1 for every
distribution on these models. It says nothing beyond them.
"""

from __future__ import annotations

import sys
from collections import Counter

from checkers._common import ROOT, admitted_vectors, finite_models, out_dir_from_argv, sensed_sets, write_output

NAME = "s1_check"
SCOPE = "finite-models:B12,B3,T2"
STATEMENT = "S1: P(change) <= sum(e_i + u_i); P(deny->allow) <= sum(e_i)"
INPUTS = [ROOT / "checkers" / "s1_check.py"]


def run() -> dict:
    checks, violations = Counter(), Counter()
    first_violation = None
    for fm in finite_models():
        m = fm.model
        for sensed in sensed_sets(m.contract):
            for t in m.reachable:
                for o in admitted_vectors(m, sensed):
                    changed, unsafe = m.outcome(t, o)
                    wrong = sum(1 for f in sensed if o[f] is not None and o[f] != t[f])
                    unknown = sum(1 for f in sensed if o[f] is None)
                    checks[fm.family] += 1
                    if changed > wrong + unknown or unsafe > wrong:
                        violations[fm.family] += 1
                        first_violation = first_violation or {"t": t, "o": o, "contract": m.contract}
    return {
        "scope": SCOPE,
        "argument": "pointwise at every vertex (t, o); both sides linear in the joint distribution",
        "pointwise_checks": dict(sorted(checks.items())),
        "violations": dict(sorted(violations.items())),
        "first_violation": first_violation,
        "holds": sum(violations.values()) == 0,
    }


def main() -> int:
    result = run()
    write_output(NAME, STATEMENT, INPUTS, result, out_dir_from_argv())
    return 0 if result["holds"] else 1

if __name__ == "__main__":
    sys.exit(main())
