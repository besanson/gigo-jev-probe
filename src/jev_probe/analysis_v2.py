"""jev-v2 §7–§9 analysis. Reads ONLY the raw-response cache, the frozen thresholds in
results/jev-v2.tau.json, and the pinned sibling engine (for the deterministic verdict).

    python -m jev_probe.analysis_v2          # fill results/jev-v2.md from responses/
    python -m jev_probe.analysis_v2 --check  # compute, verify every slot fills, write nothing

Operational choices (implementations of the registered text, fixed before any data):
- An invalid answer (malformed after one re-request, or HTTP 422 for Jev) has no score and
  maps to `unknown`; it is excluded from threshold setting (§7) and from calibration.
- τ: candidate thresholds are the distinct validation scores plus max+1 (τ_true) and min-1
  (τ_false); τ_true is the smallest candidate with FP rate ≤ 1% among `absent` records,
  τ_false the largest candidate with FN-side rate ≤ 1% among `valid` records.
- Verdict-change CI: Clopper-Pearson 95%. H1: exact two-sided binomial test.
- H2: exact McNemar on discordant pairs; CI for the rate difference from a paired item
  bootstrap. H3: item-clustered paired bootstrap of the mean per-verdict USD difference;
  two-sided p from the null-shifted bootstrap distribution; 95% percentile CI.
- Every bootstrap draws from a fresh random.Random(20261004) with 10,000 resamples.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jev_probe.analysis import SLOT_RE, fill, fmt, fmt_p
from jev_probe.cache import Cache
from jev_probe.constants_v2 import (
    ALPHA,
    API_ARMS,
    ARMS,
    BOOTSTRAP_B,
    BOOTSTRAP_SEED,
    CACHE_PATH,
    FP_CEILING,
    H1_BOUND,
    NOISE_LEVELS,
    RESULTS_PATH,
    SLOTS_JSON_PATH,
    TAU_PATH,
    TEMPLATE_PATH,
)
from jev_probe.corpus_v2 import Item, approval_sensitive, build_items, design_facts, sensed_verdict, verdict
from jev_probe.stats import (
    binom_test_two_sided,
    bootstrap_p_centered,
    clopper_pearson,
    holm,
    mcnemar_exact,
    quantile,
    wilson,
)

NOISES = tuple(k for k, _ in NOISE_LEVELS)
NE = "not evaluated"


# ------------------------------------------------------------------ §7 admission policy


def set_tau(rows: Sequence[tuple[float | None, bool]], ceiling: float = FP_CEILING) -> dict[str, float]:
    """rows: (score or None, truth is valid) over the validation split, all noise levels."""
    scored = [(s, y) for s, y in rows if s is not None]
    if not scored:
        return {"tau_true": math.inf, "tau_false": -math.inf}
    scores = sorted({s for s, _ in scored})
    absent = [s for s, y in scored if not y]
    valid = [s for s, y in scored if y]
    cands_true = scores + [max(scores) + 1.0]
    cands_false = [min(scores) - 1.0] + scores

    def fp(t: float) -> float:  # absent records admitted as valid
        return sum(s >= t for s in absent) / len(absent) if absent else 0.0

    def fn(t: float) -> float:  # valid records denied as absent
        return sum(s <= t for s in valid) / len(valid) if valid else 0.0

    tau_true = min(t for t in cands_true if fp(t) <= ceiling)
    tau_false = max(t for t in cands_false if fn(t) <= ceiling)
    return {"tau_true": tau_true, "tau_false": tau_false}


def map_score(score: float | None, tau: dict[str, float]) -> str:
    if score is None:
        return "unknown"
    if score >= tau["tau_true"]:
        return "true"
    if score <= tau["tau_false"]:
        return "false"
    return "unknown"


def tau_to_json(taus: dict[str, dict[str, float]]) -> dict[str, Any]:
    def enc(x: float) -> Any:
        return x if math.isfinite(x) else ("inf" if x > 0 else "-inf")

    return {arm: {k: enc(v) for k, v in t.items()} for arm, t in taus.items()}


def tau_from_json(obj: dict[str, Any]) -> dict[str, dict[str, float]]:
    return {arm: {k: float(v) for k, v in t.items()} for arm, t in obj.items() if arm in ARMS}


def validation_rows(calls: dict[tuple[str, int, str], dict[str, Any]], items: Sequence[Item],
                    arm: str) -> list[tuple[float | None, bool]]:
    rows = []
    for it in items:
        if it.split != "validation":
            continue
        for n in NOISES:
            c = calls.get((arm, it.i, n))
            if c is not None:
                rows.append((c["score"], it.truth_bool))
    return rows


# ------------------------------------------------------------------ data


@dataclass
class Data:
    calls: dict[tuple[str, int, str], dict[str, Any]]
    attempts: list[dict[str, Any]]
    retries: list[dict[str, Any]]
    run_events: list[dict[str, Any]]
    manifests: list[dict[str, Any]]


def load(cache_path: Path = CACHE_PATH) -> Data:
    calls: dict[tuple[str, int, str], dict[str, Any]] = {}
    attempts, retries, events, manifests = [], [], [], []
    for r in Cache(cache_path).records():
        k = r.get("kind")
        if k == "call":
            calls[(r["arm"], r["i"], r["noise"])] = r
        elif k == "attempt":
            attempts.append(r)
        elif k == "retry":
            retries.append(r)
        elif k == "run_event":
            events.append(r)
        elif k == "manifest":
            manifests.append(r["manifest"])
    return Data(calls, attempts, retries, events, manifests)


def call_cost(data: Data) -> dict[tuple[str, int, str], float]:
    out: dict[tuple[str, int, str], float] = {}
    for a in data.attempts:
        key = (a["arm"], a["i"], a["noise"])
        out[key] = out.get(key, 0.0) + float(a["charged_usd"])
    return out


# ------------------------------------------------------------------ slot helpers


def cp_slots(out: dict[str, str], prefix: str, k: int, n: int) -> None:
    lo, hi = clopper_pearson(k, n)
    out[f"{prefix}.k"] = fmt(k)
    out[f"{prefix}.n"] = fmt(n)
    out[f"{prefix}.rate"] = fmt(k / n if n else math.nan)
    out[f"{prefix}.lo"] = fmt(lo)
    out[f"{prefix}.hi"] = fmt(hi)


def wilson_slots(out: dict[str, str], prefix: str, k: int, n: int) -> None:
    lo, hi = wilson(k, n)
    out[f"{prefix}.k"] = fmt(k)
    out[f"{prefix}.n"] = fmt(n)
    out[f"{prefix}.rate"] = fmt(k / n if n else math.nan)
    out[f"{prefix}.lo"] = fmt(lo)
    out[f"{prefix}.hi"] = fmt(hi)


@dataclass
class Outcome:
    item: Item
    sensed: str  # true / false / unknown
    true_verdict: str
    sensed_verdict: str
    perturbation: str
    score: float | None

    @property
    def change(self) -> bool:
        return self.sensed_verdict != self.true_verdict

    @property
    def unsafe(self) -> bool:
        return self.true_verdict == "deny" and self.sensed_verdict == "allow"

    @property
    def failclosed(self) -> bool:
        return self.true_verdict == "allow" and self.sensed_verdict == "deny"

    @property
    def definite(self) -> bool:
        return self.sensed != "unknown"

    @property
    def field_error(self) -> bool:
        return self.definite and (self.sensed == "true") != self.item.truth_bool


def outcomes(data: Data, items: Sequence[Item], taus: dict[str, dict[str, float]], arm: str,
             noise: str) -> list[Outcome]:
    res = []
    for it in items:
        if it.split != "test":
            continue
        c = data.calls.get((arm, it.i, noise))
        if c is None:
            continue
        s = map_score(c["score"], taus[arm])
        res.append(Outcome(it, s, verdict(it.t), sensed_verdict(it.t, s), c["perturbation"], c["score"]))
    return res


# ------------------------------------------------------------------ §8 metrics


def verdict_slots(out: dict[str, str], oc: dict[tuple[str, str], list[Outcome]]) -> None:
    for (arm, n), os_ in oc.items():
        p = f"{arm}.{n}"
        cp_slots(out, f"vcr.{p}", sum(o.change for o in os_), len(os_))
        cp_slots(out, f"vcr_unsafe.{p}", sum(o.unsafe for o in os_), len(os_))
        cp_slots(out, f"vcr_failclosed.{p}", sum(o.failclosed for o in os_), len(os_))
        for stratum, sel in (("sensitive", lambda o: approval_sensitive(o.item.t)),
                             ("allow", lambda o: o.true_verdict == "allow")):
            sub = [o for o in os_ if sel(o)]
            cp_slots(out, f"vcr_stratum.{p}.{stratum}", sum(o.change for o in sub), len(sub))
        out[f"vcr_cause.{p}.misread"] = fmt(sum(o.change and o.definite for o in os_))
        out[f"vcr_cause.{p}.unknown"] = fmt(sum(o.change and not o.definite for o in os_))
        for scope, sel in (("all", lambda o: True), ("perturbed", lambda o: o.perturbation != "none"),
                           ("unperturbed", lambda o: o.perturbation == "none")):
            sub = [o for o in os_ if sel(o)]
            definite = [o for o in sub if o.definite]
            wilson_slots(out, f"field_error.{p}.{scope}", sum(o.field_error for o in definite), len(definite))
            wilson_slots(out, f"abstain.{p}.{scope}", sum(not o.definite for o in sub), len(sub))


def reliability_slots(out: dict[str, str], oc: dict[tuple[str, str], list[Outcome]]) -> None:
    for arm in ARMS:
        scopes = {"all": [o for n in NOISES for o in oc.get((arm, n), [])]}
        scopes.update({n: oc.get((arm, n), []) for n in NOISES})
        for scope, os_ in scopes.items():
            pts = [(o.score, 1.0 if o.item.truth_bool else 0.0) for o in os_ if o.score is not None]
            pre = f"{arm}.{scope}"
            out[f"brier.{pre}"] = fmt(sum((s - y) ** 2 for s, y in pts) / len(pts) if pts else math.nan)
            ece = 0.0
            for b in range(10):
                lo_, hi_ = b / 10, (b + 1) / 10
                inb = [(s, y) for s, y in pts if (lo_ <= s < hi_) or (b == 9 and s == 1.0)]
                bp = f"reliability.{pre}.b{b}"
                k = int(sum(y for _, y in inb))
                lo, hi = wilson(k, len(inb))
                mean_p = sum(s for s, _ in inb) / len(inb) if inb else math.nan
                obs = k / len(inb) if inb else math.nan
                out[f"{bp}.n"] = fmt(len(inb))
                out[f"{bp}.mean_p"] = fmt(mean_p)
                out[f"{bp}.obs"] = fmt(obs)
                out[f"{bp}.lo"] = fmt(lo)
                out[f"{bp}.hi"] = fmt(hi)
                if inb:
                    ece += len(inb) / len(pts) * abs(mean_p - obs)
            out[f"ece.{pre}"] = fmt(ece if pts else math.nan)


def ops_slots(out: dict[str, str], data: Data) -> None:
    costs = call_cost(data)
    for arm in API_ARMS:
        att = [a for a in data.attempts if a["arm"] == arm]
        calls = [c for (a, _, _), c in data.calls.items() if a == arm]
        lat_a = [a["latency_s"] for a in att if a["latency_s"] is not None]
        lat_c = [c["latency_total_s"] for c in calls]
        for kind, xs in (("attempt", lat_a), ("call", lat_c)):
            for st, q in (("median", 0.5), ("p90", 0.9), ("p99", 0.99)):
                out[f"latency.{arm}.{kind}.{st}"] = fmt(quantile(xs, q), 3)
            out[f"latency.{arm}.{kind}.max"] = fmt(max(xs) if xs else math.nan, 3)
            out[f"latency.{arm}.{kind}.n"] = fmt(len(xs))
        out[f"latency.{arm}.calls_rerequested"] = fmt(sum(c["n_requests"] > 1 for c in calls))
        out[f"latency.{arm}.calls_with_retries"] = fmt(len({(r["i"], r["noise"]) for r in data.retries
                                                             if r["arm"] == arm}))
        tin = sum(a["usage_input_tokens"] or 0 for a in att)
        tout = sum(a["usage_output_tokens"] or 0 for a in att)
        usd_total = sum(float(a["charged_usd"]) for a in att)
        per_verdict = [costs.get((arm, c["i"], c["noise"]), 0.0) for c in calls]
        out[f"cost.{arm}.input_tokens"] = fmt(tin)
        out[f"cost.{arm}.output_tokens"] = fmt(tout)
        out[f"cost.{arm}.usd"] = fmt(usd_total, 6)
        out[f"cost.{arm}.usd_per_call"] = fmt(usd_total / len(att) if att else math.nan, 8)
        out[f"cost.{arm}.usd_per_verdict"] = fmt(sum(per_verdict) / len(per_verdict) if per_verdict else math.nan, 8)
        out[f"cost.{arm}.attempts"] = fmt(len(att))
        b = [a["request_bytes"] for a in att]
        out[f"bytes.{arm}.total"] = fmt(sum(b))
        out[f"bytes.{arm}.per_call"] = fmt(sum(b) / len(b) if b else math.nan, 1)
        out[f"invalid.{arm}"] = fmt(sum(c["status"] == "invalid" for c in calls))
    out["cost.total.usd"] = fmt(sum(float(a["charged_usd"]) for a in data.attempts), 6)
    out["cost.kw.usd"] = fmt(0.0, 6)


# ------------------------------------------------------------------ §9 hypotheses


def paired(oc_a: list[Outcome], oc_b: list[Outcome]) -> list[tuple[bool, bool]]:
    b_by = {o.item.i: o for o in oc_b}
    return [(o.change, b_by[o.item.i].change) for o in oc_a if o.item.i in b_by]


def h1(oc: list[Outcome]) -> dict[str, Any]:
    k, n = sum(o.change for o in oc), len(oc)
    lo, hi = clopper_pearson(k, n)
    return {"estimate": k / n, "k": k, "n": n, "ci_lo": lo, "ci_hi": hi,
            "p": binom_test_two_sided(k, n, H1_BOUND)}


def h2(pairs: list[tuple[bool, bool]], b_boot: int = BOOTSTRAP_B) -> dict[str, Any]:
    n = len(pairs)
    b = sum(a and not c for a, c in pairs)  # Jev changed, LLM did not
    c = sum(c_ and not a for a, c_ in pairs)
    ra = sum(a for a, _ in pairs) / n
    rb = sum(c_ for _, c_ in pairs) / n
    rng = random.Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(b_boot):
        s = [pairs[rng.randrange(n)] for _ in range(n)]
        draws.append(sum(a for a, _ in s) / n - sum(c_ for _, c_ in s) / n)
    return {"jev_rate": ra, "llm_rate": rb, "estimate": ra - rb, "b": b, "c": c, "n": n,
            "ci_lo": quantile(draws, 0.025), "ci_hi": quantile(draws, 0.975), "p": mcnemar_exact(b, c)}


def h3(diffs_by_item: list[list[float]], b_boot: int = BOOTSTRAP_B) -> dict[str, Any]:
    flat = [d for ds in diffs_by_item for d in ds]
    est = sum(flat) / len(flat)
    rng = random.Random(BOOTSTRAP_SEED)
    m = len(diffs_by_item)
    draws = []
    for _ in range(b_boot):
        s = [d for _ in range(m) for d in diffs_by_item[rng.randrange(m)]]
        draws.append(sum(s) / len(s))
    return {"estimate": est, "n": len(flat), "ci_lo": quantile(draws, 0.025), "ci_hi": quantile(draws, 0.975),
            "p": bootstrap_p_centered(est, draws)}


def two_way(p_adj: float, est: float, below: str, above: str, other: str) -> str:
    if p_adj < ALPHA and est < 0:
        return below
    if p_adj < ALPHA and est > 0:
        return above
    return other


def hypothesis_slots(out: dict[str, str], data: Data, oc: dict[tuple[str, str], list[Outcome]],
                     items: Sequence[Item], evaluated: bool, b_boot: int = BOOTSTRAP_B) -> None:
    keys = {"H1": ("estimate", "k", "n", "ci_lo", "ci_hi", "p", "p_adj", "verdict"),
            "H2": ("jev_rate", "llm_rate", "estimate", "b", "c", "n", "ci_lo", "ci_hi", "p", "p_adj", "verdict"),
            "H3": ("jev_usd", "llm_usd", "estimate", "n", "ci_lo", "ci_hi", "p", "p_adj", "verdict")}
    if not evaluated:
        for h, ks in keys.items():
            for k in ks:
                out[f"{h}.{k}"] = NE
        return
    r1 = h1(oc[("jev", "n00")])
    r2 = h2(paired(oc[("jev", "n30")], oc[("llm", "n30")]), b_boot)
    costs = call_cost(data)
    test = [it for it in items if it.split == "test"]
    diffs = [[costs.get(("jev", it.i, n), 0.0) - costs.get(("llm", it.i, n), 0.0) for n in NOISES] for it in test]
    r3 = h3(diffs, b_boot)
    r3["jev_usd"] = sum(costs.get(("jev", it.i, n), 0.0) for it in test for n in NOISES) / r3["n"]
    r3["llm_usd"] = sum(costs.get(("llm", it.i, n), 0.0) for it in test for n in NOISES) / r3["n"]
    adj = holm([r1["p"], r2["p"], r3["p"]])
    r1["p_adj"], r2["p_adj"], r3["p_adj"] = adj
    r1["verdict"] = two_way(r1["p_adj"], r1["estimate"] - H1_BOUND, "supported: below the 2% bound",
                            "refuted: above the 2% bound", "inconclusive")
    r2["verdict"] = two_way(r2["p_adj"], r2["estimate"], "supported: Jev better",
                            "refuted: Jev worse", "not refuted: no significant difference (not equivalence)")
    r3["verdict"] = two_way(r3["p_adj"], r3["estimate"], "supported: Jev cheaper",
                            "refuted: Jev dearer", "inconclusive")
    for h, r in (("H1", r1), ("H2", r2), ("H3", r3)):
        for k in keys[h]:
            v = r[k]
            if k in ("p", "p_adj"):
                out[f"{h}.{k}"] = fmt_p(v)
            elif h == "H3" and k in ("jev_usd", "llm_usd", "estimate", "ci_lo", "ci_hi"):
                out[f"{h}.{k}"] = fmt(v, 8)
            else:
                out[f"{h}.{k}"] = fmt(v)


# ------------------------------------------------------------------ run and design


def run_slots(out: dict[str, str], data: Data, items: Sequence[Item], evaluated: bool) -> None:
    last = data.run_events[-1]["manifest"] if data.run_events else (data.manifests[-1] if data.manifests else {})
    out["run.status"] = str(last.get("status", "none"))
    out["run.hypotheses_evaluated"] = fmt(evaluated)
    out["run.n_segments"] = fmt(len({e["segment"] for e in data.run_events}))
    for arm in ARMS:
        out[f"run.n_calls.{arm}"] = fmt(sum(1 for (a, _, _) in data.calls if a == arm))
    out["run.n_attempts"] = fmt(len(data.attempts))
    out["run.n_retries"] = fmt(sum(1 for r in data.retries if not r.get("exhausted")))
    for arm in API_ARMS:
        ms = sorted({c["returned_model"] for (a, _, _), c in data.calls.items() if a == arm})
        out[f"run.model_versions.{arm}"] = ", ".join(ms) or "none"
    out["run.model_version_changed"] = fmt(bool(last.get("model_version_changed", False)))
    for k in ("prereg_commit", "generator_sha256", "jev_context_sha256", "jev_question_sha256",
              "llm_prompt_sha256", "tau_sha256"):
        out[f"run.{k}"] = str(last.get(k, "n/a"))
    sdks = last.get("sdks", {})
    out["run.sdk.jev"] = str(sdks.get("typesafe-sdk", "n/a"))
    out["run.sdk.llm"] = str(sdks.get("anthropic", "n/a"))
    pins = last.get("engine_pins", {})
    out["run.pin.sarc_authority_derivation"] = str(pins.get("sarc-authority-derivation", "n/a"))
    out["run.spend_usd"] = fmt(sum(float(a["charged_usd"]) for a in data.attempts), 6)
    facts = design_facts(list(items))
    for split in ("validation", "test"):
        for k, v in facts[split].items():
            out[f"design.{split}.{k}"] = fmt(v)
    out["design.population_sensitive"] = fmt(facts["population_sensitive"])


def all_test_complete(data: Data, items: Sequence[Item]) -> bool:
    return all((arm, it.i, n) in data.calls for it in items if it.split == "test"
               for arm in API_ARMS for n in NOISES)


def compute(cache_path: Path = CACHE_PATH, tau_path: Path = TAU_PATH, *, items: Sequence[Item] | None = None,
            bootstrap_b: int = BOOTSTRAP_B) -> dict[str, str]:
    data = load(cache_path)
    items = build_items() if items is None else list(items)
    taus = tau_from_json(json.loads(tau_path.read_text(encoding="utf-8")))
    out: dict[str, str] = {}
    for arm in ARMS:
        recomputed = set_tau(validation_rows(data.calls, items, arm))
        out[f"tau.{arm}.true"] = fmt(taus[arm]["tau_true"])
        out[f"tau.{arm}.false"] = fmt(taus[arm]["tau_false"])
        out[f"tau.{arm}.recomputed_match"] = fmt(recomputed == taus[arm])
        out[f"tau.{arm}.n_validation"] = fmt(len(validation_rows(data.calls, items, arm)))
    oc = {(arm, n): outcomes(data, items, taus, arm, n) for arm in ARMS for n in NOISES}
    verdict_slots(out, oc)
    reliability_slots(out, oc)
    ops_slots(out, data)
    evaluated = all_test_complete(data, items) and not str(
        (data.run_events[-1]["status"] if data.run_events else "")).startswith("CAP_TRUNCATED")
    hypothesis_slots(out, data, oc, items, evaluated, bootstrap_b)
    run_slots(out, data, items, evaluated)
    out["analysis.bootstrap_b"] = fmt(bootstrap_b)
    out["analysis.bootstrap_seed"] = fmt(BOOTSTRAP_SEED)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=CACHE_PATH)
    ap.add_argument("--tau", type=Path, default=TAU_PATH)
    ap.add_argument("--template", type=Path, default=TEMPLATE_PATH)
    ap.add_argument("--out", type=Path, default=RESULTS_PATH)
    ap.add_argument("--slots-json", type=Path, default=SLOTS_JSON_PATH)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    slots = compute(args.cache, args.tau)
    template = args.template.read_text(encoding="utf-8")
    filled = fill(template, slots)
    if args.check:
        print(f"analysis_v2: {len(slots)} slots computed; template fills cleanly")
        return 0
    args.out.write_text(filled, encoding="utf-8")
    args.slots_json.write_text(json.dumps(slots, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"analysis_v2: wrote {args.out} ({len(SLOT_RE.findall(template))} slots filled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
