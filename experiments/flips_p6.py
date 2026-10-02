"""Item-level record of every deny-to-allow change in E1 and E2 (test split), from the caches only.

    python -m experiments.flips_p6            # write results/p6-flips.json
    python -m experiments.flips_p6 --check    # exit 1 if the committed file is not current

Descriptive evidence for the paper's discussion of the flips (Phase D brief §4, 8.3). Reads the
raw caches, the frozen threshold files and the pinned siblings, exactly as
experiments/analysis_p6.py does; calls no model. Each verdict counted in results/p6.md's unsafe
columns appears here once, with the record it came from, so the flips can be traced to the
cached responses (responses/p6-E1.jsonl, responses/p6-E2.jsonl) by experiment, sensor, item and
noise level.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from experiments.analysis_p6 import load_policies, readings
from experiments.constants_p6 import ROOT, SENSORS, cache_path, tau_path
from experiments.corpus_p6 import (
    approval_token_from_assertion,
    build_items,
    e1_outcome,
    e1_truth,
    e2_outcome,
    perturbation,
    truth_values,
)
from experiments.run_p6 import cached_calls
from jev_probe.cache import Cache

FLIPS_PATH = ROOT / "results" / "p6-flips.json"
REDUCTS = ("R_branch", "R_env")


def flips() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for exp in ("E1", "E2"):
        items = {it.i: it for it in build_items(exp) if it.split == "test"}
        calls = cached_calls(Cache(cache_path(exp)))
        pol = load_policies(tau_path(exp))
        reads = readings(exp, list(items.values()), calls, {s: pol[s]["policy"]["thresholds"] for s in SENSORS})
        for (sensor, label, i, noise), adm in sorted(reads.items()):
            it = items[i]
            arm = None if exp == "E1" else int(label.rsplit(".", 1)[1])
            cases = [(None, e1_outcome(it, adm))] if exp == "E1" else [(r, e2_outcome(it, r, adm)) for r in REDUCTS]
            for reduct, (_, unsafe) in cases:
                if not unsafe:
                    continue
                truth = truth_values(it) if exp == "E1" else truth_values(it, arm)
                row: dict[str, Any] = {
                    "experiment": exp, "label": label, "arm": arm, "sensor": sensor, "item": i,
                    "noise": noise, "reduct": reduct,
                    "perturbation": {f: perturbation(it, f, noise, arm) for f in adm},
                    "admitted": adm, "truth": truth,
                }
                if exp == "E1":
                    _, request_date = e1_truth(it)
                    row["approval_token"] = {
                        "true": it.t.approval_token,
                        "from_admitted": approval_token_from_assertion(adm["approval_assertion"], request_date),
                    }
                out.append(row)
    return out


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    records = sorted({(r["experiment"], r["arm"] or 0, r["item"]) for r in rows})
    per_exp = {e: sum(r["experiment"] == e for r in rows) for e in ("E1", "E2")}
    e2 = [r for r in rows if r["experiment"] == "E2"]
    e2_keys = {(r["label"], r["item"], r["noise"], r["reduct"]) for r in e2}
    return {
        "flips": len(rows),
        "flips_by_experiment": per_exp,
        "distinct_records": len(records),
        "records": [{"experiment": e, "arm": a or None, "item": i} for e, a, i in records],
        "all_on_contradictory_approval_statement": all(
            r["perturbation"]["approval_assertion"] == "contradictory" for r in rows),
        "all_wrong_field_is_approval_assertion": all(
            r["admitted"]["approval_assertion"] != r["truth"]["approval_assertion"]
            and all(r["admitted"][f] == r["truth"][f] for f in r["admitted"] if f != "approval_assertion")
            for r in rows),
        "e2_both_sensors_on_every_flip": all(
            sum((r["label"], r["item"], r["noise"], r["reduct"]) == k for r in e2) == len(SENSORS) for k in e2_keys),
        "e2_both_reducts_on_every_flip": all(
            {r["reduct"] for r in e2 if (r["label"], r["item"], r["noise"]) == (k[0], k[1], k[2])} == set(REDUCTS)
            for k in e2_keys),
    }


def document() -> str:
    rows = flips()
    doc = {"source": "experiments/flips_p6.py (caches and frozen thresholds only; no model call)",
           "summary": summary(rows), "flips": rows}
    return json.dumps(doc, indent=1, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    text = document()
    if "--check" in args:
        ok = FLIPS_PATH.exists() and FLIPS_PATH.read_text(encoding="utf-8") == text
        print(f"flips_p6: {'ok' if ok else 'stale'} ({FLIPS_PATH.relative_to(ROOT)})")
        return 0 if ok else 1
    FLIPS_PATH.write_text(text, encoding="utf-8")
    print(f"flips_p6: wrote {FLIPS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
