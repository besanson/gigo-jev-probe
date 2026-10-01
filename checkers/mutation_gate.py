"""Mutation gate for src/sensed_authority: kill score >= 0.85 and no mutant without a test.

Reads mutants/mutmut-cicd-stats.json (written by `mutmut export-cicd-stats`). The kill score is
killed / (killed + survived), the formula of sarc-authority-derivation's mutation_check.py
(ADR-003), which this follows.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from checkers._provenance import head_sha, inputs_hash

THRESHOLD = 0.85
STATS_PATH = Path("mutants/mutmut-cicd-stats.json")
ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "out" / "p6" / "mutation.json"
# What the score depends on: the mutated package, the tests run against it, and the configuration.
INPUT_GLOBS = ("src/sensed_authority/*.py", "tests/test_p6_record.py", "tests/test_p6_admission.py",
               "tests/test_p6_bound.py", "tests/test_p6_selection.py", "tests/test_p6_properties.py",
               "pyproject.toml", "checkers/mutation_gate.py")


def stamped(result: dict[str, Any]) -> dict[str, Any]:
    with contextlib.chdir(ROOT):
        paths = sorted({p for g in INPUT_GLOBS for p in Path().glob(g)}, key=lambda p: p.as_posix())
        return {**result, "target": "src/sensed_authority", "tool": "mutmut 3.7.0",
                "inputs_hash": inputs_hash(paths), "inputs": [p.as_posix() for p in paths],
                "generated_at_head_sha": head_sha()}


def evaluate(stats: dict[str, Any]) -> dict[str, Any]:
    killed, survived, no_tests = stats["killed"], stats["survived"], stats["no_tests"]
    denominator = killed + survived
    score = killed / denominator if denominator else 0.0
    return {"killed": killed, "survived": survived, "no_tests": no_tests, "total": stats["total"],
            "kill_score": score, "threshold": THRESHOLD,
            "passes": score >= THRESHOLD and no_tests == 0}


def main(argv: list[str] | None = None, stats_path: Path = STATS_PATH) -> int:
    args = sys.argv[1:] if argv is None else argv
    result = evaluate(json.loads(stats_path.read_text(encoding="utf-8")))
    if "--write" in args:
        result = stamped(result)
        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passes"] else 1


if __name__ == "__main__":
    sys.exit(main())
