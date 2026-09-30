"""Paper 6 checkers: committed outputs hold, are fresh, and back every proof-status tag."""

from __future__ import annotations

import contextlib
import copy
import json
from pathlib import Path

import pytest

from checkers import mutation_gate, n6_witness, proof_status_lint, run_all, s3_check
from checkers._common import OUT_DIR, ROOT, write_output
from checkers._provenance import inputs_hash

STATUS = json.loads((ROOT / "proof_status.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", run_all.CHECKERS)
def test_committed_output_holds_and_is_fresh(name: str) -> None:
    out = json.loads((OUT_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert out["holds"] is True
    assert out["checker"] == name
    assert out["provenance"].startswith("sarc-suite-one-pass")
    mod = __import__(f"checkers.{name}", fromlist=["INPUTS"])
    from checkers._common import CORE_INPUTS
    with contextlib.chdir(ROOT):
        fresh = inputs_hash([p.relative_to(ROOT) for p in sorted(set(CORE_INPUTS + mod.INPUTS))])
    assert out["inputs_hash"] == fresh, f"{name}: stale output, run `make formal`"
    assert len(out["generated_at_head_sha"]) == 40


def test_proof_status_is_within_checker_scope() -> None:
    assert proof_status_lint.problems(STATUS) == []
    assert proof_status_lint.main() == 0


def test_proof_status_lint_catches_overclaims(tmp_path: Path) -> None:
    status = copy.deepcopy(STATUS)
    general = next(s for s in status["statements"] if s["id"] == "S1")
    general["tag"] = "machine-checked"
    assert proof_status_lint.problems(status) == ["S1: tagged machine-checked above its checker's scope"]
    proof = next(s for s in status["statements"] if s["id"] == "S1-proof")
    proof["tag"] = "checked-scope-only"
    assert len(proof_status_lint.problems(status)) == 2
    bad = {"statements": [{"id": "X", "scope": "general", "checker": None, "tag": "proved"}]}
    assert proof_status_lint.problems(bad) == ["X: unknown tag 'proved'"]
    (tmp_path / "s1_check.json").write_text(json.dumps({"holds": False, "scope": "general"}))
    failing = {"statements": [{"id": "Y", "scope": "general", "checker": "s1_check", "tag": "checked-scope-only"}]}
    assert proof_status_lint.problems(failing, tmp_path) != []
    missing = {"statements": [{"id": "Z", "scope": "w", "checker": "absent", "tag": "checked-scope-only"}]}
    assert proof_status_lint.problems(missing, tmp_path) != []


def test_every_statement_is_tagged_and_proofs_pending() -> None:
    ids = {s["id"] for s in STATUS["statements"]}
    assert {"S1", "S2", "S3", "N6", "S1-finite", "S2-finite", "S3-finite"} <= ids
    for s in STATUS["statements"]:
        if s["id"].endswith("-proof"):
            assert s["tag"] == "pending-human-review"


def test_checker_output_is_deterministic(tmp_path: Path) -> None:
    for d in ("a", "b"):
        write_output("s3_check", s3_check.STATEMENT, s3_check.INPUTS, s3_check.run(), tmp_path / d)
    assert (tmp_path / "a" / "s3_check.json").read_bytes() == (tmp_path / "b" / "s3_check.json").read_bytes()


def test_n6_witness_values() -> None:
    r = n6_witness.run()
    a, b = r["a_disjoint"]["exact"], r["b_joint"]["exact"]
    assert (a["unsafe"], a["s1_unsafe_bound"], a["bound_attained"]) == ("1/20", "1/20", True)
    assert (b["unsafe"], b["s1_unsafe_bound"], b["v1_directional_bound"]) == ("1/20", "1/10", "0")
    assert b["global_deny_ward"] is False and r["q"] == "1/20"
    assert r["b_joint"]["simulation"]["seed"] == 20261108 and r["a_disjoint"]["simulation"]["seed"] == 20261105
    assert r["b_joint"]["simulation"]["n"] == 10_000


def test_mutation_gate_formula() -> None:
    ok = mutation_gate.evaluate({"killed": 85, "survived": 15, "no_tests": 0, "total": 100})
    assert ok["kill_score"] == 0.85 and ok["passes"]
    assert not mutation_gate.evaluate({"killed": 84, "survived": 16, "no_tests": 0, "total": 100})["passes"]
    assert not mutation_gate.evaluate({"killed": 90, "survived": 10, "no_tests": 1, "total": 101})["passes"]
    assert mutation_gate.evaluate({"killed": 0, "survived": 0, "no_tests": 0, "total": 0})["kill_score"] == 0.0
