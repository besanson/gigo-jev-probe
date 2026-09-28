"""Fills docs/jev-v1-note.md from docs/jev-v1-note.template.md. Every number in the note
is a named {{slot}} read from results/jev-v1.slots.json; none is typed by hand.

    python -m jev_probe.note           # (re)write the filled note
    python -m jev_probe.note --check   # verify every slot fills and the committed note is current
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jev_probe.analysis import fill
from jev_probe.constants import ROOT, SLOTS_JSON_PATH

NOTE_TEMPLATE_PATH = ROOT / "docs" / "jev-v1-note.template.md"
NOTE_PATH = ROOT / "docs" / "jev-v1-note.md"

# The note's prose states these readings in words; refuse to fill it if the slots disagree.
PROSE_PRECONDITIONS = {
    "H2.PM.verdict": "refuted",
    "detect.PM.schema_drift.Q0_valid.k": "0",
}


def build(template_path: Path = NOTE_TEMPLATE_PATH, slots_path: Path = SLOTS_JSON_PATH) -> str:
    slots = json.loads(slots_path.read_text(encoding="utf-8"))
    for key, want in PROSE_PRECONDITIONS.items():
        if slots.get(key) != want:
            raise ValueError(f"note prose assumes {key} = {want!r}, slots give {slots.get(key)!r}")
    return fill(template_path.read_text(encoding="utf-8"), slots)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    filled = build()
    if args.check:
        if not NOTE_PATH.exists() or NOTE_PATH.read_text(encoding="utf-8") != filled:
            print(f"note: {NOTE_PATH} is missing or stale")
            return 1
        print(f"note: {NOTE_PATH} is current")
        return 0
    NOTE_PATH.write_text(filled, encoding="utf-8")
    print(f"note: wrote {NOTE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
