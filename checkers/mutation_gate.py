"""Mutation gate for src/sensed_authority: kill score >= 0.85 and no mutant without a test.

Reads mutants/mutmut-cicd-stats.json (written by `mutmut export-cicd-stats`). The kill score is
killed / (killed + survived), the formula of sarc-authority-derivation's mutation_check.py
(ADR-003), which this follows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

THRESHOLD = 0.85
STATS_PATH = Path("mutants/mutmut-cicd-stats.json")


def evaluate(stats: dict[str, Any]) -> dict[str, Any]:
    killed, survived, no_tests = stats["killed"], stats["survived"], stats["no_tests"]
    denominator = killed + survived
    score = killed / denominator if denominator else 0.0
    return {"killed": killed, "survived": survived, "no_tests": no_tests, "total": stats["total"],
            "kill_score": score, "threshold": THRESHOLD,
            "passes": score >= THRESHOLD and no_tests == 0}


def main(stats_path: Path = STATS_PATH) -> int:
    result = evaluate(json.loads(stats_path.read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passes"] else 1


if __name__ == "__main__":
    sys.exit(main())
