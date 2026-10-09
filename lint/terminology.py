"""Terminology lint for paper 6 (brief §6): model output is an observation, never a verdict.

    python -m lint.terminology          # lint the paper 6 files; exit 1 on any hit

Checks the paper 6 documents and code, not the frozen Jev probe record. The manuscript
(paper/paper6-draft-v0.1.md) is held to further rules from the Phase D brief §5: "sensed", never
"inferred", for a field value; no "proves", "guarantees", "safe in general", "the smallest"
(reducts: "a smallest"); British spelling; no em-dashes or double hyphens. Code spans, code
blocks and pandoc citations are not prose and are skipped. The non-claims sentence quoted
verbatim from CLAIMS.md is exempt, since it states those words in order to deny them.
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
           "prereg/p6-*.md", "src/sensed_authority/**/*.py", "experiments/**/*.py",
           "paper/paper6-draft-v0.1.md")
MANUSCRIPT = "paper/paper6-draft-v0.1.md"
MANUSCRIPT_FORBIDDEN = {
    "inferred value": r"\binferred value", "inferred field": r"\binferred field",
    "value is inferred": r"\bvalue is inferred", "proves": r"\bproves\b", "proven": r"\bproven\b",
    "guarantee": r"\bguarantee", "safe in general": r"\bsafe in general\b",
    "the smallest": r"\bthe smallest\b", "\u2014": "\u2014", " -- ": r" -- ",
}
# American spellings, by stem, as whole words (British spelling, brief §5).
AMERICAN = ("behavior", "color", "favor", "honor", "labor", "modeling", "modeled", "labeled", "labeling",
            "center", "centers", "analyze", "analyzed", "minimize", "minimized", "minimizing", "optimize",
            "optimized", "summarize", "summarized", "synthesize", "synthesized", "realize", "realized",
            "recognize", "organize", "organization", "program logic is", "catalog", "defense", "license",
            "artifact", "judgment", "fulfill")


def hits(text: str) -> list[str]:
    """Forbidden phrases in text, case-insensitive, whitespace-normalised."""
    flat = re.sub(r"\s+", " ", text.lower())
    return [p for p in FORBIDDEN if p in flat]


def _prose(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"\[[^\]\n]*@[^\]\n]*\]", " ", text)
    return text


def _non_claims(root: Path) -> list[str]:
    claims = root / "CLAIMS.md"
    if not claims.exists():
        return []
    m = re.search(r"stated in the paper: (.+?\.)\s*$", claims.read_text(encoding="utf-8"), re.MULTILINE)
    return [m.group(1)] if m else []


def manuscript_hits(text: str, root: Path = ROOT) -> list[str]:
    """Manuscript-only rules; the CLAIMS.md non-claims sentence is removed first."""
    prose = _prose(text)
    for sentence in _non_claims(root):
        prose = prose.replace(sentence, " ")
    low = re.sub(r"\s+", " ", prose.lower())
    found = [name for name, pattern in MANUSCRIPT_FORBIDDEN.items() if re.search(pattern, low)]
    found += [w for w in AMERICAN if re.search(rf"\b{re.escape(w)}\b", low)]
    return found


def files(root: Path = ROOT) -> list[Path]:
    return sorted({p for pattern in TARGETS for p in root.glob(pattern) if p.is_file()})


def main(root: Path = ROOT) -> int:
    bad = [(p.relative_to(root), h) for p in files(root) for h in hits(p.read_text(encoding="utf-8"))]
    manuscript = root / MANUSCRIPT
    if manuscript.exists():
        bad += [(manuscript.relative_to(root), h) for h in manuscript_hits(manuscript.read_text(encoding="utf-8"), root)]
    for path, phrase in bad:
        print(f"terminology: {path}: forbidden phrase {phrase!r}")
    if not bad:
        print(f"terminology: ok ({len(files(root))} files)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
