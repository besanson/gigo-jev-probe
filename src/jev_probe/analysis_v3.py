"""jev-v3 analysis (prereg/jev-v3.md §5–§7). Reads ONLY the jev-v3 cache (arm B), the jev-v2
cache and frozen thresholds (arm A, carried unchanged), the jev-v3 thresholds and the pinned
sibling. It never calls a model.

    python -m jev_probe.analysis_v3          # fill results/jev-v3.md
    python -m jev_probe.analysis_v3 --check  # compute, verify every slot fills, write nothing

H2 and H3 use the jev-v2 §9 procedures (analysis_v2.h2 / h3) and are Holm-corrected as a
family of two. H1 is not re-tested.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from jev_probe.analysis import SLOT_RE, fill, fmt, fmt_p
from jev_probe.analysis_v2 import (
    NE,
    NOISES,
    Data,
    call_cost,
    cp_slots,
    h2,
    h3,
    load,
    outcomes,
    paired,
    quantile,
    set_tau,
    tau_from_json,
    two_way,
    validation_rows,
)
from jev_probe.constants_v2 import BOOTSTRAP_B, BOOTSTRAP_SEED
from jev_probe.constants_v2 import CACHE_PATH as V2_CACHE_PATH
from jev_probe.constants_v2 import TAU_PATH as V2_TAU_PATH
from jev_probe.constants_v3 import (
    CACHE_PATH,
    CARRIED_JEV_H2_K,
    CARRIED_JEV_H2_N,
    RESULTS_PATH,
    SLOTS_JSON_PATH,
    TAU_PATH,
    TEMPLATE_PATH,
)
from jev_probe.corpus_v2 import Item, build_items
from jev_probe.stats import holm

NOISE_NAME = {"n00": "0%", "n10": "10%", "n30": "30%"}


def merged(v2: Data, v3: Data) -> Data:
    """Arm A from jev-v2, arm B from jev-v3; nothing else."""
    calls = {k: c for k, c in v2.calls.items() if k[0] == "jev"}
    calls.update({k: c for k, c in v3.calls.items() if k[0] == "llm"})
    attempts = [a for a in v2.attempts if a["arm"] == "jev"] + [a for a in v3.attempts if a["arm"] == "llm"]
    return Data(calls, attempts, v3.retries, v3.run_events, v3.manifests)


def reply_stats(v3: Data) -> dict[str, int]:
    n = trunc = fenced = 0
    for a in v3.attempts:
        if a["arm"] != "llm" or a["http_status"] != 200:
            continue
        try:
            body = json.loads(a["response_body"])
        except (TypeError, ValueError):
            continue
        n += 1
        trunc += body.get("stop_reason") == "max_tokens"
        text = "".join(b.get("text", "") for b in body.get("content", []) if isinstance(b, dict))
        fenced += "```" in text
    return {"replies": n, "truncated": trunc, "fenced": fenced}


def compute(cache_path: Path = CACHE_PATH, tau_path: Path = TAU_PATH, *, v2_cache_path: Path = V2_CACHE_PATH,
            v2_tau_path: Path = V2_TAU_PATH, items: list[Item] | None = None,
            bootstrap_b: int = BOOTSTRAP_B) -> dict[str, str]:
    v3 = load(cache_path)
    data = merged(load(v2_cache_path), v3)
    items = build_items() if items is None else list(items)
    test = [it for it in items if it.split == "test"]
    out: dict[str, str] = {}

    # run
    last = v3.run_events[-1]["manifest"] if v3.run_events else {}
    status = str(last.get("status", "none"))
    out["run.status"] = status
    out["run.n_segments"] = fmt(len({e["segment"] for e in v3.run_events}))
    out["run.n_calls.llm"] = fmt(sum(1 for (a, _, _) in data.calls if a == "llm"))
    out["run.n_attempts"] = fmt(sum(1 for a in v3.attempts if a["arm"] == "llm"))
    out["run.n_retries"] = fmt(sum(1 for r in v3.retries if not r.get("exhausted")))
    out["run.spend_usd"] = fmt(sum(float(a["charged_usd"]) for a in v3.attempts), 6)
    out["run.model_versions.llm"] = ", ".join(sorted({c["returned_model"] for (a, _, _), c in data.calls.items()
                                                      if a == "llm"})) or "none"
    out["run.model_version_changed"] = fmt(bool(last.get("model_version_changed", False)))
    for k in ("prereg_commit", "generator_sha256", "llm_prompt_sha256", "tau_sha256"):
        out[f"run.{k}"] = str(last.get(k, "n/a"))
    out["run.sdk.llm"] = str(last.get("sdks", {}).get("anthropic", "n/a"))
    for check in ("smoke", "validation"):
        h = last.get("health", {}).get(check)
        out[f"health.{check}.invalid"] = fmt(h["invalid"]) if h else "not reached"
        out[f"health.{check}.n"] = fmt(h["n"]) if h else "not reached"
        out[f"health.{check}.stopped"] = fmt(h["stopped"]) if h else "not reached"

    # validity and replies
    llm_calls = [c for (a, _, _), c in data.calls.items() if a == "llm"]
    k_inv = sum(c["status"] == "invalid" for c in llm_calls)
    out["invalid.llm"] = fmt(k_inv)
    out["invalid.llm.rate"] = fmt(k_inv / len(llm_calls) if llm_calls else math.nan)
    for k, v in reply_stats(v3).items():
        out[f"replies.llm.{k}"] = fmt(v)

    # thresholds
    taus = tau_from_json(json.loads(v2_tau_path.read_text(encoding="utf-8")))
    taus = {"jev": taus["jev"]}
    has_tau = tau_path.exists()
    if has_tau:
        taus["llm"] = tau_from_json(json.loads(tau_path.read_text(encoding="utf-8")))["llm"]
    val = validation_rows(data.calls, items, "llm")
    out["tau.llm.true"] = fmt(taus["llm"]["tau_true"]) if has_tau else "not written"
    out["tau.llm.false"] = fmt(taus["llm"]["tau_false"]) if has_tau else "not written"
    out["tau.llm.recomputed_match"] = fmt(set_tau(val) == taus["llm"]) if has_tau else "n/a"
    out["tau.llm.n_validation"] = fmt(len(val))
    out["tau.llm.n_scored"] = fmt(sum(s is not None for s, _ in val))
    out["tau.jev.true"] = fmt(taus["jev"]["tau_true"])
    out["tau.jev.false"] = fmt(taus["jev"]["tau_false"])

    # verdict change (test split)
    arms = ("jev", "llm") if has_tau else ("jev",)
    oc = {(arm, n): outcomes(data, items, taus, arm, n) for arm in arms for n in NOISES}
    for arm in ("jev", "llm"):
        for n in NOISES:
            os_ = oc.get((arm, n), [])
            p = f"{arm}.{n}"
            cp_slots(out, f"vcr.{p}", sum(o.change for o in os_), len(os_))
            cp_slots(out, f"vcr_unsafe.{p}", sum(o.unsafe for o in os_), len(os_))
            cp_slots(out, f"vcr_failclosed.{p}", sum(o.failclosed for o in os_), len(os_))
            cp_slots(out, f"abstain.{p}", sum(not o.definite for o in os_), len(os_))
    jev30 = oc[("jev", "n30")]
    out["carried.jev.h2_match"] = fmt(sum(o.change for o in jev30) == CARRIED_JEV_H2_K
                                      and len(jev30) == CARRIED_JEV_H2_N)

    # cost
    costs = call_cost(data)
    llm_pv = [costs.get(("llm", c["i"], c["noise"]), 0.0) for c in llm_calls]
    out["cost.llm.usd"] = fmt(sum(float(a["charged_usd"]) for a in data.attempts if a["arm"] == "llm"), 6)
    out["cost.llm.usd_per_verdict"] = fmt(sum(llm_pv) / len(llm_pv) if llm_pv else math.nan, 8)
    out["cost.llm.input_tokens"] = fmt(sum(a["usage_input_tokens"] or 0 for a in data.attempts if a["arm"] == "llm"))
    out["cost.llm.output_tokens"] = fmt(sum(a["usage_output_tokens"] or 0 for a in data.attempts if a["arm"] == "llm"))
    lat = [c["latency_total_s"] for c in llm_calls]
    out["latency.llm.call.median"] = fmt(quantile(lat, 0.5), 3)
    out["latency.llm.call.p90"] = fmt(quantile(lat, 0.9), 3)

    # §6 hypotheses
    keys = {"H2": ("jev_rate", "llm_rate", "estimate", "b", "c", "n", "ci_lo", "ci_hi", "p", "p_adj", "verdict"),
            "H3": ("jev_usd", "llm_usd", "estimate", "n", "ci_lo", "ci_hi", "p", "p_adj", "verdict")}
    evaluated = status == "COMPLETE" and has_tau and all(("llm", it.i, n) in data.calls for it in test for n in NOISES)
    out["run.hypotheses_evaluated"] = fmt(evaluated)
    if not evaluated:
        for h, ks in keys.items():
            for k in ks:
                out[f"{h}.{k}"] = NE
    else:
        r2 = h2(paired(oc[("jev", "n30")], oc[("llm", "n30")]), bootstrap_b)
        diffs = [[costs.get(("jev", it.i, n), 0.0) - costs.get(("llm", it.i, n), 0.0) for n in NOISES] for it in test]
        r3 = h3(diffs, bootstrap_b)
        r3["jev_usd"] = sum(costs.get(("jev", it.i, n), 0.0) for it in test for n in NOISES) / r3["n"]
        r3["llm_usd"] = sum(costs.get(("llm", it.i, n), 0.0) for it in test for n in NOISES) / r3["n"]
        r2["p_adj"], r3["p_adj"] = holm([r2["p"], r3["p"]])
        r2["verdict"] = two_way(r2["p_adj"], r2["estimate"], "supported: Jev better", "refuted: Jev worse",
                                "not refuted: no significant difference (not equivalence)")
        r3["verdict"] = two_way(r3["p_adj"], r3["estimate"], "supported: Jev cheaper", "refuted: Jev dearer",
                                "inconclusive")
        for h, r in (("H2", r2), ("H3", r3)):
            for k in keys[h]:
                v = r[k]
                if k in ("p", "p_adj"):
                    out[f"{h}.{k}"] = fmt_p(v)
                elif h == "H3" and k in ("jev_usd", "llm_usd", "estimate", "ci_lo", "ci_hi"):
                    out[f"{h}.{k}"] = fmt(v, 8)
                else:
                    out[f"{h}.{k}"] = fmt(v)
    out["analysis.bootstrap_b"] = fmt(bootstrap_b)
    out["analysis.bootstrap_seed"] = fmt(BOOTSTRAP_SEED)
    return out


# ------------------------------------------------------------------ template


def s(name: str) -> str:
    return "{{" + name + "}}"


def cp(prefix: str) -> str:
    return f"{s(prefix + '.rate')} [{s(prefix + '.lo')}, {s(prefix + '.hi')}] ({s(prefix + '.k')}/{s(prefix + '.n')})"


def build() -> str:
    L: list[str] = []
    a = L.append
    a("# jev-v3 results: re-run of the LLM baseline arm")
    a("")
    a("> Generated by `python -m jev_probe.analysis_v3` from `responses/jev-v3.jsonl` (arm B), "
      "`responses/jev-v2.jsonl` and `results/jev-v2.tau.json` (arm A, carried unchanged) and "
      "`results/jev-v3.tau.json`. Every number below is a named slot; none is entered by hand. "
      "Registration: `prereg/jev-v3.md` (tag `prereg-jev-v3`). Departures: `prereg/DEVIATIONS.md`. "
      "The jev-v2 results stand as the record of jev-v2, with the KI-1 caveat.")
    a("")
    a("## Run")
    a("")
    a("| field | value |")
    a("|---|---|")
    for label, key in (("status", "run.status"), ("hypotheses evaluated", "run.hypotheses_evaluated"),
                       ("run segments", "run.n_segments"), ("arm-B records cached", "run.n_calls.llm"),
                       ("HTTP attempts", "run.n_attempts"), ("adapter retries", "run.n_retries"),
                       ("spend, USD (this run)", "run.spend_usd"), ("returned model string(s)", "run.model_versions.llm"),
                       ("MODEL_VERSION_CHANGED", "run.model_version_changed"), ("anthropic SDK", "run.sdk.llm"),
                       ("prereg commit", "run.prereg_commit"), ("generator SHA-256", "run.generator_sha256"),
                       ("LLM prompt SHA-256", "run.llm_prompt_sha256"), ("thresholds file SHA-256", "run.tau_sha256")):
        a(f"| {label} | {s(key)} |")
    a(f"| bootstrap | {s('analysis.bootstrap_b')} resamples, seed {s('analysis.bootstrap_seed')} |")
    a("")
    a("## Arm health (§3c)")
    a("")
    a("| check | invalid | records | stopped the run |")
    a("|---|---|---|---|")
    a(f"| smoke (first 20 validation records, max 2 invalid) | {s('health.smoke.invalid')} | "
      f"{s('health.smoke.n')} | {s('health.smoke.stopped')} |")
    a(f"| validation split (max 5% invalid) | {s('health.validation.invalid')} | {s('health.validation.n')} | "
      f"{s('health.validation.stopped')} |")
    a("")
    a(f"Invalid records overall: {s('invalid.llm')} (rate {s('invalid.llm.rate')}). Replies: {s('replies.llm.replies')}; "
      f"truncated at max_tokens: {s('replies.llm.truncated')}; containing a code fence: {s('replies.llm.fenced')}.")
    a("")
    a("## Thresholds (false-positive ceiling 1%)")
    a("")
    a("| arm | tau_true | tau_false | source |")
    a("|---|---|---|---|")
    a(f"| A: Jev | {s('tau.jev.true')} | {s('tau.jev.false')} | frozen in jev-v2, carried |")
    a(f"| B: Claude Haiku 4.5 | {s('tau.llm.true')} | {s('tau.llm.false')} | jev-v3 validation, "
      f"{s('tau.llm.n_scored')} scored of {s('tau.llm.n_validation')}; recomputation matches: "
      f"{s('tau.llm.recomputed_match')} |")
    a("")
    a("## Hypotheses (Holm over H2, H3; two-sided, alpha 0.05)")
    a("")
    a("| hypothesis | estimate | 95% CI | p | Holm-adjusted p | verdict |")
    a("|---|---|---|---|---|---|")
    a(f"| H2: Jev not worse than LLM at 30% noise | Jev {s('H2.jev_rate')} vs LLM {s('H2.llm_rate')}; "
      f"difference {s('H2.estimate')} (b = {s('H2.b')}, c = {s('H2.c')}, n = {s('H2.n')}) | "
      f"[{s('H2.ci_lo')}, {s('H2.ci_hi')}] | {s('H2.p')} | {s('H2.p_adj')} | {s('H2.verdict')} |")
    a(f"| H3: Jev cost per verdict below LLM | Jev USD {s('H3.jev_usd')} vs LLM USD {s('H3.llm_usd')}; "
      f"difference {s('H3.estimate')} (n = {s('H3.n')}) | [{s('H3.ci_lo')}, {s('H3.ci_hi')}] | "
      f"{s('H3.p')} | {s('H3.p_adj')} | {s('H3.verdict')} |")
    a("")
    a(f"Arm A values are carried from jev-v2; the carried H2 indicator count matches the registration "
      f"(68/700): {s('carried.jev.h2_match')}.")
    a("")
    a("## Verdict change (test split, Clopper-Pearson 95%)")
    a("")
    a("| arm | noise | verdict-change rate | unsafe (deny to allow) | fail-closed (allow to deny) | abstention |")
    a("|---|---|---|---|---|---|")
    for arm, label in (("jev", "A: Jev (carried)"), ("llm", "B: Claude Haiku 4.5")):
        for n in NOISES:
            p = f"{arm}.{n}"
            a(f"| {label} | {NOISE_NAME[n]} | {cp(f'vcr.{p}')} | {cp(f'vcr_unsafe.{p}')} | "
              f"{cp(f'vcr_failclosed.{p}')} | {cp(f'abstain.{p}')} |")
    a("")
    a("## Cost and latency (arm B)")
    a("")
    a("| measure | value |")
    a("|---|---|")
    for label, key in (("USD", "cost.llm.usd"), ("USD per verdict", "cost.llm.usd_per_verdict"),
                       ("input tokens", "cost.llm.input_tokens"), ("output tokens", "cost.llm.output_tokens"),
                       ("latency per record, median (s)", "latency.llm.call.median"),
                       ("latency per record, p90 (s)", "latency.llm.call.p90")):
        a(f"| {label} | {s(key)} |")
    a("")
    a("Everything outside the hypotheses table is descriptive.")
    a("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write-template", action="store_true", help="(re)write results/jev-v3.template.md only")
    args = ap.parse_args(argv)
    if args.write_template:
        TEMPLATE_PATH.write_text(build(), encoding="utf-8")
        print(f"analysis_v3: wrote {TEMPLATE_PATH}")
        return 0
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    slots = compute()
    filled = fill(template, slots)
    if args.check:
        print(f"analysis_v3: {len(slots)} slots computed; template fills cleanly")
        return 0
    RESULTS_PATH.write_text(filled, encoding="utf-8")
    SLOTS_JSON_PATH.write_text(json.dumps(slots, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"analysis_v3: wrote {RESULTS_PATH} ({len(SLOT_RE.findall(template))} slots filled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
