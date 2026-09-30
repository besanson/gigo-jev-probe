"""No statement in proof_status.json is tagged above what its checker covers.

- machine-checked: the checker's committed output holds and its scope equals the statement's;
- checked-scope-only: the checker's committed output holds (on the scope it states);
- pending-human-review: always allowed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from checkers._common import OUT_DIR, ROOT

RANK = {"pending-human-review": 0, "checked-scope-only": 1, "machine-checked": 2}


def allowed_rank(statement: dict[str, Any], out_dir: Path = OUT_DIR) -> int:
    checker = statement.get("checker")
    if not checker:
        return RANK["pending-human-review"]
    path = out_dir / f"{checker}.json"
    if not path.exists():
        return RANK["pending-human-review"]
    output = json.loads(path.read_text(encoding="utf-8"))
    if output.get("holds") is not True:
        return RANK["pending-human-review"]
    if output.get("scope") == statement["scope"]:
        return RANK["machine-checked"]
    return RANK["checked-scope-only"]


def problems(status: dict[str, Any], out_dir: Path = OUT_DIR) -> list[str]:
    found = []
    for s in status["statements"]:
        if s["tag"] not in RANK:
            found.append(f"{s['id']}: unknown tag {s['tag']!r}")
        elif RANK[s["tag"]] > allowed_rank(s, out_dir):
            found.append(f"{s['id']}: tagged {s['tag']} above its checker's scope")
    return found


def main() -> int:
    bad = problems(json.loads((ROOT / "proof_status.json").read_text(encoding="utf-8")))
    for line in bad:
        print(f"proof_status: {line}")
    if not bad:
        print("proof_status: ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
