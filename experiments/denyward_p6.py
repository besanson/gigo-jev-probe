"""S3's global deny-ward condition per contract and sensed-field set (round-two finding F3).

    python -m experiments.denyward_p6       # print the result; analysis_p6 writes the slots

S3 needs the condition to hold over every reachable deny tuple and every joint assignment of
the sensed fields to any value they can take; zero observed deny-to-allow changes on a test
split cannot establish it. This module evaluates the condition itself, exhaustively, on the
pinned reachable sets of paper 5 (CH-C1 for E1, CH-B1 for E2), with no model call.

The sensed fields enter each contract through the property they determine: `approval_assertion`
through `approval_token` (I2), the other sensed fields directly. A sensed field can take any
value its derivation can produce: on CH-C1 an assertion can derive every token value (absent,
valid, expired; expiry depends on the recorded request date), on CH-B1 it derives valid or
absent. Those sets are checked to equal the contract model's own domains before evaluation.

Result per (contract, sensed set): whether the configuration is deny-ward, the number of
reachable deny tuples, how many of them some joint wrong reading turns into allow, and one
witness.
"""

from __future__ import annotations

import itertools
import json
import sys
from typing import Any

from experiments.corpus_p6 import e1_model, e2_model
from sensed_authority.bound import ContractModel

# contract name -> (model builder, {sensed-set name: contract properties sensed})
CONFIGURATIONS: dict[str, tuple[Any, dict[str, tuple[str, ...]]]] = {
    "K": (e1_model, {"approval_residency": ("approval_token", "data_residency_region")}),
    "R_branch": (lambda: e2_model("R_branch"), {"approval": ("approval_token",),
                                                "approval_branch": ("approval_token", "branch")}),
    "R_env": (lambda: e2_model("R_env"), {"approval": ("approval_token",),
                                          "approval_environment": ("approval_token", "environment")}),
}
# which experiment and arm each configuration is evaluated in
USED_IN = {("K", "approval_residency"): "E1", ("R_branch", "approval"): "E2 arm 2",
           ("R_branch", "approval_branch"): "E2 arm 1", ("R_env", "approval"): "E2 arm 1",
           ("R_env", "approval_environment"): "E2 arm 2"}
DERIVABLE = {"K": {"approval_token": ("absent", "expired", "valid")},
             "R_branch": {"approval_token": ("absent", "valid")},
             "R_env": {"approval_token": ("absent", "valid")}}


def evaluate(model: ContractModel, sensed: tuple[str, ...]) -> dict[str, Any]:
    deny = [t for t in model.reachable if model.table[tuple(t[f] for f in model.contract)] == "deny"]
    flippable, witness = 0, None
    for t in deny:
        for combo in itertools.product(*(model.domains[f] for f in sensed)):
            assigned = dict(zip(sensed, combo, strict=True))
            if model.evaluate(model.observe(t, assigned)) == "allow":
                flippable += 1
                if witness is None:
                    witness = {"true": {f: t[f] for f in model.contract}, "sensed": assigned}
                break
    return {"deny_ward": flippable == 0, "deny_tuples": len(deny), "witness_tuples": flippable,
            "witness": witness}


def denyward() -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for name, (build, sets) in CONFIGURATIONS.items():
        model = build()
        for field, values in DERIVABLE[name].items():
            if tuple(model.domains[field]) != values:
                raise ValueError(f"{name}: {field} domain {model.domains[field]} differs from the derivable set {values}")
        out[name] = {s: {**evaluate(model, fields), "sensed": list(fields), "used_in": USED_IN[(name, s)]}
                     for s, fields in sets.items()}
    return out


def main() -> int:
    print(json.dumps(denyward(), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
