#!/usr/bin/env python3
"""Fill the paper 6 manuscript from committed machine output only.

    python paper/populate.py            # write paper/paper6-draft-v0.1-populated.md
    python paper/populate.py --check    # exit 1 if the committed populated draft is stale

Every number in paper/paper6-draft-v0.1.md is a {{slot}}. build_slots() is the only source of
slot values, and gate G3 (paper-tex/gates/run_gates.py) reads the same function. Sources, by
namespace:

  (none)   results/p6.slots.json, as written by experiments/analysis_p6.py
  chk.*    out/p6/checkers/*.json (S1, S2, S3, N6), flattened
  ps.*     proof_status.json (statement tags, verbatim)
  mut.*    out/p6/mutation.json
  E0.*     the jev-v1, jev-v2, jev-v3 and exploratory slot files at tag jev-probes-final, read
           with `git show` at the commit pinned as [self] in engines.lock (the same slots
           docs/jev-note.md is filled from); E0.n_verdicts_total and E0.unsafe_total are derived
           exactly as that tag's src/jev_probe/note_all.py derives them
  flips.*  results/p6-flips.json (experiments/flips_p6.py, from the caches)
  tau.*    results/p6-E1.tau.json and results/p6-E2.tau.json (frozen thresholds, Appendix B)
  d.*      sums and counts of the slots above, computed here
  pin.*    engines.lock and the registration tags (commit identifiers)
  appB.*   Appendix B tables, rendered from experiments/constants_p6.py, the registered text
           that tests/test_p6_corpus.py checks verbatim against prereg/p6-v1.1.md
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

DRAFT_PATH = ROOT / "paper" / "paper6-draft-v0.1.md"
POPULATED_PATH = ROOT / "paper" / "paper6-draft-v0.1-populated.md"
SLOT_RE = re.compile(r"\{\{([A-Za-z0-9_.\-]+)\}\}")
SENSORS = ("jev", "llm")
NOISES = ("n00", "n10", "n30")
E0_SOURCES = {"v1": "results/jev-v1.slots.json", "v2": "results/jev-v2.slots.json",
              "v3": "results/jev-v3.slots.json", "xp": "results/jev-v2-exploratory.slots.json"}
E0_SENSOR_ROWS = (("v2", "jev"), ("v3", "llm"))  # as note_all.SENSOR_ROWS at jev-probes-final


def slot_names(text: str) -> set[str]:
    return set(SLOT_RE.findall(text))


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def _flatten(prefix: str, value: Any, out: dict[str, str]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}", v, out)
    elif isinstance(value, list):
        out[prefix] = ", ".join(str(x) for x in value)
    elif isinstance(value, bool):
        out[prefix] = "yes" if value else "no"
    elif value is not None:
        out[prefix] = str(value)


def _thousands(n: int) -> str:
    return f"{n:,}"


def _tau(v: float) -> str:
    if v > 1:
        return "never true"
    if v < 0:
        return "never false"
    return f"{v:.2f}"


def e0_slots() -> dict[str, str]:
    lock = tomllib.loads((ROOT / "engines.lock").read_text(encoding="utf-8"))["self"]
    tag_commit = _git("rev-parse", f"{lock['tag']}^{{commit}}").strip()
    if tag_commit != lock["commit"]:
        raise ValueError(f"tag {lock['tag']} is {tag_commit}, engines.lock pins {lock['commit']}")
    out: dict[str, str] = {}
    for prefix, path in E0_SOURCES.items():
        for k, v in json.loads(_git("show", f"{lock['commit']}:{path}")).items():
            out[f"E0.{prefix}.{k}"] = v
    rows = [(src, arm, n) for src, arm in E0_SENSOR_ROWS for n in NOISES]
    out["E0.n_verdicts_total"] = str(sum(int(out[f"E0.{s}.vcr.{a}.{n}.n"]) for s, a, n in rows))
    out["E0.unsafe_total"] = str(sum(int(out[f"E0.{s}.vcr_unsafe.{a}.{n}.k"]) for s, a, n in rows))
    out["d.e0_verdicts_total"] = _thousands(int(out["E0.n_verdicts_total"]))
    return out


def derived(p6: dict[str, str]) -> dict[str, str]:
    unsafe = {k[: -len(".unsafe.k")]: int(v) for k, v in p6.items()
              if k.startswith(("E1.", "E2.")) and k.endswith(".unsafe.k")}
    n = {k: int(p6[f"{k}.unsafe.n"]) for k in unsafe}
    e1 = [k for k in unsafe if k.startswith("E1.")]
    e2 = [k for k in unsafe if k.startswith("E2.")]
    rates = [float(p6[f"{k}.unsafe.rate"]) for k in unsafe]
    bss = [float(p6[f"E5.{d}.{s}.bss"]) for d in ("E1", "E2") for s in SENSORS]
    e5_p = [float(p6[f"E5.{d}.{s}.p"]) for d in ("E1", "E2") for s in SENSORS]
    h2 = [p6[f"H2.{s}.E2.{a}.verdict"] for s in SENSORS for a in (1, 2)]
    e1_bounds = [float(p6[f"E1.{s}.{x}.unsafe_bound"]) for s in SENSORS for x in NOISES]
    e1_change_bounds = [float(p6[f"E1.{s}.{x}.change_bound"]) for s in SENSORS for x in NOISES]
    e1_unsafe_rates = [float(p6[f"E1.{s}.{x}.unsafe.rate"]) for s in SENSORS for x in NOISES]
    e1_change_rates = [float(p6[f"E1.{s}.{x}.change.rate"]) for s in SENSORS for x in NOISES]
    # B over the observed verdict-change rate, in the E1 cells where any change was observed
    change_ratios = [b / r for b, r in zip(e1_change_bounds, e1_change_rates) if r]
    return {
        "d.unsafe_total": str(sum(unsafe.values())),
        "d.unsafe_e1": str(sum(unsafe[k] for k in e1)),
        "d.unsafe_e2": str(sum(unsafe[k] for k in e2)),
        "d.verdicts_total": _thousands(sum(n.values())),
        "d.verdicts_e1": _thousands(sum(n[k] for k in e1)),
        "d.verdicts_e2": _thousands(sum(n[k] for k in e2)),
        "d.cells_total": str(len(unsafe)),
        "d.cells_e1": str(len(e1)),
        "d.cells_e2": str(len(e2)),
        "d.cells_with_flip": str(sum(v > 0 for v in unsafe.values())),
        "d.max_flips_per_cell": str(max(unsafe.values())),
        "d.max_unsafe_rate": f"{max(rates):.4f}",
        "d.calls_total": _thousands(int(p6["E1.n_calls"]) + int(p6["E2.n_calls"])),
        "d.calls_e1": _thousands(int(p6["E1.n_calls"])),
        "d.calls_e2": _thousands(int(p6["E2.n_calls"])),
        "d.invalid_total": str(int(p6["E1.invalid"]) + int(p6["E2.invalid"])),
        "d.spend_total": f"{float(p6['E1.spend_usd']) + float(p6['E2.spend_usd']):.2f}",
        "d.h2_supported": str(sum(v.startswith("supported") for v in h2)),
        "d.h2_tests": str(len(h2)),
        "d.bss_min": f"{min(bss):.4f}",
        "d.bss_max": f"{max(bss):.4f}",
        "d.e5_p_max": f"{max(e5_p):.4f}",
        "d.e1_unsafe_bound_min": f"{min(e1_bounds):.4f}",
        "d.e1_unsafe_bound_max": f"{max(e1_bounds):.4f}",
        "d.e1_change_bound_max": f"{max(e1_change_bounds):.4f}",
        "d.e1_unsafe_rate_max": f"{max(e1_unsafe_rates):.4f}",
        "d.e1_vacuous": vacuous_text(p6),
        "d.e1_change_ratio_min": f"{min(change_ratios):.1f}",
        "d.e1_change_ratio_max": f"{max(change_ratios):.1f}",
        "d.e1_unsafe_ratio_min": f"{min(b / r for b, r in zip(e1_bounds, e1_unsafe_rates) if r):.0f}",
    }


def vacuous_text(p6: dict[str, str]) -> str:
    """The E1 bounds above one, in words; analysis_p6 marks them with a "vacuous" label slot."""
    names = {"jev": "Jev", "llm": "Haiku"}
    noise = {"n00": "0%", "n10": "10%", "n30": "30%"}
    found = [f"{'$B^{+}$' if b == 'unsafe_bound' else '$B$'} for {names[s]} at {noise[x]} noise"
             for s in SENSORS for x in NOISES for b in ("unsafe_bound", "change_bound")
             if p6[f"E1.{s}.{x}.{b}.label"].strip() == "vacuous"]
    return "; ".join(found) if found else "none"


def pins() -> dict[str, str]:
    lock = tomllib.loads((ROOT / "engines.lock").read_text(encoding="utf-8"))
    out = {f"pin.{k.replace('-', '_')}": v["commit"][:7] for k, v in lock.items()}
    for tag in ("prereg-p6-v1", "prereg-p6-v1.1"):
        out[f"pin.{tag.replace('-', '_').replace('.', '_')}"] = _git("rev-parse", f"{tag}^{{commit}}").strip()[:7]
    return out


def tau_slots() -> dict[str, str]:
    out: dict[str, str] = {}
    for exp in ("E1", "E2"):
        doc = json.loads((ROOT / "results" / f"p6-{exp}.tau.json").read_text(encoding="utf-8"))
        for sensor, body in doc["sensors"].items():
            for field, values in body["policy"]["thresholds"].items():
                for value, t in values.items():
                    key = f"tau.{exp}.{sensor}.{field}.{value.replace(':', '_')}"
                    out[f"{key}.true"] = _tau(t["tau_true"])
                    out[f"{key}.false"] = _tau(t["tau_false"])
    return out


def _code(s: str) -> str:
    return f"`{s}`"


def appendix_b() -> dict[str, str]:
    from experiments import constants_p6 as k

    rows = ["| field | value | question id | question (verbatim) |", "|" + "|".join("-" * w for w in (18, 22, 22, 38)) + "|"]
    for (field, value), (qid, text) in k.JEV_QUESTIONS.items():
        rows.append(f"| {_code(field)} | {_code(value)} | {_code(qid)} | {text} |")
    questions = "\n".join(rows)

    prompt = "```\n" + k.LLM_PROMPT.rstrip("\n") + "\n<rendered record text>\n```"
    rows = ["| field | `{task}` (verbatim) | `{object}` keys |", "|" + "|".join("-" * w for w in (24, 42, 34)) + "|"]
    for (exp, field), task in sorted(k.LLM_TASKS.items()):
        domain = "CH-C1" if exp == "E1" else "CH-B1"
        keys = ", ".join(_code(x) for x in k.llm_keys(exp, field))
        rows.append(f"| {_code(field)} ({domain}) | {task} | {keys} |")
    tasks = "\n".join(rows)

    def banks(table: dict) -> str:
        r = ["| field | value | validation bank | test bank |", "|" + "|".join("-" * w for w in (20, 16, 38, 38)) + "|"]
        for (field, value), (val, test) in table.items():
            r.append(f"| {_code(field)} | {_code(value)} | {' / '.join(_code(x) for x in val)} | "
                     f"{' / '.join(_code(x) for x in test)} |")
        return "\n".join(r)

    def thresholds(exp: str) -> str:
        doc = json.loads((ROOT / "results" / f"p6-{exp}.tau.json").read_text(encoding="utf-8"))
        r = ["| field | value | Jev $\\tau^{\\mathrm{true}}$ | Jev $\\tau^{\\mathrm{false}}$ | "
             "Haiku $\\tau^{\\mathrm{true}}$ | Haiku $\\tau^{\\mathrm{false}}$ |",
             # separator dashes set pandoc's relative column widths (field and value need room)
             "|" + "-" * 26 + "|" + "-" * 26 + "|" + "|".join(["-" * 12] * 4) + "|"]
        fields = doc["sensors"]["jev"]["policy"]["thresholds"]
        for field, values in fields.items():
            for value in values:
                key = f"tau.{exp}.{{s}}.{field}.{value.replace(':', '_')}"
                cells = [f"{{{{{key.format(s=s)}.{side}}}}}" for s in SENSORS for side in ("true", "false")]
                r.append(f"| {_code(field)} | {_code(value)} | " + " | ".join(cells) + " |")
        return "\n".join(r)

    return {"appB.jev_questions": questions, "appB.llm_prompt": prompt, "appB.llm_tasks": tasks,
            "appB.e1_banks": banks(k.E1_BANKS), "appB.e2_banks": banks(k.E2_BANKS),
            "appB.e1_thresholds": thresholds("E1"), "appB.e2_thresholds": thresholds("E2")}


def build_slots() -> dict[str, str]:
    p6 = json.loads((ROOT / "results" / "p6.slots.json").read_text(encoding="utf-8"))
    slots: dict[str, str] = dict(p6)
    for path in sorted((ROOT / "out" / "p6" / "checkers").glob("*.json")):
        _flatten(f"chk.{path.stem}", json.loads(path.read_text(encoding="utf-8")), slots)
    for st in json.loads((ROOT / "proof_status.json").read_text(encoding="utf-8"))["statements"]:
        slots[f"ps.{st['id']}.tag"] = st["tag"]
        slots[f"ps.{st['id']}.scope"] = st["scope"]
    mut = json.loads((ROOT / "out" / "p6" / "mutation.json").read_text(encoding="utf-8"))
    slots.update({"mut.kill_score": f"{mut['kill_score']:.3f}", "mut.killed": str(mut["killed"]),
                  "mut.survived": str(mut["survived"]), "mut.total": str(mut["total"]),
                  "mut.no_tests": str(mut["no_tests"]), "mut.threshold": str(mut["threshold"]),
                  "mut.tool": mut["tool"]})
    slots.update(e0_slots())
    flips = json.loads((ROOT / "results" / "p6-flips.json").read_text(encoding="utf-8"))["summary"]
    _flatten("flips", {k: v for k, v in flips.items() if k != "records"}, slots)
    for r in flips["records"]:
        slots[f"flips.item.{r['experiment']}" + (f".arm{r['arm']}" if r["arm"] else "")] = str(r["item"])
    slots.update(tau_slots())
    slots.update(derived(p6))
    slots.update(pins())
    slots.update(appendix_b())
    return slots


def fill(template: str, slots: dict[str, str]) -> str:
    missing = sorted(slot_names(template) - set(slots))
    if missing:
        raise KeyError(f"{len(missing)} slot(s) have no value: {missing[:20]}")
    # Appendix B blocks carry slots of their own (thresholds): fill until no slot is left.
    for _ in range(3):
        template = SLOT_RE.sub(lambda m: slots[m.group(1)], template)
        if not SLOT_RE.search(template):
            break
    return template


def used_slot_values(template: str | None = None) -> dict[str, str]:
    """Every slot the manuscript uses (including slots inside Appendix B blocks), fully filled.
    Gate G3 checks exactly these values against the PDF."""
    template = DRAFT_PATH.read_text(encoding="utf-8") if template is None else template
    slots = build_slots()
    names, frontier = set(), slot_names(template)
    while frontier:
        names |= frontier
        frontier = {n for name in frontier for n in slot_names(slots[name])} - names
    return {n: fill(slots[n], slots) for n in sorted(names)}


def populated() -> str:
    return fill(DRAFT_PATH.read_text(encoding="utf-8"), build_slots())


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    text = populated()
    if "--check" in args:
        ok = POPULATED_PATH.exists() and POPULATED_PATH.read_text(encoding="utf-8") == text
        print(f"populate: {'ok' if ok else 'stale'} ({POPULATED_PATH.relative_to(ROOT)})")
        return 0 if ok else 1
    POPULATED_PATH.write_text(text, encoding="utf-8")
    print(f"populate: wrote {POPULATED_PATH.relative_to(ROOT)} ({len(slot_names(DRAFT_PATH.read_text(encoding='utf-8')))} slots)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
