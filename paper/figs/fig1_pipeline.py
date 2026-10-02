#!/usr/bin/env python3
"""Figure 1 of paper 6: the sensing pipeline, with no numbers in it.

    python paper/figs/fig1_pipeline.py           # write fig1-pipeline.svg and fig1-pipeline.pdf
    python paper/figs/fig1_pipeline.py --check   # exit 1 if either committed file is stale

Top row: document, sensor, score, admission, sensed record, contract, verdict. Bottom row, the
Evidence Set line: a recorded field and a sensed field side by side, both entering the contract.
The figure carries no number (Phase D brief §4); text_has_no_digit() checks every label.

Round-one finding F2: both files are drawn by matplotlib (pinned in pyproject.toml), which
embeds its own bundled DejaVu fonts, with fixed metadata and SOURCE_DATE_EPOCH, so the PDF that
LaTeX includes is the same bytes on every machine. No rsvg-convert, no system fonts.
"""

from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = Path(__file__).resolve().parent
SVG_OUT = HERE / "fig1-pipeline.svg"
PDF_OUT = HERE / "fig1-pipeline.pdf"
SOURCE_DATE_EPOCH = "1786609963"  # the release kit's content-stable epoch (paper-tex/gates/run_gates.py)
W, H = 940, 350
DPI = 100

# (label lines, sublabel, left x); mathtext gives the subscripts
TOP = [
    (["evidence", "document $d$"], "unstructured text", 10),
    (["sensor $S_i$", "(model)"], "writes an\nobservation", 145),
    (["score $s$"], "one per\ncandidate value", 280),
    (["admission $A_i$"], "thresholds fitted\non split A", 415),
    (["sensed record"], "value, score,\nstamp, hash", 550),
    (["contract $C$"], "deterministic,\nsufficient", 685),
    (["verdict"], "allow or deny", 820),
]
SENSING = {1, 2}  # probabilistic steps, drawn dashed
BOX_W, BOX_H, TOP_Y = 110, 58, 40
INK, SHADE, RULE = "#222222", "#f2f2f2", "#999999"
LABELS: list[str] = []


def _text(ax, x, y, s, size=10, weight="normal", ha="center", style="normal") -> None:
    LABELS.append(s)
    ax.text(x, y, s, fontsize=size, fontweight=weight, ha=ha, va="center", style=style, color=INK,
            family="DejaVu Sans")


def _box(ax, x, y, w, h, dashed=False, fill="#ffffff") -> None:
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=6", linewidth=1.2,
                                edgecolor=INK, facecolor=fill, linestyle=(0, (4, 3)) if dashed else "-"))


def _arrow(ax, points, dashed=False, style=None) -> None:
    for (x1, y1), (x2, y2) in zip(points[:-2], points[1:-1]):
        ax.plot([x1, x2], [y1, y2], color=INK, linewidth=1.2,
                linestyle=style or ((0, (4, 3)) if dashed else "-"), solid_capstyle="butt")
    ax.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle="-|>", mutation_scale=10, color=INK,
                                 linewidth=1.2, linestyle=style or ((0, (4, 3)) if dashed else "-"),
                                 shrinkA=0, shrinkB=0))


def draw():
    LABELS.clear()
    plt.rcParams.update({"svg.hashsalt": "paper6-fig1", "svg.fonttype": "path", "pdf.fonttype": 42,
                         "font.family": "DejaVu Sans", "mathtext.fontset": "dejavusans"})
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")

    _text(ax, 10, 20, "Sensing path", 9.5, "bold", "left")
    for idx, (lines, sub, x) in enumerate(TOP):
        _box(ax, x, TOP_Y, BOX_W, BOX_H, dashed=idx in SENSING, fill=SHADE if idx in SENSING else "#ffffff")
        cy = TOP_Y + BOX_H / 2 - (len(lines) - 1) * 8
        for j, line in enumerate(lines):
            _text(ax, x + BOX_W / 2, cy + j * 16, line, 9, "bold")
        for j, part in enumerate(sub.split("\n")):
            _text(ax, x + BOX_W / 2, TOP_Y + BOX_H + 12 + j * 11, part, 6.5, style="italic")
        if idx:
            px = TOP[idx - 1][2] + BOX_W
            _arrow(ax, [(px + 2, TOP_Y + BOX_H / 2), (x - 3, TOP_Y + BOX_H / 2)])

    ax_x, vx = TOP[3][2] + BOX_W / 2, TOP[6][2] + BOX_W / 2
    _arrow(ax, [(ax_x, TOP_Y), (ax_x, TOP_Y - 18), (vx, TOP_Y - 18), (vx, TOP_Y - 3)], style=(0, (1, 2.5)))
    _text(ax, (ax_x + vx) / 2, TOP_Y - 25, "unknown denies", 7.5, style="italic")

    ey = 205
    ax.plot([10, W - 10], [ey - 22, ey - 22], color=RULE, linewidth=0.8)
    _text(ax, 10, ey - 8, "Evidence Set (what the contract reads)", 9.5, "bold", "left")
    row_y, row_w, row_h, rec_x = ey + 12, 280, 64, 100
    rx = TOP[4][2] + BOX_W / 2
    sen_x = rx - row_w / 2 - 40
    _box(ax, rec_x, row_y, row_w, row_h)
    _text(ax, rec_x + row_w / 2, row_y + 18, "recorded field ($F_r$)", 9, "bold")
    _text(ax, rec_x + row_w / 2, row_y + 37, "read from a system of record", 7.5)
    _text(ax, rec_x + row_w / 2, row_y + 51, "with its metadata", 7.5)
    _box(ax, sen_x, row_y, row_w, row_h, dashed=True, fill=SHADE)
    _text(ax, sen_x + row_w / 2, row_y + 18, "sensed field ($F_s$)", 9, "bold")
    _text(ax, sen_x + row_w / 2, row_y + 37, "the admitted value of a sensed record,", 7.5)
    _text(ax, sen_x + row_w / 2, row_y + 51, "stamped with sensor, policy and document", 7.5)
    bottom = TOP_Y + BOX_H + 30
    sx, rcx = TOP[5][2] + BOX_W / 2 - 15, TOP[5][2] + BOX_W / 2 + 25
    _arrow(ax, [(rx, bottom), (rx, row_y - 3)], dashed=True)
    _arrow(ax, [(sen_x + row_w, row_y + row_h / 2), (sx, row_y + row_h / 2), (sx, bottom)])
    low = row_y + row_h + 16
    _arrow(ax, [(rec_x + row_w / 2, row_y + row_h), (rec_x + row_w / 2, low), (rcx, low), (rcx, bottom)])
    _text(ax, W / 2, H - 12, "Dashed: probabilistic. Solid: deterministic. The sensor never emits a verdict.",
          7.5, style="italic")
    return fig


def render() -> dict[Path, bytes]:
    os.environ["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    fig = draw()
    out = {}
    for path, fmt, meta in ((SVG_OUT, "svg", {"Date": None, "Creator": None}),
                            (PDF_OUT, "pdf", {"CreationDate": None, "ModDate": None, "Creator": None,
                                              "Producer": None})):
        buf = io.BytesIO()
        fig.savefig(buf, format=fmt, metadata=meta)
        out[path] = buf.getvalue()
    plt.close(fig)
    return out


def text_has_no_digit(labels: list[str] | None = None) -> bool:
    if labels is None:
        draw()
        labels = LABELS
    return not any(re.search(r"\d", s) for s in labels)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    files = render()
    if not text_has_no_digit(LABELS):
        print("fig1_pipeline: a label carries a digit", file=sys.stderr)
        return 1
    if "--check" in args:
        stale = [p.name for p, b in files.items() if not p.exists() or p.read_bytes() != b]
        print(f"fig1_pipeline: {'stale ' + str(stale) if stale else 'ok'}")
        return 1 if stale else 0
    for path, data in files.items():
        path.write_bytes(data)
    print(f"fig1_pipeline: wrote {', '.join(p.name for p in files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
