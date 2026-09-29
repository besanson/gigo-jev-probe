"""Fills docs/jev-note.md (jev-v1 to jev-v3) from docs/jev-note.template.md. Every result in
the note is a named {{slot}} read from the committed slot files; none is typed by hand.

    python -m jev_probe.note_all           # (re)write the filled note
    python -m jev_probe.note_all --check   # verify every slot fills and the committed note is current

Slots are namespaced by source: v1.* (results/jev-v1.slots.json), v2.* (jev-v2), v3.* (jev-v3)
and xp.* (results/jev-v2-exploratory.slots.json). Three derived slots are computed here from
those values: n_verdicts_total, unsafe_total and tau_true_llm.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jev_probe.analysis import fill
from jev_probe.constants import ROOT

TEMPLATE_PATH = ROOT / "docs" / "jev-note.template.md"
NOTE_PATH = ROOT / "docs" / "jev-note.md"
SOURCES = {
    "v1": ROOT / "results" / "jev-v1.slots.json",
    "v2": ROOT / "results" / "jev-v2.slots.json",
    "v3": ROOT / "results" / "jev-v3.slots.json",
    "xp": ROOT / "results" / "jev-v2-exploratory.slots.json",
}
NOISES = ("n00", "n10", "n30")
# (source, arm) for the six test-split rows of the v2/v3 verdict-change table.
SENSOR_ROWS = (("v2", "jev"), ("v3", "llm"))

# The note's prose states these readings in words; refuse to fill it if the slots disagree.
PROSE_PRECONDITIONS = {
    "v1.H2.PM.verdict": "refuted",
    "v1.detect.PM.schema_drift.Q0_valid.k": "0",
    "v3.H2.verdict": "supported: Jev better",
    "v3.invalid.llm": "0",
    "v3.run.status": "COMPLETE",
}


def load_slots(sources: dict[str, Path] = SOURCES) -> dict[str, str]:
    slots: dict[str, str] = {}
    for prefix, path in sources.items():
        for k, v in json.loads(path.read_text(encoding="utf-8")).items():
            slots[f"{prefix}.{k}"] = v
    rows = [(src, arm, n) for src, arm in SENSOR_ROWS for n in NOISES]
    n_total = sum(int(slots[f"{src}.vcr.{arm}.{n}.n"]) for src, arm, n in rows)
    unsafe = sum(int(slots[f"{src}.vcr_unsafe.{arm}.{n}.k"]) for src, arm, n in rows)
    for src, arm, n in rows:  # "every verdict change was fail-closed"
        if slots[f"{src}.vcr_failclosed.{arm}.{n}.k"] != slots[f"{src}.vcr.{arm}.{n}.k"]:
            raise ValueError(f"note prose assumes every change is fail-closed; {src} {arm} {n} disagrees")
    if unsafe != 0:
        raise ValueError(f"note prose says no deny-to-allow change; slots give {unsafe}")
    slots["n_verdicts_total"] = str(n_total)
    slots["unsafe_total"] = str(unsafe)
    slots["tau_true_llm"] = slots["v3.tau.llm.true"]
    for key, want in PROSE_PRECONDITIONS.items():
        if slots.get(key) != want:
            raise ValueError(f"note prose assumes {key} = {want!r}, slots give {slots.get(key)!r}")
    return slots


def build(template_path: Path = TEMPLATE_PATH, sources: dict[str, Path] = SOURCES) -> str:
    return fill(template_path.read_text(encoding="utf-8"), load_slots(sources))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    filled = build()
    if args.check:
        if not NOTE_PATH.exists() or NOTE_PATH.read_text(encoding="utf-8") != filled:
            print(f"note_all: {NOTE_PATH} is missing or stale")
            return 1
        print(f"note_all: {NOTE_PATH} is current")
        return 0
    NOTE_PATH.write_text(filled, encoding="utf-8")
    print(f"note_all: wrote {NOTE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
