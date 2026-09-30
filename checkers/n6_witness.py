"""N6 witnesses (prereg/p6-v1.1.md §3 N6, §5.7; F1, F9). Exact, then a seeded simulation.

(a) Disjoint errors, S1 attained. Two binary sensed fields, allow iff both true; true values
    (false, true) or (true, false) with probability 1/2 each; the false field is admitted as
    true with probability 0.05, every other reading is correct. e_1 = e_2 = 0.025 and
    P(deny -> allow) = 0.05 = e_1 + e_2: the S1 unsafe bound is attained. Seed 20261105.
(b) Joint errors, AND contract, q = 0.05. True values (false, false); with probability q both
    fields are admitted true together, otherwise both are correct. The directional term of
    prereg/p6-v1.md (e_i^+: field i wrong alone, the others true, turns deny into allow) is 0
    for both fields, yet P(deny -> allow) = q, so the v1 directional bound is false. The
    registered v1.1 S1 bound, e_1 + e_2 = 2q, holds and is not attained; the configuration is
    not deny-ward under S3's global condition. Seed 20261108.

Both witnesses are computed exactly with fractions; the simulations (10,000 items each) check
that a sampled implementation reproduces them.
"""

from __future__ import annotations

import random
import sys
from fractions import Fraction

from checkers._common import ROOT, out_dir_from_argv, write_output
from sensed_authority.bound import ContractModel, is_deny_ward

NAME = "n6_witness"
SCOPE = "witness"
Q = Fraction(5, 100)
N_SIM = 10_000
SEED_A, SEED_B = 20261105, 20261108
FIELDS = ("f1", "f2")
STATEMENT = ("N6: (a) the S1 unsafe bound is attained with disjoint errors; (b) joint errors defeat the v1 "
             "directional bound while S1 holds")
INPUTS = [ROOT / "checkers" / "n6_witness.py"]


def and_model() -> ContractModel:
    reach = [{"f1": a, "f2": b} for a in (False, True) for b in (False, True)]
    return ContractModel(FIELDS, reach, lambda t: "allow" if t["f1"] and t["f2"] else "deny",
                         {"f1": (False, True), "f2": (False, True)})


def joint_a() -> list[tuple[Fraction, dict, dict]]:
    half = Fraction(1, 2)
    out = []
    for t in ({"f1": False, "f2": True}, {"f1": True, "f2": False}):
        false_field = "f1" if not t["f1"] else "f2"
        flipped = dict(t, **{false_field: True})
        out += [(half * Q, t, flipped), (half * (1 - Q), t, dict(t))]
    return out


def joint_b() -> list[tuple[Fraction, dict, dict]]:
    t = {"f1": False, "f2": False}
    return [(Q, t, {"f1": True, "f2": True}), (1 - Q, t, dict(t))]


def exact(model: ContractModel, joint: list[tuple[Fraction, dict, dict]]) -> dict:
    unsafe = sum((p for p, t, o in joint if model.outcome(t, o)[1]), Fraction(0))
    e = {f: sum((p for p, t, o in joint if o[f] != t[f]), Fraction(0)) for f in FIELDS}
    bound = sum(e.values(), Fraction(0))
    return {"unsafe": str(unsafe), "e": {f: str(v) for f, v in e.items()}, "s1_unsafe_bound": str(bound),
            "bound_holds": unsafe <= bound, "bound_attained": unsafe == bound}


def v1_directional_bound(model: ContractModel, joint: list[tuple[Fraction, dict, dict]]) -> Fraction:
    """sum over fields of e_i^+ as prereg/p6-v1.md defined it (withdrawn in v1.1 by F1)."""
    total = Fraction(0)
    for f in FIELDS:
        for p, t, o in joint:
            if o[f] != t[f] and model.outcome(t, {g: (o[f] if g == f else t[g]) for g in FIELDS})[1]:
                total += p
    return total


def simulate(model: ContractModel, which: str, seed: int) -> dict:
    rng = random.Random(seed)
    unsafe = wrong1 = wrong2 = 0
    for _ in range(N_SIM):
        if which == "a":
            t = {"f1": False, "f2": True} if rng.random() < 0.5 else {"f1": True, "f2": False}
            o = dict(t)
            if rng.random() < float(Q):
                o["f1" if not t["f1"] else "f2"] = True
        else:
            t = {"f1": False, "f2": False}
            o = {"f1": True, "f2": True} if rng.random() < float(Q) else dict(t)
        unsafe += model.outcome(t, o)[1]
        wrong1 += o["f1"] != t["f1"]
        wrong2 += o["f2"] != t["f2"]
    return {"seed": seed, "n": N_SIM, "unsafe": unsafe, "wrong_f1": wrong1, "wrong_f2": wrong2,
            "bound_holds": unsafe <= wrong1 + wrong2}


def run() -> dict:
    m = and_model()
    a, b = exact(m, joint_a()), exact(m, joint_b())
    b["v1_directional_bound"] = str(v1_directional_bound(m, joint_b()))
    b["global_deny_ward"] = is_deny_ward(m, FIELDS)
    return {
        "scope": SCOPE,
        "q": str(Q),
        "a_disjoint": {"exact": a, "simulation": simulate(m, "a", SEED_A)},
        "b_joint": {"exact": b, "simulation": simulate(m, "b", SEED_B)},
        "holds": (a["bound_attained"] and b["bound_holds"] and not b["bound_attained"]
                  and Fraction(b["unsafe"]) > Fraction(b["v1_directional_bound"]) == 0
                  and not b["global_deny_ward"]),
    }


def main() -> int:
    result = run()
    write_output(NAME, STATEMENT, INPUTS, result, out_dir_from_argv())
    return 0 if result["holds"] else 1

if __name__ == "__main__":
    sys.exit(main())
