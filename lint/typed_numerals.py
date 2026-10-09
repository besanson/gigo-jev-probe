r"""Typed-numerals lint for the paper 6 manuscript (Phase D brief §4 and §6).

    python -m lint.typed_numerals        # lint paper/paper6-draft-v0.1.md; exit 1 on any hit

Every number in the manuscript must be a `{{slot}}` filled by paper/populate.py, except what
this file allows by rule. Ported in design from sarc-authority-derivation's
checkers/typed_numerals_lint.py at the engines.lock pin (commit cfb321e), adapted to paper 6's
`{{slot}}` syntax. The same rules give gate G3 its reverse direction: a number printed in the PDF
must be a slot number or survive this allowlist (`residual_numbers(..., pdf=True)`).

Stripped before any rule applies: a slot; fenced code and inline code (identifiers, commands,
verbatim registered text); double-quoted spans (verbatim quotations); URLs; link and image
targets; pandoc citations.

Allowed, applied to what remains:

1. Structural numbers: Section, Sections, Appendix, Table, Figure, Proposition, Claim, Phase,
   Step and Item references; E2's arm labels ("arm 1", "arm 2"); a repository issue number
   ("issue #2"); a registration section ("§5.2"); "paper 5" and "papers 1 to 5" in the series; a heading's or an
   ordered list item's own number; in the PDF, a section heading's number at the start of a line
   and a numeric citation such as "[3]" or "[3, 7]".
2. Years 1900 to 2099 and ISO dates (the registered date set D and the run dates).
3. Identifiers: any token that contains a letter (E1, H2, S1, B12, F13, CH-C1, p6-v1.1,
   jev-1.13.0, SHA-256, a commit hash), except a number in scientific notation, which is a
   number.
4. Registered design parameters, by literal value, each traced to prereg/p6-v1.1.md: noise
   levels 0, 10 and 30% (also 0.10 and 0.30), the admission ceilings 1% and 5%, the 95% interval
   level, alpha and q of 0.05, split sizes (150, 300, 700, 1,000 items), the CH-C1 population
   (27,000 tuples), the E4 witness size (10,000 items), the registered call counts (12,000 and
   24,000), the seeds 20261101 to 20261108, the 30-day approval window, the score range [0, 1],
   the USD 60 cap, the arm health rule (first 20 validation records, more than 2 invalid, 5%),
   and the sensor name Claude Haiku 4.5.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFT_PATH = ROOT / "paper" / "paper6-draft-v0.1.md"

STRIP_FIRST = [
    re.compile(r"\{\{[A-Za-z0-9_.\-]+\}\}"),
    re.compile(r"```.*?```", re.DOTALL),
    re.compile(r"`[^`\n]*`"),
    re.compile(r'"[^"\n]*"'),
    re.compile(r"“[^”\n]*”"),
    re.compile(r"https?://\S+"),
    re.compile(r"\]\([^)\s]*\)"),
    re.compile(r"\[[^\]\n]*@[^\]\n]*\]"),
]

STRUCTURAL = [
    re.compile(r"\b(?:Sections?|Appendix|Tables?|Figures?|Propositions?|Claims?|Phase|Steps?|Items?)\s+"
               r"\d+(?:\.\d+)*(?:\s*(?:to|and|-)\s*\d+(?:\.\d+)*)?\b"),
    re.compile(r"\b[Pp]apers?\s+\d+(?:\s*(?:to|and|-)\s*\d+)?\b"),
    re.compile(r"\b[Aa]rms?\s+\d\b"),
    re.compile(r"\b[Ii]ssues?\s+#\d+\b"),
    re.compile(r"§\s?\d+(?:\.\d+)*"),
    re.compile(r"^#+\s*\d+(?:\.\d+)*\.?\s", re.MULTILINE),
    re.compile(r"^\s*\d+\.\s", re.MULTILINE),
]

STRUCTURAL_PDF = [
    re.compile(r"^\s*\d+(?:\.\d+)*\s+(?=[A-Z])", re.MULTILINE),
    re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]"),
]

DATES = [
    re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|"
               r"November|December)\s+(?:19|20)\d{2}\b"),
    re.compile(r"\b(?:19|20)\d{2}\b"),
]

REGISTERED = [
    re.compile(r"(?<![\d.])(?:0|10|30)%"),
    re.compile(r"(?<![\d.])0\.(?:10|30)(?!\d)"),
    re.compile(r"(?<![\d.])[15]%"),
    re.compile(r"(?<![\d.])95%"),
    re.compile(r"(?<![\d.])0\.05(?!\d)"),
    re.compile(r"(?<![\d.,])(?:150|300|700|1,000|1000|27,000|10,000|12,000|24,000)(?!\d|,\d)"),
    re.compile(r"\b202611(?:0[1-8])\b"),
    re.compile(r"\b30(?:-day| days)\b"),
    re.compile(r"\[0,\s*1\]"),
    re.compile(r"\bUSD 60(?:\.00)?\b"),
    re.compile(r"\bfirst 20 validation\b"),
    re.compile(r"\bmore than 2 invalid\b"),
    re.compile(r"\bHaiku 4\.5\b"),
]

SCI = re.compile(r"[-+]?\d+(?:\.\d+)?[eE][-+]?\d+")
NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?(?!\d)|\d+\.\d+(?:[eE][-+]?\d+)?(?!\d)|\d+[eE][-+]?\d+(?!\d)|\d+(?!\d)")


def _blank(text: str, patterns: list[re.Pattern]) -> str:
    for p in patterns:
        text = p.sub(lambda m: "".join(c if c == "\n" else " " for c in m.group(0)), text)
    return text


def _is_identifier(token: str) -> bool:
    core = token.strip("()[]{},;:.!?\"'")
    if SCI.fullmatch(core):
        return False
    return bool(re.search(r"[A-Za-z]", core))


def residual(text: str, pdf: bool = False) -> list[tuple[int, str]]:
    """(offset, token) for every token left with a digit after stripping and the allowlist."""
    text = _blank(text, STRIP_FIRST)
    text = _blank(text, STRUCTURAL + (STRUCTURAL_PDF if pdf else []) + DATES + REGISTERED)
    out = []
    for m in re.finditer(r"\S+", text):
        tok = m.group(0)
        if re.search(r"\d", tok) and not _is_identifier(tok):
            out.append((m.start(), tok))
    return out


def residual_numbers(text: str, pdf: bool = False) -> list[str]:
    """The numbers inside the residual tokens (what gate G3 checks against the slots)."""
    return [n for _, tok in residual(text, pdf) for n in NUMBER.findall(tok)]


def front_matter_and_body(text: str) -> str:
    """YAML keys are not prose; the values (title, abstract) are linted."""
    if text.startswith("---\n"):
        end = text.index("\n---\n", 4)
        head = re.sub(r"(?m)^[a-z_]+:", lambda m: " " * len(m.group(0)), text[:end])
        return head + text[end:]
    return text


def find_violations(text: str) -> list[dict]:
    text = front_matter_and_body(text)
    out = []
    for offset, tok in residual(text):
        line_no = text.count("\n", 0, offset) + 1
        line = text.splitlines()[line_no - 1].strip()
        out.append({"line": line_no, "token": tok, "context": line[:160]})
    return out


def main(path: Path = DRAFT_PATH) -> int:
    violations = find_violations(path.read_text(encoding="utf-8"))
    for v in violations:
        print(f"typed_numerals: {path.relative_to(ROOT)}:{v['line']}: {v['token']!r} in: {v['context']}")
    if not violations:
        print(f"typed_numerals: ok ({path.relative_to(ROOT)})")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
