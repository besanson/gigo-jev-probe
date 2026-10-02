#!/usr/bin/env python3
"""Figure 1 of paper 6: the sensing pipeline, as an SVG with no numbers in it.

    python paper/figs/fig1_pipeline.py           # write paper/figs/fig1-pipeline.svg
    python paper/figs/fig1_pipeline.py --check   # exit 1 if the committed SVG is stale

Top row: document, sensor, score, admission, sensed record, contract, verdict. Bottom row, the
Evidence Set line: a recorded field and a sensed field side by side, both entering the contract.
The figure carries no number (Phase D brief §4); text_has_no_digit() is checked on every write.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent / "fig1-pipeline.svg"
W, H = 940, 350
FONT = "DejaVu Sans, Helvetica, Arial, sans-serif"

# (label lines, sublabel, x, y, width, height, dashed)
TOP = [
    (["evidence", "document d"], "unstructured text", 10),
    (["sensor S_i", "(model)"], "writes an observation", 145),
    (["score s"], "one per candidate value", 280),
    (["admission A_i"], "thresholds fitted on split A", 415),
    (["sensed record"], "value, score, stamp, hash", 550),
    (["contract C"], "deterministic, sufficient", 685),
    (["verdict"], "allow or deny", 820),
]
BOX_W, BOX_H, TOP_Y = 110, 58, 40


def _text(x: float, y: float, s: str, size: int = 13, weight: str = "normal", anchor: str = "middle",
          style: str = "normal") -> str:
    """Text; a trailing "_x" is set as a subscript x (S_i, A_i, F_r, F_s)."""
    head = (f'<text x="{x:g}" y="{y:g}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'font-style="{style}" text-anchor="{anchor}">')
    m = re.fullmatch(r"(.*?)_([a-z])(\)?)", s)
    if m:
        tail = escape(m.group(3) or "")
        return (f'{head}{escape(m.group(1))}<tspan font-size="{size - 3}" baseline-shift="sub">{m.group(2)}</tspan>'
                f'{tail}</text>')
    return f"{head}{escape(s)}</text>"


def _box(x: float, y: float, w: float, h: float, dashed: bool = False, fill: str = "#ffffff") -> str:
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    return (f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="6" ry="6" fill="{fill}" '
            f'stroke="#222222" stroke-width="1.4"{dash}/>')


def _arrow(x1: float, y1: float, x2: float, y2: float, dashed: bool = False) -> str:
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    return (f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="#222222" stroke-width="1.4"'
            f'{dash} marker-end="url(#arrow)"/>')


def svg() -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#222222"/></marker></defs>',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>',
        _text(10, 22, "Sensing path", 13, "bold", "start"),
    ]
    sensing = {1, 2}
    for idx, (lines, sub, x) in enumerate(TOP):
        fill = "#f2f2f2" if idx in sensing else "#ffffff"
        parts.append(_box(x, TOP_Y, BOX_W, BOX_H, dashed=idx in sensing, fill=fill))
        cy = TOP_Y + BOX_H / 2 - (len(lines) - 1) * 8 + 5
        for j, line in enumerate(lines):
            parts.append(_text(x + BOX_W / 2, cy + j * 16, line, 13, "bold"))
        parts.append(_text(x + BOX_W / 2, TOP_Y + BOX_H + 16, sub, 10, style="italic"))
        if idx:
            px = TOP[idx - 1][2] + BOX_W
            parts.append(_arrow(px + 2, TOP_Y + BOX_H / 2, x - 3, TOP_Y + BOX_H / 2))

    # unknown routes to deny: from admission over the top to the verdict
    ax = TOP[3][2] + BOX_W / 2
    vx = TOP[6][2] + BOX_W / 2
    parts.append(f'<path d="M {ax:g} {TOP_Y} L {ax:g} {TOP_Y - 18} L {vx:g} {TOP_Y - 18} L {vx:g} {TOP_Y - 3}" '
                 'fill="none" stroke="#222222" stroke-width="1.2" stroke-dasharray="2,3" marker-end="url(#arrow)"/>')
    parts.append(_text((ax + vx) / 2, TOP_Y - 23, "unknown denies", 11, style="italic"))

    # Evidence Set line
    ey = 205
    parts.append(f'<line x1="10" y1="{ey - 22}" x2="{W - 10}" y2="{ey - 22}" stroke="#999999" stroke-width="1"/>')
    parts.append(_text(10, ey - 6, "Evidence Set (what the contract reads)", 13, "bold", "start"))
    row_y, row_w, row_h = ey + 12, 280, 64
    rec_x = 100
    rx = TOP[4][2] + BOX_W / 2
    sen_x = rx - row_w / 2 - 40
    parts.append(_box(rec_x, row_y, row_w, row_h))
    parts.append(_text(rec_x + row_w / 2, row_y + 22, "recorded field (F_r)", 13, "bold"))
    parts.append(_text(rec_x + row_w / 2, row_y + 40, "read from a system of record", 11))
    parts.append(_text(rec_x + row_w / 2, row_y + 55, "with its metadata", 11))
    parts.append(_box(sen_x, row_y, row_w, row_h, dashed=True, fill="#f2f2f2"))
    parts.append(_text(sen_x + row_w / 2, row_y + 22, "sensed field (F_s)", 13, "bold"))
    parts.append(_text(sen_x + row_w / 2, row_y + 40, "the admitted value of a sensed record,", 11))
    parts.append(_text(sen_x + row_w / 2, row_y + 55, "stamped with sensor, policy and document", 11))
    contract_bottom = TOP_Y + BOX_H + 22
    sx, rcx = TOP[5][2] + BOX_W / 2 - 15, TOP[5][2] + BOX_W / 2 + 25
    parts.append(_arrow(rx, contract_bottom, rx, row_y - 3, dashed=True))
    parts.append(f'<path d="M {sen_x + row_w:g} {row_y + row_h / 2:g} L {sx:g} {row_y + row_h / 2:g} L {sx:g} '
                 f'{contract_bottom:g}" fill="none" stroke="#222222" stroke-width="1.4" marker-end="url(#arrow)"/>')
    low = row_y + row_h + 16
    parts.append(f'<path d="M {rec_x + row_w / 2:g} {row_y + row_h:g} L {rec_x + row_w / 2:g} {low:g} L {rcx:g} {low:g} '
                 f'L {rcx:g} {contract_bottom:g}" fill="none" stroke="#222222" stroke-width="1.4" '
                 'marker-end="url(#arrow)"/>')
    parts.append(_text(W / 2, H - 12, "Dashed: probabilistic. Solid: deterministic. The sensor never emits a verdict.",
                       11, style="italic"))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def text_has_no_digit(doc: str) -> bool:
    texts = re.findall(r"<text[^>]*>(.*?)</text>", doc, re.DOTALL)
    return not any(re.search(r"\d", re.sub(r"<[^>]+>", "", t)) for t in texts)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    doc = svg()
    if not text_has_no_digit(doc):
        print("fig1_pipeline: a text element carries a digit", file=sys.stderr)
        return 1
    if "--check" in args:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == doc
        print(f"fig1_pipeline: {'ok' if ok else 'stale'}")
        return 0 if ok else 1
    OUT.write_text(doc, encoding="utf-8")
    print(f"fig1_pipeline: wrote {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
