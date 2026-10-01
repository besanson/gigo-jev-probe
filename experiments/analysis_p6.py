"""Paper 6 analysis (prereg/p6-v1.1.md §5.4 to §5.8, §6). Reads ONLY the raw caches
responses/p6-E1.jsonl and responses/p6-E2.jsonl, the frozen results/p6-E*.tau.json and the pinned
siblings; it never calls a model. E3 to E5 are computed from the E1 and E2 caches.

    python -m experiments.analysis_p6                  # fill results/p6.md and results/p6.slots.json
    python -m experiments.analysis_p6 --check          # compute, verify every slot fills, write nothing
    python -m experiments.analysis_p6 --write-template # (re)write results/p6.template.md

Every number in results/p6.md is a named slot. Slots of an experiment that is not COMPLETE read
"not evaluated"; H1 and H2 are evaluated only when both experiments are COMPLETE.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from experiments.constants_p6 import (
    ALPHA,
    BOOTSTRAP_B,
    BOOTSTRAP_SEED,
    CEILING,
    CEILING_E3,
    FIELD_VALUES,
    H1_CELLS,
    H2_NOISE,
    RESULTS_PATH,
    SENSORS,
    SLOTS_JSON_PATH,
    TEMPLATE_PATH,
    cache_path,
    tau_path,
)
from experiments.corpus_p6 import (
    Item,
    assertion_labels,
    build_items,
    e1_outcome,
    e2_outcome,
    fields_for,
    sensed_sets,
    truth_values,
)
from experiments.run_p6 import NOISES, cached_calls, fit_policy, labels, registered_order, tau_document
from jev_probe.analysis import SLOT_RE, fill, fmt, fmt_p
from jev_probe.cache import Cache
from jev_probe.stats import binom_pmf, clopper_pearson, holm, mcnemar_exact, quantile, sd, two_sided_normal_p
from sensed_authority.admission import admit, cp_upper, load_policy

NE = "not evaluated"
NOISE_NAME = {"n00": "0%", "n10": "10%", "n30": "30%"}
SENSOR_NAME = {"jev": "Jev", "llm": "Claude Haiku 4.5"}
REDUCTS = ("R_branch", "R_env")


# ------------------------------------------------------------------ loading


def status_of(store: Cache) -> str:
    events = [r for r in store.records() if r.get("kind") == "run_event"]
    return str(events[-1]["status"]) if events else "none"


def load_policies(path: Path) -> dict[str, dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {s: {**v, "policy": load_policy(json.dumps(v["policy"]))} for s, v in doc["sensors"].items()}


def admitted(call: dict | None, thresholds: dict[str, tuple[float, float]]) -> str | None:
    if call is None or call["score"] is None:
        return None
    return admit(call["score"], thresholds)


def readings(exp: str, items: list[Item], calls: dict, thresholds: dict[str, dict], split: str = "test"):
    """{(sensor, label, i, noise): {field: admitted value or None}} for one split."""
    out: dict[tuple[str, str, int, str], dict[str, str | None]] = {}
    for it, noise, label, arm, sensor, field in registered_order(items, exp, (split,)):
        c = calls.get((label, field, sensor, it.i, noise))
        out.setdefault((sensor, label, it.i, noise), {})[field] = admitted(c, thresholds[sensor][field])
    return out


def cp_slots(out: dict[str, str], prefix: str, k: int, n: int) -> None:
    lo, hi = clopper_pearson(k, n)
    out.update({f"{prefix}.k": fmt(k), f"{prefix}.n": fmt(n), f"{prefix}.rate": fmt(k / n if n else math.nan),
                f"{prefix}.lo": fmt(lo), f"{prefix}.hi": fmt(hi)})


def upper_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p): the one-sided p-value of H0: rate <= p."""
    if p >= 1.0:
        return 1.0
    return min(1.0, math.fsum(binom_pmf(x, n, p) for x in range(k, n + 1)))


def bootstrap_diff(pairs: Sequence[tuple[bool, bool]], b: int = BOOTSTRAP_B) -> tuple[float, float]:
    """Item-clustered bootstrap CI for rate(first) - rate(second); one pair per item here."""
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(pairs)
    draws = []
    for _ in range(b):
        s = [pairs[rng.randrange(n)] for _ in range(n)]
        draws.append((sum(a for a, _ in s) - sum(c for _, c in s)) / n)
    return quantile(draws, 0.025), quantile(draws, 0.975)


# ------------------------------------------------------------------ E1


def e1_slots(out: dict[str, str], items: list[Item], calls: dict, pol: dict) -> dict[str, float]:
    thresholds = {s: pol[s]["policy"]["thresholds"] for s in SENSORS}
    reads = readings("E1", items, calls, thresholds)
    test = [it for it in items if it.split == "test"]
    pvals: dict[str, float] = {}
    for s in SENSORS:
        for noise in NOISES:
            p = f"E1.{s}.{noise}"
            change = unsafe = 0
            wrong = {f: 0 for f in fields_for("E1")}
            unknown = {f: 0 for f in fields_for("E1")}
            for it in test:
                adm = reads[(s, "E1", it.i, noise)]
                c, u = e1_outcome(it, adm)
                change += c
                unsafe += u
                truth = truth_values(it)
                for f in fields_for("E1"):
                    unknown[f] += adm[f] is None
                    wrong[f] += adm[f] is not None and adm[f] != truth[f]
            n = len(test)
            cp_slots(out, f"{p}.unsafe", unsafe, n)
            cp_slots(out, f"{p}.change", change, n)
            for f in fields_for("E1"):
                out[f"{p}.{f}.wrong"] = fmt(wrong[f] / n if n else math.nan)
                out[f"{p}.{f}.unknown"] = fmt(unknown[f] / n if n else math.nan)
            bounds = pol[s]["bounds"][noise]
            out[f"{p}.unsafe_bound"] = fmt(bounds["unsafe_bound"])
            out[f"{p}.change_bound"] = fmt(bounds["change_bound"])
            for b in ("unsafe_bound", "change_bound"):
                out[f"{p}.{b}.label"] = " vacuous" if bounds[b] > 1 else ""
            out[f"{p}.s3_held"] = fmt(unsafe == 0)
            pvals[f"{s}.{noise}"] = upper_tail(unsafe, n, bounds["unsafe_bound"])
            out[f"{p}.h1_p"] = fmt_p(pvals[f"{s}.{noise}"])
    # looseness: the bound a sensor with no split-B errors still gets, one Clopper-Pearson floor per term
    n_b = sum(it.part == "B" for it in items)
    floors = {f: cp_upper(0, n_b) for f in fields_for("E1")}
    out["E1.floor.n"] = fmt(n_b)
    for f, v in floors.items():
        out[f"E1.floor.{f}"] = fmt(v)
    out["E1.floor.unsafe_bound"] = fmt(sum(floors.values()))
    out["E1.floor.change_bound"] = fmt(2 * sum(floors.values()))
    return pvals


# ------------------------------------------------------------------ E2


def e2_slots(out: dict[str, str], items: list[Item], calls: dict, pol: dict,
             bootstrap_b: int = BOOTSTRAP_B) -> dict[str, dict[str, Any]]:
    thresholds = {s: pol[s]["policy"]["thresholds"] for s in SENSORS}
    reads = readings("E2", items, calls, thresholds)
    test = [it for it in items if it.split == "test"]
    h2: dict[str, dict[str, Any]] = {}
    for s in SENSORS:
        for label, arm in labels("E2"):
            picked = pol[s]["picks"][label]["picked"]
            other = next(r for r in REDUCTS if r != picked)
            q = f"E2.{s}.{label}"
            out[f"{q}.picked"] = picked
            out[f"{q}.sensed.{picked}"] = ", ".join(sensed_sets(arm)[picked])
            out[f"{q}.sensed.{other}"] = ", ".join(sensed_sets(arm)[other])
            for r in REDUCTS:
                out[f"{q}.estimated_bound.{r}"] = fmt(pol[s]["picks"][label]["estimated_bounds"][r])
            for noise in NOISES:
                outcomes = {r: [e2_outcome(it, r, reads[(s, label, it.i, noise)]) for it in test] for r in REDUCTS}
                for role, r in (("picked", picked), ("other", other)):
                    cp_slots(out, f"{q}.{noise}.{role}.change", sum(c for c, _ in outcomes[r]), len(test))
                    cp_slots(out, f"{q}.{noise}.{role}.unsafe", sum(u for _, u in outcomes[r]), len(test))
                if noise == H2_NOISE:
                    pairs = [(a[0], b[0]) for a, b in zip(outcomes[picked], outcomes[other], strict=True)]
                    b = sum(a and not c for a, c in pairs)
                    c = sum(c and not a for a, c in pairs)
                    n = len(pairs)
                    est = (sum(a for a, _ in pairs) - sum(c_ for _, c_ in pairs)) / n if n else math.nan
                    lo, hi = bootstrap_diff(pairs, bootstrap_b) if n else (math.nan, math.nan)
                    h2[f"{s}.{label}"] = {"estimate": est, "b": b, "c": c, "n": n, "ci_lo": lo, "ci_hi": hi,
                                          "p": mcnemar_exact(b, c)}
    return h2


# ------------------------------------------------------------------ E3 (from the E1 caches)


def e3_slots(out: dict[str, str], items: list[Item], calls: dict, pol: dict) -> None:
    test = [it for it in items if it.split == "test"]
    by_eps = {CEILING: {s: pol[s]["policy"]["thresholds"] for s in SENSORS},
              CEILING_E3: {s: fit_policy("E1", items, calls, s, CEILING_E3)["thresholds"] for s in SENSORS}}
    for eps, thresholds in by_eps.items():
        reads = readings("E1", items, calls, thresholds)
        tag = f"eps{round(eps * 100)}"
        for s in SENSORS:
            for noise in NOISES:
                outs = []
                for it in test:
                    adm = reads[(s, "E1", it.i, noise)]
                    outs.append((any(v is None for v in adm.values()), *e1_outcome(it, adm)))
                n = len(outs)
                for policy in ("deny", "escalate"):
                    decided = [o for o in outs if policy == "deny" or not o[0]]
                    p = f"E3.{tag}.{policy}.{s}.{noise}"
                    out[f"{p}.coverage"] = fmt(len(decided) / n if n else math.nan)
                    out[f"{p}.unsafe"] = fmt(sum(o[2] for o in decided) / n if n else math.nan)
                    out[f"{p}.exposure"] = fmt(sum(o[1] for o in decided) / len(decided) if decided else math.nan)


# ------------------------------------------------------------------ E4 (synthetic, no model)


def e4_slots(out: dict[str, str]) -> bool:
    """The pipeline's own evaluation reproduces the N6 witnesses exactly as the checker computes them."""
    from checkers import n6_witness as w

    model = w.and_model()
    exact = w.run()
    ok = True
    for tag, which, seed, key in (("a", "a", w.SEED_A, "a_disjoint"), ("b", "b", w.SEED_B, "b_joint")):
        rng = random.Random(seed)
        unsafe = wrong = 0
        for _ in range(w.N_SIM):
            if which == "a":
                t = {"f1": False, "f2": True} if rng.random() < 0.5 else {"f1": True, "f2": False}
                o = dict(t)
                if rng.random() < float(w.Q):
                    o["f1" if not t["f1"] else "f2"] = True
            else:
                t = {"f1": False, "f2": False}
                o = {"f1": True, "f2": True} if rng.random() < float(w.Q) else dict(t)
            truth_v = model.table[(t["f1"], t["f2"])]
            got = model.evaluate(o)
            unsafe += truth_v == "deny" and got == "allow"
            wrong += (o["f1"] != t["f1"]) + (o["f2"] != t["f2"])
        sim = exact[key]["simulation"]
        same = unsafe == sim["unsafe"] and wrong == sim["wrong_f1"] + sim["wrong_f2"]
        ok &= same
        cp_slots(out, f"E4.{tag}.unsafe", unsafe, w.N_SIM)
        out[f"E4.{tag}.exact_unsafe"] = exact[key]["exact"]["unsafe"]
        out[f"E4.{tag}.exact_bound"] = exact[key]["exact"]["s1_unsafe_bound"]
        out[f"E4.{tag}.matches_checker"] = fmt(same)
    out["E4.check_passes"] = fmt(ok)
    return ok


# ------------------------------------------------------------------ E5 (against the assertion label)


def e5_slots(out: dict[str, str], exp: str, items: list[Item], calls: dict, b: int = BOOTSTRAP_B) -> None:
    for s in SENSORS:
        per_item: dict[tuple[str, int], float] = {}
        rows: list[tuple[str, float, float]] = []
        for it, noise, label, arm, sensor, field in registered_order(items, exp, ("test",)):
            if sensor != s:
                continue
            c = calls.get((label, field, s, it.i, noise))
            if c is None or c["score"] is None:
                continue
            labs = assertion_labels(it, field, noise, arm)
            for v in FIELD_VALUES[(exp, field)]:
                p, y = c["score"][v], 1.0 if labs[v] else 0.0
                rows.append((f"{field}={v}", p, y))
                per_item[(exp, it.i)] = per_item.get((exp, it.i), 0.0) + (y - p) * (1 - 2 * p)
        q = f"E5.{exp}.{s}"
        out[f"{q}.n"] = fmt(len(rows))
        if not rows:
            for k in ("z", "p", "brier", "bss"):
                out[f"{q}.{k}"] = "n/a"
            continue
        num = math.fsum(per_item.values())
        vals = list(per_item.values())
        rng = random.Random(BOOTSTRAP_SEED)
        nums = [math.fsum(vals[rng.randrange(len(vals))] for _ in vals) for _ in range(b)]
        se = sd(nums)
        z = num / se if se else (0.0 if num == 0 else math.copysign(math.inf, num))
        brier = math.fsum((p - y) ** 2 for _, p, y in rows) / len(rows)
        base: dict[str, list[float]] = {}
        for qid, _, y in rows:
            base.setdefault(qid, []).append(y)
        ref = math.fsum(math.fsum((sum(ys) / len(ys) - y) ** 2 for y in ys) for ys in base.values())
        out[f"{q}.z"] = fmt(z)
        out[f"{q}.p"] = fmt_p(two_sided_normal_p(z) if math.isfinite(z) else 0.0)
        out[f"{q}.brier"] = fmt(brier)
        out[f"{q}.bss"] = fmt(1 - brier * len(rows) / ref if ref > 0 else math.nan)


# ------------------------------------------------------------------ hypotheses (§6)


def verdict(p_adj: float, est: float) -> str:
    if p_adj < ALPHA and est < 0:
        return "supported: picked reduct lower"
    if p_adj < ALPHA and est > 0:
        return "refuted: picked reduct higher"
    return "not refuted: no significant difference"


def hypothesis_slots(out: dict[str, str], h1_cells: dict[str, float] | None, h2: dict[str, dict] | None) -> None:
    if h1_cells is None or h2 is None:
        return
    p1 = min(1.0, H1_CELLS * min(h1_cells.values()))
    keys = sorted(h2)
    adj = holm([p1] + [h2[k]["p"] for k in keys])
    out["H1.p"] = fmt_p(p1)
    out["H1.p_adj"] = fmt_p(adj[0])
    out["H1.verdict"] = "refuted: bound violated" if adj[0] < ALPHA else "not refuted: no violation detected"
    for k, pa in zip(keys, adj[1:], strict=True):
        r = h2[k]
        for f in ("estimate", "ci_lo", "ci_hi"):
            out[f"H2.{k}.{f}"] = fmt(r[f])
        for f in ("b", "c", "n"):
            out[f"H2.{k}.{f}"] = fmt(r[f])
        out[f"H2.{k}.p"] = fmt_p(r["p"])
        out[f"H2.{k}.p_adj"] = fmt_p(pa)
        out[f"H2.{k}.verdict"] = verdict(pa, r["estimate"])


# ------------------------------------------------------------------ compute


def compute(*, caches: dict[str, Path] | None = None, taus: dict[str, Path] | None = None,
            items: dict[str, list[Item]] | None = None, bootstrap_b: int = BOOTSTRAP_B) -> dict[str, str]:
    caches = caches or {e: cache_path(e) for e in ("E1", "E2")}
    taus = taus or {e: tau_path(e) for e in ("E1", "E2")}
    out: dict[str, str] = {"analysis.bootstrap_b": fmt(bootstrap_b), "analysis.bootstrap_seed": fmt(BOOTSTRAP_SEED)}
    h1 = h2 = None
    for exp in ("E1", "E2"):
        store = Cache(caches[exp])
        status = status_of(store)
        out[f"{exp}.status"] = status
        calls = cached_calls(store)
        out[f"{exp}.spend_usd"] = fmt(sum(float(r["charged_usd"]) for r in store.records() if r.get("kind") == "attempt"), 6)
        out[f"{exp}.n_calls"] = fmt(len(calls))
        out[f"{exp}.invalid"] = fmt(sum(c["status"] == "invalid" for c in calls.values()))
        out[f"{exp}.models"] = ", ".join(sorted({c["returned_model"] for c in calls.values()})) or "none"
        if status != "COMPLETE" or not taus[exp].exists():
            continue
        its = (items or {}).get(exp) or build_items(exp)
        if taus[exp].read_text(encoding="utf-8") != tau_document(exp, its, calls):
            out[f"{exp}.tau_recomputed_match"] = "no"
            continue
        out[f"{exp}.tau_recomputed_match"] = "yes"
        pol = load_policies(taus[exp])
        if exp == "E1":
            h1 = e1_slots(out, its, calls, pol)
            e3_slots(out, its, calls, pol)
        else:
            h2 = e2_slots(out, its, calls, pol, bootstrap_b)
        e5_slots(out, exp, its, calls, bootstrap_b)
    e4_slots(out)
    out["hypotheses_evaluated"] = fmt(h1 is not None and h2 is not None)
    hypothesis_slots(out, h1, h2)
    return out


def fill_all(template: str, slots: dict[str, str]) -> str:
    """Slots not computed (an experiment not yet COMPLETE) read 'not evaluated'."""
    names = set(SLOT_RE.findall(template))
    return fill(template, {**{n: NE for n in names}, **slots})


# ------------------------------------------------------------------ template


def s(name: str) -> str:
    return "{{" + name + "}}"


def cp(prefix: str) -> str:
    return f"{s(prefix + '.rate')} [{s(prefix + '.lo')}, {s(prefix + '.hi')}] ({s(prefix + '.k')}/{s(prefix + '.n')})"


def build() -> str:
    L: list[str] = []
    a = L.append
    a("# Paper 6 results: probabilistic sensing, deterministic authority")
    a("")
    a("> Generated by `python -m experiments.analysis_p6` from `responses/p6-E1.jsonl`, `responses/p6-E2.jsonl` "
      "and the frozen `results/p6-E1.tau.json` and `results/p6-E2.tau.json`. Every number is a named slot; none is "
      "entered by hand. Registration: `prereg/p6-v1.1.md` (tag `prereg-p6-v1.1`). Departures: `prereg/DEVIATIONS.md`.")
    a("")
    a("## Runs")
    a("")
    a("| experiment | status | records cached | invalid | spend, USD | returned models | thresholds recomputed |")
    a("|---|---|---|---|---|---|---|")
    for e in ("E1", "E2"):
        a(f"| {e} | {s(e + '.status')} | {s(e + '.n_calls')} | {s(e + '.invalid')} | {s(e + '.spend_usd')} | "
          f"{s(e + '.models')} | {s(e + '.tau_recomputed_match')} |")
    a("")
    a(f"Bootstrap: {s('analysis.bootstrap_b')} resamples, seed {s('analysis.bootstrap_seed')}, item-clustered.")
    a("")
    a("## Hypotheses (Holm over H1 and the four H2 tests, alpha 0.05)")
    a("")
    a(f"Evaluated: {s('hypotheses_evaluated')}.")
    a("")
    a("| hypothesis | estimate | 95% CI | p | Holm-adjusted p | verdict |")
    a("|---|---|---|---|---|---|")
    a(f"| H1: no E1 cell's unsafe rate exceeds its split-B bound (Bonferroni over 6 cells) | see E1 table | | "
      f"{s('H1.p')} | {s('H1.p_adj')} | {s('H1.verdict')} |")
    for sen in SENSORS:
        for label, arm in labels("E2"):
            k = f"H2.{sen}.{label}"
            a(f"| H2, {SENSOR_NAME[sen]}, arm {arm}: picked reduct has lower exposure at 30% noise | "
              f"{s(k + '.estimate')} (b = {s(k + '.b')}, c = {s(k + '.c')}, n = {s(k + '.n')}) | "
              f"[{s(k + '.ci_lo')}, {s(k + '.ci_hi')}] | {s(k + '.p')} | {s(k + '.p_adj')} | {s(k + '.verdict')} |")
    a("")
    a("## E1: the bound on CH-C1 (test split; Clopper-Pearson 95%)")
    a("")
    a("| sensor | noise | unsafe rate (all items) | split-B bound B+ | verdict-change rate | split-B bound B | "
      "approval wrong / unknown | residency wrong / unknown | no unsafe change | H1 cell p |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for sen in SENSORS:
        for n in NOISES:
            p = f"E1.{sen}.{n}"
            a(f"| {SENSOR_NAME[sen]} | {NOISE_NAME[n]} | {cp(p + '.unsafe')} | {s(p + '.unsafe_bound')} | "
              f"{cp(p + '.change')} | {s(p + '.change_bound')} | "
              f"{s(p + '.approval_assertion.wrong')} / {s(p + '.approval_assertion.unknown')} | "
              f"{s(p + '.data_residency_region.wrong')} / {s(p + '.data_residency_region.unknown')} | "
              f"{s(p + '.s3_held')} | {s(p + '.h1_p')} |")
    a("")
    a("Bound labels (a bound greater than 1 is vacuous: it holds for any sensor): " + "; ".join(
        f"{SENSOR_NAME[sen]} {NOISE_NAME[n]}: B+ {s(f'E1.{sen}.{n}.unsafe_bound')}{s(f'E1.{sen}.{n}.unsafe_bound.label')}, "
        f"B {s(f'E1.{sen}.{n}.change_bound')}{s(f'E1.{sen}.{n}.change_bound.label')}"
        for sen in SENSORS for n in NOISES) + ".")
    a("")
    a(f"Looseness: split B has n = {s('E1.floor.n')} items per field; with zero observed errors the one-sided 95% "
      f"Clopper-Pearson upper bound is {s('E1.floor.approval_assertion')} for approval_assertion and "
      f"{s('E1.floor.data_residency_region')} for data_residency_region, so a sensor with no split-B errors still "
      f"gets B+ = {s('E1.floor.unsafe_bound')} and B = {s('E1.floor.change_bound')}.")
    a("")
    a("## E2: substitution test on CH-B1 (test split)")
    a("")
    a("| sensor | arm | picked reduct | sensed fields (picked / other) | estimated bound (R_branch / R_env) | "
      "noise | picked: change | other: change | picked: unsafe | other: unsafe |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for sen in SENSORS:
        for label, arm in labels("E2"):
            q = f"E2.{sen}.{label}"
            for n in NOISES:
                a(f"| {SENSOR_NAME[sen]} | {arm} | {s(q + '.picked')} | "
                  f"{s(q + '.sensed.R_branch')} / {s(q + '.sensed.R_env')} | "
                  f"{s(q + '.estimated_bound.R_branch')} / {s(q + '.estimated_bound.R_env')} | {NOISE_NAME[n]} | "
                  f"{cp(f'{q}.{n}.picked.change')} | {cp(f'{q}.{n}.other.change')} | "
                  f"{cp(f'{q}.{n}.picked.unsafe')} | {cp(f'{q}.{n}.other.unsafe')} |")
    a("")
    a("The sensed-field columns list R_branch first, then R_env.")
    a("")
    a("## E3: admission ablation (from the E1 caches; no new calls)")
    a("")
    a("Coverage is the fraction of test items decided; the unsafe rate is over all test items; exposure is among "
      "decided items.")
    a("")
    a("| ceiling | unknown | sensor | noise | coverage | unsafe rate | exposure among decided |")
    a("|---|---|---|---|---|---|---|")
    for eps in (CEILING, CEILING_E3):
        tag = f"eps{round(eps * 100)}"
        for policy in ("deny", "escalate"):
            for sen in SENSORS:
                for n in NOISES:
                    p = f"E3.{tag}.{policy}.{sen}.{n}"
                    a(f"| {round(eps * 100)}% | {policy} | {SENSOR_NAME[sen]} | {NOISE_NAME[n]} | "
                      f"{s(p + '.coverage')} | {s(p + '.unsafe')} | {s(p + '.exposure')} |")
    a("")
    a("## E4: witness and implementation check (synthetic, no model)")
    a("")
    a("| witness | measured deny-to-allow | checker exact rate | S1 bound | pipeline matches checker |")
    a("|---|---|---|---|---|")
    for tag, name in (("a", "(a) disjoint errors"), ("b", "(b) joint errors, AND contract")):
        a(f"| {name} | {cp(f'E4.{tag}.unsafe')} | {s(f'E4.{tag}.exact_unsafe')} | {s(f'E4.{tag}.exact_bound')} | "
          f"{s(f'E4.{tag}.matches_checker')} |")
    a("")
    a(f"Check passes: {s('E4.check_passes')}.")
    a("")
    a("## E5: calibration against the assertion label (test split; secondary)")
    a("")
    a("| domain | sensor | answers | Spiegelhalter Z | p | Brier | BSS |")
    a("|---|---|---|---|---|---|---|")
    for e, dom in (("E1", "CH-C1"), ("E2", "CH-B1")):
        for sen in SENSORS:
            q = f"E5.{e}.{sen}"
            a(f"| {dom} | {SENSOR_NAME[sen]} | {s(q + '.n')} | {s(q + '.z')} | {s(q + '.p')} | {s(q + '.brier')} | "
              f"{s(q + '.bss')} |")
    a("")
    a("Everything outside the hypotheses table is descriptive.")
    a("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write-template", action="store_true")
    args = ap.parse_args(argv)
    if args.write_template:
        TEMPLATE_PATH.write_text(build(), encoding="utf-8")
        print(f"analysis_p6: wrote {TEMPLATE_PATH}")
        return 0
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    slots = compute()
    filled = fill_all(template, slots)
    if args.check:
        print(f"analysis_p6: {len(slots)} slots computed; template fills cleanly")
        return 0
    RESULTS_PATH.write_text(filled, encoding="utf-8")
    SLOTS_JSON_PATH.write_text(json.dumps(slots, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"analysis_p6: wrote {RESULTS_PATH} ({len(SLOT_RE.findall(template))} slots)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
