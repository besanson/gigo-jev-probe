"""jev-v2 EXPLORATORY, POST HOC re-score of the LLM arm from the committed cache (DEVIATIONS KI-1).

    python -m jev_probe.exploratory_v2   # write results/jev-v2-exploratory.md; no API call

This is not the registered test. The parser was changed after the data were seen: the
registered parser (§6 B) accepts bare JSON only, and every Haiku reply was fenced. Here a reply
is scored by stripping Markdown code fences and taking the first JSON object; anything else is
invalid. The replies are read in the registered order (first request, then the one
re-request), and the first that parses gives the score.

The LLM arm's thresholds are refitted on the validation cache with this parser at the
registered 1% ceiling. Jev's thresholds are the frozen ones from results/jev-v2.tau.json, and
Jev's scores are the registered ones. Nothing here is imported by analysis_v2.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from jev_probe.analysis import SLOT_RE, fill, fmt, fmt_p
from jev_probe.analysis_v2 import (
    NOISES,
    Data,
    cp_slots,
    h2,
    load,
    outcomes,
    paired,
    set_tau,
    tau_from_json,
    validation_rows,
)
from jev_probe.constants_v2 import BOOTSTRAP_B, CACHE_PATH, FP_CEILING, ROOT, TAU_PATH
from jev_probe.corpus_v2 import Item, build_items

OUT_PATH = ROOT / "results" / "jev-v2-exploratory.md"
TEMPLATE_PATH = ROOT / "results" / "jev-v2-exploratory.template.md"
SLOTS_JSON_PATH = ROOT / "results" / "jev-v2-exploratory.slots.json"
NOISE_NAME = {"n00": "0%", "n10": "10%", "n30": "30%"}
HEADER = "EXPLORATORY, POST HOC, NOT THE REGISTERED TEST. Parser changed after data were seen."

FENCE_RE = re.compile(r"```[A-Za-z0-9_-]*")


def reply_text(raw: str | None) -> tuple[str | None, str | None]:
    """(text of the reply, stop_reason), or (None, None) when the body is not a message."""
    try:
        body = json.loads(raw) if raw else None
    except ValueError:
        return None, None
    if not isinstance(body, dict) or not isinstance(body.get("content"), list):
        return None, None
    text = "".join(b.get("text", "") for b in body["content"] if isinstance(b, dict) and b.get("type") == "text")
    return text, body.get("stop_reason")


def parse_lenient(raw: str | None) -> float | None:
    """Strip code fences, take the first JSON object, read p_valid in [0, 1]; else invalid."""
    text, stop = reply_text(raw)
    if text is None or stop == "refusal":
        return None
    text = FENCE_RE.sub("", text)
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start)
    except ValueError:
        return None
    v = obj.get("p_valid") if isinstance(obj, dict) else None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) and 0.0 <= v <= 1.0 else None


def rescore(data: Data) -> tuple[Data, dict[str, int]]:
    """Copy of data with every LLM call re-scored by the lenient parser, plus reply counts."""
    by_call: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for a in data.attempts:
        if a["arm"] == "llm" and a["http_status"] == 200:
            by_call.setdefault((a["i"], a["noise"]), []).append(a)
    counts = {"replies": 0, "replies_recovered": 0, "replies_truncated": 0, "replies_fenced": 0}
    calls = dict(data.calls)
    for (arm, i, noise), c in data.calls.items():
        if arm != "llm":
            continue
        score = None
        for a in sorted(by_call.get((i, noise), []), key=lambda a: (a["request_n"], a["attempt"])):
            text, stop = reply_text(a["response_body"])
            s = parse_lenient(a["response_body"])
            counts["replies"] += 1
            counts["replies_recovered"] += s is not None
            counts["replies_truncated"] += stop == "max_tokens"
            counts["replies_fenced"] += bool(text and "```" in text)
            if score is None:
                score = s
        calls[(arm, i, noise)] = {**c, "score": score, "status": "ok" if score is not None else "invalid"}
    return Data(calls, data.attempts, data.retries, data.run_events, data.manifests), counts


def compute(cache_path: Path = CACHE_PATH, tau_path: Path = TAU_PATH, *, items: list[Item] | None = None,
            bootstrap_b: int = BOOTSTRAP_B) -> dict[str, str]:
    data, counts = rescore(load(cache_path))
    items = build_items() if items is None else list(items)
    taus = tau_from_json(json.loads(tau_path.read_text(encoding="utf-8")))
    taus["llm"] = set_tau(validation_rows(data.calls, items, "llm"), FP_CEILING)
    out: dict[str, str] = {}
    for k, v in counts.items():
        out[f"x.{k}"] = fmt(v)
    out["x.replies_recovered.rate"] = fmt(counts["replies_recovered"] / counts["replies"] if counts["replies"] else math.nan)
    llm_calls = [c for (a, _, _), c in data.calls.items() if a == "llm"]
    out["x.records"] = fmt(len(llm_calls))
    out["x.records_recovered"] = fmt(sum(c["score"] is not None for c in llm_calls))
    out["x.records_recovered.rate"] = fmt(sum(c["score"] is not None for c in llm_calls) / len(llm_calls)
                                          if llm_calls else math.nan)
    val = validation_rows(data.calls, items, "llm")
    out["x.tau.llm.true"] = fmt(taus["llm"]["tau_true"])
    out["x.tau.llm.false"] = fmt(taus["llm"]["tau_false"])
    out["x.tau.llm.n_scored"] = fmt(sum(s is not None for s, _ in val))
    out["x.tau.llm.n_validation"] = fmt(len(val))
    out["x.tau.jev.true"] = fmt(taus["jev"]["tau_true"])
    out["x.tau.jev.false"] = fmt(taus["jev"]["tau_false"])
    oc = {(arm, n): outcomes(data, items, taus, arm, n) for arm in ("jev", "llm") for n in NOISES}
    for (arm, n), os_ in oc.items():
        p = f"{arm}.{n}"
        cp_slots(out, f"x.vcr.{p}", sum(o.change for o in os_), len(os_))
        cp_slots(out, f"x.unsafe.{p}", sum(o.unsafe for o in os_), len(os_))
        cp_slots(out, f"x.failclosed.{p}", sum(o.failclosed for o in os_), len(os_))
        cp_slots(out, f"x.abstain.{p}", sum(not o.definite for o in os_), len(os_))
    r2 = h2(paired(oc[("jev", "n30")], oc[("llm", "n30")]), bootstrap_b)
    for k in ("jev_rate", "llm_rate", "estimate", "b", "c", "n", "ci_lo", "ci_hi"):
        out[f"x.H2.{k}"] = fmt(r2[k])
    out["x.H2.p"] = fmt_p(r2["p"])
    out["x.bootstrap_b"] = fmt(bootstrap_b)
    return out


def s(name: str) -> str:
    return "{{" + name + "}}"


def cp(prefix: str) -> str:
    return f"{s(prefix + '.rate')} [{s(prefix + '.lo')}, {s(prefix + '.hi')}] ({s(prefix + '.k')}/{s(prefix + '.n')})"


def build() -> str:
    L: list[str] = []
    a = L.append
    a("# jev-v2 exploratory re-score of the LLM arm")
    a("")
    a(f"**{HEADER}**")
    a("")
    a("> Generated by `python -m jev_probe.exploratory_v2` from the committed cache `responses/jev-v2.jsonl`; "
      "no API call is made. Why: `prereg/DEVIATIONS.md` KI-1. The registered results in "
      "`results/jev-v2.md` are unchanged and remain the record of the registered test.")
    a("")
    a("Lenient parser: strip Markdown code fences, take the first JSON object, read `p_valid` in [0, 1]; "
      "anything else is invalid. Replies are read in the registered order (first request, then the "
      "re-request); the first that parses gives the score. The LLM arm's thresholds are refitted on "
      "the validation split with this parser at the registered 1% ceiling. Jev keeps its frozen "
      "thresholds and registered scores.")
    a("")
    a("## Replies recovered")
    a("")
    a("| measure | value |")
    a("|---|---|")
    a(f"| LLM replies (HTTP 200, incl. re-requests) | {s('x.replies')} |")
    a(f"| replies in a code fence | {s('x.replies_fenced')} |")
    a(f"| replies truncated at max_tokens | {s('x.replies_truncated')} |")
    a(f"| replies recovered by the lenient parser | {s('x.replies_recovered')} "
      f"(fraction {s('x.replies_recovered.rate')}) |")
    a(f"| records with a lenient score | {s('x.records_recovered')} of {s('x.records')} "
      f"(fraction {s('x.records_recovered.rate')}) |")
    a("")
    a("## Thresholds")
    a("")
    a("| arm | tau_true | tau_false | source |")
    a("|---|---|---|---|")
    a(f"| A: Jev | {s('x.tau.jev.true')} | {s('x.tau.jev.false')} | frozen, results/jev-v2.tau.json |")
    a(f"| B: Claude Haiku 4.5 | {s('x.tau.llm.true')} | {s('x.tau.llm.false')} | refitted post hoc on "
      f"{s('x.tau.llm.n_scored')} of {s('x.tau.llm.n_validation')} validation records |")
    a("")
    a("## Verdict change (test split, Clopper-Pearson 95%)")
    a("")
    a("| arm | noise | verdict-change rate | unsafe (deny to allow) | fail-closed (allow to deny) | abstention |")
    a("|---|---|---|---|---|---|")
    for arm, label in (("jev", "A: Jev"), ("llm", "B: Claude Haiku 4.5")):
        for n in NOISES:
            p = f"{arm}.{n}"
            a(f"| {label} | {NOISE_NAME[n]} | {cp(f'x.vcr.{p}')} | {cp(f'x.unsafe.{p}')} | "
              f"{cp(f'x.failclosed.{p}')} | {cp(f'x.abstain.{p}')} |")
    a("")
    a("## H2 recomputed (exploratory; not Holm-adjusted, not a registered test)")
    a("")
    a("| comparison | estimate | 95% CI (paired bootstrap) | exact McNemar p |")
    a("|---|---|---|---|")
    a(f"| Jev vs LLM at 30% noise | Jev {s('x.H2.jev_rate')} vs LLM {s('x.H2.llm_rate')}; difference "
      f"{s('x.H2.estimate')} (b = {s('x.H2.b')}, c = {s('x.H2.c')}, n = {s('x.H2.n')}) | "
      f"[{s('x.H2.ci_lo')}, {s('x.H2.ci_hi')}] | {s('x.H2.p')} |")
    a("")
    a(f"Bootstrap: {s('x.bootstrap_b')} resamples, the registered seed. No verdict is stated: the parser "
      "and the LLM thresholds were chosen after the data were seen.")
    a("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=CACHE_PATH)
    ap.add_argument("--tau", type=Path, default=TAU_PATH)
    args = ap.parse_args(argv)
    template = build()
    slots = compute(args.cache, args.tau)
    filled = fill(template, slots)
    TEMPLATE_PATH.write_text(template, encoding="utf-8")
    OUT_PATH.write_text(filled, encoding="utf-8")
    SLOTS_JSON_PATH.write_text(json.dumps(slots, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"exploratory_v2: wrote {OUT_PATH} ({len(SLOT_RE.findall(template))} slots filled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
