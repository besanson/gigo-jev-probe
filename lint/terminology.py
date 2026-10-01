"""Terminology lint for paper 6 (brief §6): model output is an observation, never a verdict.

    python -m lint.terminology          # lint the paper 6 files; exit 1 on any hit

Checks the paper 6 documents and code, not the frozen Jev probe record.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "the model decides",
    "governs any model",
    "proves safe",
    "lifts the limitation",
    "model verdict",
    "sensor verdict",
)
TARGETS = ("README.md", "NOVELTY.md", "CLAIMS.md", "DECISIONS.md", "FINAL-AUDIT.md",
           "prereg/p6-*.md", "src/sensed_authority/**/*.py", "experiments/**/*.py")


def hits(text: str) -> list[str]:
    """Forbidden phrases in text, case-insensitive, whitespace-normalised."""
    flat = re.sub(r"\s+", " ", text.lower())
    return [p for p in FORBIDDEN if p in flat]


def files(root: Path = ROOT) -> list[Path]:
    return sorted({p for pattern in TARGETS for p in root.glob(pattern) if p.is_file()})


def main(root: Path = ROOT) -> int:
    bad = [(p.relative_to(root), h) for p in files(root) for h in hits(p.read_text(encoding="utf-8"))]
    for path, phrase in bad:
        print(f"terminology: {path}: forbidden phrase {phrase!r}")
    if not bad:
        print(f"terminology: ok ({len(files(root))} files)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
