"""S3 (prereg/p6-v1.1.md §3; F1): the global deny-ward condition, exhaustive on the finite
models of `_common`.

For every model and sensed-field set, `is_deny_ward` (global: every reachable deny tuple, every
joint assignment of sensed values) is compared with brute force over every true tuple and every
admitted vector including unknown:

- sufficiency: if the configuration is deny-ward, no (t, o) turns deny into allow, so
  P(deny -> allow) = 0 under every distribution;
- tightness: if it is not deny-ward, some (t, o) turns deny into allow, so a distribution with
  P(deny -> allow) > 0 exists.

It also counts configurations where every sensed field is deny-ward on its own but the set is
not: the field-by-field reading is strictly weaker, which is why S3 is global.
"""

from __future__ import annotations

import sys
from collections import Counter

from checkers._common import ROOT, admitted_vectors, finite_models, out_dir_from_argv, sensed_sets, write_output
from sensed_authority.bound import is_deny_ward, single_field_deny_ward

NAME = "s3_check"
SCOPE = "finite-models:B12,B3,T2"
STATEMENT = "S3: unknown denies and the configuration is deny-ward (global) => P(deny->allow) = 0"
INPUTS = [ROOT / "checkers" / "s3_check.py"]


def run() -> dict:
    configs, deny_ward, mismatches, field_wise_only = Counter(), Counter(), Counter(), Counter()
    for fm in finite_models():
        m = fm.model
        for sensed in sensed_sets(m.contract):
            unsafe_exists = any(m.outcome(t, o)[1] for t in m.reachable for o in admitted_vectors(m, sensed))
            dw = is_deny_ward(m, sensed)
            configs[fm.family] += 1
            deny_ward[fm.family] += dw
            if dw == unsafe_exists:
                mismatches[fm.family] += 1
            if not dw and single_field_deny_ward(m, sensed):
                field_wise_only[fm.family] += 1
    return {
        "scope": SCOPE,
        "argument": "deny-ward (global) holds exactly when no vertex (t, o) turns deny into allow",
        "configurations": dict(sorted(configs.items())),
        "deny_ward": dict(sorted(deny_ward.items())),
        "mismatches": dict(sorted(mismatches.items())),
        "field_wise_deny_ward_but_not_global": dict(sorted(field_wise_only.items())),
        "holds": sum(mismatches.values()) == 0 and sum(field_wise_only.values()) > 0,
    }


def main() -> int:
    result = run()
    write_output(NAME, STATEMENT, INPUTS, result, out_dir_from_argv())
    return 0 if result["holds"] else 1

if __name__ == "__main__":
    sys.exit(main())
