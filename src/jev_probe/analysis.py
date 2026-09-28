"""§6–§8 analysis. Reads ONLY the raw-response cache (plus the pinned engine for the
§7 predicate baseline and the quoted sibling figures), computes every registered
metric, and fills the result slots.

    python -m jev_probe.analysis          # fill results/jev-v1.md from responses/
    python -m jev_probe.analysis --check  # compute, verify every slot fills, write nothing

Operational choices (implementations of the registered text, fixed before any data):
- Item outcome: majority of 3 repeats; an invalid answer is neither yes nor no, so it
  counts as a non-detection for every question (and never as a false positive).
- Calibration uses every valid individual answer; invalid answers carry no p_yes.
- Channel calibration scopes pool that channel's four class questions.
- H1: difference d - chance; bootstrap resamples corrupted and clean items separately
  (clean items carry all four of their question outcomes); two-sided p from the
  null-shifted bootstrap distribution; 95% percentile CI.
- H2: Spiegelhalter numerator sum (y-p)(1-2p) divided by its item-clustered bootstrap
  SE; normal two-sided p. BSS is 1 - Brier/Brier_ref with a per-question base rate
  recomputed inside each resample; 95% percentile CI.
- H3: exact McNemar on discordant pairs; CI from a paired item bootstrap.
- Every bootstrap draws from a fresh random.Random(20260928) with 10,000 resamples.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jev_probe.cache import Cache, parse_answers
from jev_probe.constants import (
    ALPHA,
    BOOTSTRAP_B,
    BOOTSTRAP_SEED,
    CACHE_PATH,
    CONDITIONS,
    FPR_GUARD,
    METADATA_BORNE,
    N_CLEAN,
    N_ITEMS,
    PAYLOAD_VISIBLE,
    REPEATS,
    RESULTS_PATH,
    ROOT,
    SLOTS_JSON_PATH,
    TEMPLATE_PATH,
    USD_PER_INPUT_TOKEN,
)
from jev_probe.questions import CLASS_QUESTIONS, QUESTION_IDS, class_of_question, question_for_class
from jev_probe.stats import (
    bootstrap_p_centered,
    fleiss_kappa,
    holm,
    mcnemar_exact,
    quantile,
    sd,
    two_sided_normal_p,
    wilson,
)

CLASSES = (
    "stale_master_data",
    "superseded_golden_record",
    "silent_unit_change",
    "duplicate_vendor_conflicting_terms",
    "cross_source_contradiction",
    "schema_drift",
    "missing_mandatory_field",
    "plausible_outlier",
)  # TAXONOMY_V0 declared order (checked against the engine in tests)
CHANNEL_QUESTIONS = {
    "metadata": tuple(question_for_class(c) for c in METADATA_BORNE),
    "payload": tuple(question_for_class(c) for c in PAYLOAD_VISIBLE),
}
SLOT_RE = re.compile(r"\{\{([A-Za-z0-9_.\-]+)\}\}")
NE = "not evaluated"


def class_at(j: int) -> str | None:
    return None if j < N_CLEAN else CLASSES[(j - N_CLEAN) % len(CLASSES)]


def truth(j: int, qid: str) -> bool:
    c = class_at(j)
    return c is None if qid == "Q0_valid" else c == class_of_question(qid)


def fmt(x: Any, nd: int = 4) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        if math.isnan(x):
            return "n/a"
        return f"{x:.{nd}f}"
    return str(x)


def fmt_p(p: float) -> str:
    if isinstance(p, float) and not math.isnan(p) and p < 1e-4:
        return f"{p:.2e}"
    return fmt(p)


# --------------------------------------------------------------------------- data


@dataclass
class Data:
    answers: dict[tuple[int, str, int], dict[str, float | None]]
    attempts: list[dict[str, Any]]
    calls: dict[tuple[int, str, int], dict[str, Any]]
    retries: list[dict[str, Any]]
    run_events: list[dict[str, Any]]
    manifests: list[dict[str, Any]]


def load(cache_path: Path = CACHE_PATH) -> Data:
    recs = Cache(cache_path).records()
    attempts = [r for r in recs if r.get("kind") == "attempt"]
    by_key: dict[tuple[str, int, str, int, int, int], dict[str, Any]] = {}
    for a in attempts:
        by_key[(a["segment"], a["j"], a["condition"], a["repeat"], a["request_n"], a["attempt"])] = a
    calls: dict[tuple[int, str, int], dict[str, Any]] = {}
    answers: dict[tuple[int, str, int], dict[str, float | None]] = {}
    for r in recs:
        if r.get("kind") != "call":
            continue
        key = (r["j"], r["condition"], r["repeat"])
        if key in calls:
            raise ValueError(f"duplicate call record for {key}")
        final = by_key.get((r["segment"], r["j"], r["condition"], r["repeat"],
                            r["final_request_n"], r["final_attempt"]))
        if final is None:
            raise ValueError(f"call {key}: final attempt missing from cache")
        # Answers are re-derived from the raw response body, not trusted from the summary.
        derived = ({q: None for q in QUESTION_IDS} if final["http_status"] == 422
                   else parse_answers(final["response_body"]))
        if derived != r["answers"]:
            raise ValueError(f"call {key}: summary answers disagree with the raw response")
        calls[key] = r
        answers[key] = derived
    return Data(
        answers=answers,
        attempts=attempts,
        calls=calls,
        retries=[r for r in recs if r.get("kind") == "retry"],
        run_events=[r for r in recs if r.get("kind") == "run_event"],
        manifests=[r["manifest"] for r in recs if r.get("kind") in ("manifest", "run_event")],
    )


class Outcomes:
    def __init__(self, data: Data) -> None:
        self.a = data.answers

    def complete(self, j: int, cond: str) -> bool:
        return all((j, cond, r) in self.a for r in range(1, REPEATS + 1))

    def items(self, cond: str) -> list[int]:
        return [j for j in range(N_ITEMS) if self.complete(j, cond)]

    def all_complete(self) -> bool:
        return all(self.complete(j, c) for j in range(N_ITEMS) for c in CONDITIONS)

    def votes(self, j: int, cond: str, q: str) -> tuple[int, int, int]:
        ps = [self.a[(j, cond, r)][q] for r in range(1, REPEATS + 1)]
        yes = sum(1 for p in ps if p is not None and p >= 0.5)
        no = sum(1 for p in ps if p is not None and p < 0.5)
        return yes, no, len(ps) - yes - no

    def maj_yes(self, j: int, cond: str, q: str) -> bool:
        return self.votes(j, cond, q)[0] >= 2

    def maj_no(self, j: int, cond: str, q: str) -> bool:
        return self.votes(j, cond, q)[1] >= 2

    def detect(self, j: int, cond: str, q: str) -> bool:
        """Q0_valid detects on majority 'no'; a class question on majority 'yes'.
        Invalid answers count as non-detections."""
        return self.maj_no(j, cond, q) if q == "Q0_valid" else self.maj_yes(j, cond, q)

    def answers(self, cond: str, qids: Sequence[str], items: Sequence[int] | None = None):
        """(j, qid, p_yes, y) over every valid individual answer."""
        items = self.items(cond) if items is None else items
        for j in items:
            for r in range(1, REPEATS + 1):
                row = self.a[(j, cond, r)]
                for q in qids:
                    p = row[q]
                    if p is not None:
                        yield j, q, p, 1.0 if truth(j, q) else 0.0


def rate_slots(out: dict[str, str], prefix: str, k: int, n: int) -> None:
    lo, hi = wilson(k, n)
    out[f"{prefix}.k"] = fmt(k)
    out[f"{prefix}.n"] = fmt(n)
    out[f"{prefix}.rate"] = fmt(k / n if n else math.nan)
    out[f"{prefix}.lo"] = fmt(lo)
    out[f"{prefix}.hi"] = fmt(hi)


# ---------------------------------------------------------------- §6 descriptive


def detection_slots(o: Outcomes, out: dict[str, str]) -> None:
    for cond in CONDITIONS:
        items = o.items(cond)
        for c in CLASSES:
            js = [j for j in items if class_at(j) == c]
            for q in (question_for_class(c), "Q0_valid"):
                rate_slots(out, f"detect.{cond}.{c}.{q}", sum(o.detect(j, cond, q) for j in js), len(js))
        clean = [j for j in items if class_at(j) is None]
        rate_slots(out, f"fpr.{cond}.Q0_valid", sum(o.maj_no(j, cond, "Q0_valid") for j in clean), len(clean))
        for q in CLASS_QUESTIONS:
            rate_slots(out, f"fpr.{cond}.{q}", sum(o.maj_yes(j, cond, q) for j in clean), len(clean))
        rate_slots(out, f"fpr.{cond}.any_class",
                   sum(any(o.maj_yes(j, cond, q) for q in CLASS_QUESTIONS) for j in clean), len(clean))


def calib_scopes() -> dict[str, tuple[str, ...]]:
    scopes: dict[str, tuple[str, ...]] = {"all": QUESTION_IDS}
    scopes.update({q: (q,) for q in QUESTION_IDS})
    scopes["channel_metadata"] = CHANNEL_QUESTIONS["metadata"]
    scopes["channel_payload"] = CHANNEL_QUESTIONS["payload"]
    return scopes


def brier_bss(rows: list[tuple[int, str, float, float]]) -> tuple[float, float, int]:
    """Brier over answers, and BSS vs a constant base-rate predictor per question."""
    if not rows:
        return math.nan, math.nan, 0
    se = sum((p - y) ** 2 for _, _, p, y in rows)
    by_q: dict[str, list[float]] = {}
    for _, q, _, y in rows:
        by_q.setdefault(q, []).append(y)
    ref = 0.0
    for ys in by_q.values():
        b = sum(ys) / len(ys)
        ref += sum((b - y) ** 2 for y in ys)
    bss = 1 - se / ref if ref > 0 else math.nan
    return se / len(rows), bss, len(rows)


def calibration_slots(o: Outcomes, out: dict[str, str]) -> None:
    for cond in CONDITIONS:
        for name, qids in calib_scopes().items():
            brier, bss, n = brier_bss(list(o.answers(cond, qids)))
            out[f"brier.{cond}.{name}"] = fmt(brier)
            out[f"brier.{cond}.{name}.n"] = fmt(n)
            out[f"bss.{cond}.{name}"] = fmt(bss)
        rows = list(o.answers(cond, QUESTION_IDS))
        bins: list[list[tuple[float, float]]] = [[] for _ in range(10)]
        for _, _, p, y in rows:
            bins[min(int(p * 10), 9)].append((p, y))
        ece = 0.0
        for b, cell in enumerate(bins):
            n = len(cell)
            k = int(sum(y for _, y in cell))
            lo, hi = wilson(k, n)
            mean_p = sum(p for p, _ in cell) / n if n else math.nan
            obs = k / n if n else math.nan
            if n:
                ece += n / len(rows) * abs(mean_p - obs)
            pre = f"reliability.{cond}.b{b}"
            out[f"{pre}.n"] = fmt(n)
            out[f"{pre}.mean_p"] = fmt(mean_p)
            out[f"{pre}.obs"] = fmt(obs)
            out[f"{pre}.lo"] = fmt(lo)
            out[f"{pre}.hi"] = fmt(hi)
        out[f"reliability.{cond}.ece"] = fmt(ece if rows else math.nan)


def kappa_slots(o: Outcomes, out: dict[str, str]) -> None:
    for cond in CONDITIONS:
        items = o.items(cond)
        for q in QUESTION_IDS:
            k = fleiss_kappa([list(o.votes(j, cond, q)) for j in items])
            out[f"kappa.{cond}.{q}"] = "undefined (no variation)" if k is None else fmt(k)


def ops_slots(data: Data, o: Outcomes, out: dict[str, str]) -> None:
    retried_calls = {(r["j"], r["condition"], r["repeat"]) for r in data.retries}
    total_in = total_out = 0
    for cond in CONDITIONS:
        att = [a for a in data.attempts if a["condition"] == cond]
        lat_a = [a["latency_s"] for a in att if a["http_status"] is not None]
        calls = [c for k, c in data.calls.items() if k[1] == cond]
        lat_c = [c["latency_total_s"] for c in calls]
        for name, xs in (("attempt", lat_a), ("call", lat_c)):
            pre = f"latency.{cond}.{name}"
            out[f"{pre}.n"] = fmt(len(xs))
            out[f"{pre}.median"] = fmt(quantile(xs, 0.5), 3)
            out[f"{pre}.p90"] = fmt(quantile(xs, 0.9), 3)
            out[f"{pre}.p99"] = fmt(quantile(xs, 0.99), 3)
            out[f"{pre}.max"] = fmt(max(xs) if xs else math.nan, 3)
        out[f"latency.{cond}.calls_with_retries"] = fmt(sum(1 for k in retried_calls if k[1] == cond))
        out[f"latency.{cond}.calls_rerequested"] = fmt(sum(1 for c in calls if c["n_requests"] > 1))
        tin = sum(a["usage_input_tokens"] or 0 for a in att)
        tout = sum(a["usage_output_tokens"] or 0 for a in att)
        total_in += tin
        total_out += tout
        usd = tin * USD_PER_INPUT_TOKEN
        n_items = len({c["j"] for c in calls})
        out[f"cost.{cond}.input_tokens"] = fmt(tin)
        out[f"cost.{cond}.output_tokens"] = fmt(tout)
        out[f"cost.{cond}.usd"] = fmt(usd, 6)
        out[f"cost.{cond}.usd_per_call"] = fmt(usd / len(calls) if calls else math.nan, 8)
        out[f"cost.{cond}.usd_per_item"] = fmt(usd / n_items if n_items else math.nan, 8)
        out[f"cost.{cond}.input_tokens_per_call"] = fmt(tin / len(calls) if calls else math.nan, 1)
        n_ans = sum(1 for c in calls) * len(QUESTION_IDS)
        n_inv = sum(c["n_invalid"] for c in calls)
        out[f"invalid.{cond}"] = fmt(n_inv / n_ans if n_ans else math.nan)
        out[f"invalid.{cond}.answers"] = fmt(n_inv)
        out[f"invalid.{cond}.calls_all_invalid"] = fmt(sum(1 for c in calls if c["status"] == "invalid"))
        out[f"invalid.{cond}.calls_partial"] = fmt(sum(1 for c in calls if c["status"] == "partial_invalid"))
    n_calls = len(data.calls)
    n_items_all = len({k[0] for k in data.calls})
    usd = total_in * USD_PER_INPUT_TOKEN
    out["cost.total.input_tokens"] = fmt(total_in)
    out["cost.total.output_tokens"] = fmt(total_out)
    out["cost.total.usd"] = fmt(usd, 6)
    out["cost.total.usd_per_call"] = fmt(usd / n_calls if n_calls else math.nan, 8)
    out["cost.total.usd_per_item"] = fmt(usd / n_items_all if n_items_all else math.nan, 8)
    out["cost.price_usd_per_1e9_input"] = fmt(USD_PER_INPUT_TOKEN * 1e9, 2)
    out["cost.attempts"] = fmt(len(data.attempts))


# ------------------------------------------------------------------ §7 baselines


def predicate_slots(out: dict[str, str]) -> dict[str, Any]:
    from sarc_dq.dq_spec import load_spec

    from jev_probe.items import build_items

    spec = load_spec()
    pag = spec.by_verif("PAG")
    covered = {c for con in pag for c in con.targets}
    fails: dict[int, set[str]] = {}
    any_fail: dict[int, bool] = {}
    for it in build_items():
        res = spec.evaluate(it.evidence, verif="PAG")
        failed = [con for con, r in res if not r.passed]
        any_fail[it.j] = bool(failed)
        fails[it.j] = {c for con in failed for c in con.targets}
    summary: dict[str, Any] = {"uncovered": sorted(set(CLASSES) - covered)}
    for c in CLASSES:
        js = [j for j in range(N_ITEMS) if class_at(j) == c]
        pre = f"baseline.predicate.{c}"
        if c in covered:
            k = sum(c in fails[j] for j in js)
            rate_slots(out, f"{pre}.{question_for_class(c)}", k, len(js))
            summary[c] = k / len(js)
        else:
            for f in ("k", "n", "rate", "lo", "hi"):
                out[f"{pre}.{question_for_class(c)}.{f}"] = "uncovered"
            summary[c] = "uncovered"
        rate_slots(out, f"{pre}.Q0_valid", sum(any_fail[j] for j in js), len(js))
    clean = [j for j in range(N_ITEMS) if class_at(j) is None]
    rate_slots(out, "baseline.predicate.fpr.Q0_valid", sum(any_fail[j] for j in clean), len(clean))
    for c in CLASSES:
        q = question_for_class(c)
        if c in covered:
            rate_slots(out, f"baseline.predicate.fpr.{q}", sum(c in fails[j] for j in clean), len(clean))
        else:
            for f in ("k", "n", "rate", "lo", "hi"):
                out[f"baseline.predicate.fpr.{q}.{f}"] = "uncovered"
    out["baseline.predicate.uncovered"] = ", ".join(summary["uncovered"]) or "none"
    out["baseline.predicate.n_constraints_pag"] = fmt(len(pag))
    return summary


def sibling_root() -> Path:
    lock = tomllib.loads((ROOT / "engines.lock").read_text(encoding="utf-8"))["dqSarc"]
    return (ROOT / lock["path"]).resolve()


def ladder_slots(out: dict[str, str]) -> None:
    sib = sibling_root()
    ladder = json.loads((sib / "paper/data/h1-ladder/reference_summary.json").read_text("utf-8"))
    for rung, v in ladder["rungs"].items():
        name = rung.removeprefix("claude-")
        out[f"baseline.ladder.{name}.adr"] = str(v["metadata_borne_adr"])
        out[f"baseline.ladder.{name}.flag_fraction"] = str(v["flag_fraction"])
        out[f"baseline.ladder.{name}.marker_auc"] = str(v["marker_auc"])
    tex = "".join(p.read_text("utf-8") for p in sorted((sib / "paper/generated").glob("*.tex")))
    macros = dict(re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", tex))
    out["baseline.ladder.endpoint_diff"] = macros["LadderEndpointDiff"]
    out["baseline.ladder.endpoint_ci_lo"] = macros["LadderEndpointCILo"]
    out["baseline.ladder.endpoint_ci_hi"] = macros["LadderEndpointCIHi"]
    out["baseline.ladder.trend_per_tier"] = macros["LadderTrendPerTier"]
    h2 = json.loads((sib / "paper/data/h2-detection/reference_summary.json").read_text("utf-8"))
    for c, v in h2["per_class_detection"].items():
        out[f"baseline.ladder.h2critic.{c}"] = str(v["critic"])
    out["baseline.ladder.h2critic.metadata_mean"] = str(h2["critic_detection_metadata"])


# ----------------------------------------------------------------- §8 hypotheses


def boot(rng: random.Random, xs: Sequence[Any]) -> list[Any]:
    return rng.choices(xs, k=len(xs))


def h1_test(o: Outcomes, cond: str, classes: Sequence[str], b: int) -> dict[str, float]:
    qs = [question_for_class(c) for c in classes]
    det = [1.0 if o.detect(j, cond, question_for_class(class_at(j))) else 0.0
           for j in range(N_ITEMS) if class_at(j) in classes]
    clean = [float(sum(o.maj_yes(j, cond, q) for q in qs)) for j in range(N_ITEMS) if class_at(j) is None]
    d = sum(det) / len(det)
    chance = sum(clean) / (len(clean) * len(qs))
    est = d - chance
    rng = random.Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(b):
        dd = boot(rng, det)
        cc = boot(rng, clean)
        draws.append(sum(dd) / len(dd) - sum(cc) / (len(cc) * len(qs)))
    return {"d": d, "chance": chance, "estimate": est, "ci_lo": quantile(draws, 0.025),
            "ci_hi": quantile(draws, 0.975), "p": bootstrap_p_centered(est, draws),
            "n_corrupted": float(len(det)), "n_pairs_clean": float(len(clean) * len(qs))}


def _item_vectors(o: Outcomes, cond: str, qids: Sequence[str]) -> list[tuple[float, ...]]:
    """Per item and question: n, sum y, sum sq. error, Spiegelhalter numerator and variance."""
    vecs = []
    for j in o.items(cond):
        v: list[float] = []
        for q in qids:
            n = sy = se = num = var = 0.0
            for r in range(1, REPEATS + 1):
                p = o.a[(j, cond, r)][q]
                if p is None:
                    continue
                y = 1.0 if truth(j, q) else 0.0
                n += 1
                sy += y
                se += (p - y) ** 2
                num += (y - p) * (1 - 2 * p)
                var += (1 - 2 * p) ** 2 * p * (1 - p)
            v += [n, sy, se, num, var]
        vecs.append(tuple(v))
    return vecs


def _h2_stats(tot: Sequence[float], nq: int) -> tuple[float, float, float, float]:
    se = num = var = ref = 0.0
    for k in range(nq):
        n, sy, s, nu, va = tot[5 * k: 5 * k + 5]
        se += s
        num += nu
        var += va
        if n:
            base = sy / n
            ref += n * base * base - 2 * base * sy + sy
    bss = 1 - se / ref if ref > 0 else math.nan
    return num, var, bss, se


def h2_test(o: Outcomes, cond: str, qids: Sequence[str], b: int) -> dict[str, float]:
    vecs = _item_vectors(o, cond, qids)
    total = [sum(col) for col in zip(*vecs)]
    num, var, bss, _ = _h2_stats(total, len(qids))
    rng = random.Random(BOOTSTRAP_SEED)
    nums, bsss = [], []
    for _ in range(b):
        tot = [sum(col) for col in zip(*boot(rng, vecs))]
        nu, _, bs, _ = _h2_stats(tot, len(qids))
        nums.append(nu)
        bsss.append(bs)
    se_boot = sd(nums)
    if se_boot and not math.isnan(se_boot):
        z = num / se_boot
        p = two_sided_normal_p(z)
    else:
        z = 0.0 if num == 0 else math.copysign(math.inf, num)
        p = 1.0 if num == 0 else 0.0
    z_classic = num / math.sqrt(var) if var > 0 else math.nan
    bs_ok = [x for x in bsss if not math.isnan(x)]
    return {"num": num, "se": se_boot, "z": z, "p": p, "z_classic": z_classic,
            "p_classic": two_sided_normal_p(z_classic) if not math.isnan(z_classic) else math.nan,
            "bss": bss, "bss_lo": quantile(bs_ok, 0.025), "bss_hi": quantile(bs_ok, 0.975)}


def h2_verdict(p_adj: float, lo: float, hi: float) -> str:
    if p_adj < ALPHA or (not math.isnan(hi) and hi < 0):
        return "refuted"
    if p_adj >= ALPHA and not math.isnan(lo) and lo > 0:
        return "supported"
    return "inconclusive"


def h3_test(o: Outcomes, items: Sequence[int], q_of: Callable[[int], str], b: int) -> dict[str, float]:
    pairs = [(o.detect(j, "PM", q_of(j)), o.detect(j, "P", q_of(j))) for j in items]
    bb = sum(1 for pm, p in pairs if pm and not p)
    cc = sum(1 for pm, p in pairs if p and not pm)
    diffs = [float(pm) - float(p) for pm, p in pairs]
    est = sum(diffs) / len(diffs)
    rng = random.Random(BOOTSTRAP_SEED)
    draws = [sum(s) / len(s) for s in (boot(rng, diffs) for _ in range(b))]
    return {"b": float(bb), "c": float(cc), "n": float(len(pairs)), "estimate": est,
            "pm_rate": sum(pm for pm, _ in pairs) / len(pairs), "p_rate": sum(p for _, p in pairs) / len(pairs),
            "ci_lo": quantile(draws, 0.025), "ci_hi": quantile(draws, 0.975), "p": mcnemar_exact(bb, cc)}


def hypothesis_slots(o: Outcomes, out: dict[str, str], b: int) -> dict[str, Any]:
    keys_h1 = ("d", "chance", "estimate", "ci_lo", "ci_hi", "p", "p_adj", "verdict")
    keys_h1c = ("d", "chance", "estimate", "ci_lo", "ci_hi", "p", "p_holm4")
    keys_h2 = ("z", "z_classic", "num", "se", "p", "p_classic", "p_adj", "bss", "bss_lo", "bss_hi", "verdict")
    keys_h3 = ("b", "c", "n", "pm_rate", "p_rate", "estimate", "ci_lo", "ci_hi", "p", "p_adj",
               "fpr_P", "fpr_PM", "fpr_delta", "guard", "verdict")
    h2_scopes = {"PM": ("PM", QUESTION_IDS), "P": ("P", QUESTION_IDS),
                 "PM.channel_metadata": ("PM", CHANNEL_QUESTIONS["metadata"]),
                 "PM.channel_payload": ("PM", CHANNEL_QUESTIONS["payload"]),
                 "P.channel_metadata": ("P", CHANNEL_QUESTIONS["metadata"]),
                 "P.channel_payload": ("P", CHANNEL_QUESTIONS["payload"])}
    if not o.all_complete():
        for k in keys_h1:
            out[f"H1.PM.pooled.{k}"] = NE
            out[f"H1.P.pooled.{k}"] = NE
        for c in METADATA_BORNE:
            for k in keys_h1c:
                out[f"H1.PM.{c}.{k}"] = NE
        for s in h2_scopes:
            for k in keys_h2:
                out[f"H2.{s}.{k}"] = NE
        for s in ("meta", "all", "Q0"):
            for k in keys_h3:
                out[f"H3.{s}.{k}"] = NE
        return {"evaluated": False}

    h1 = h1_test(o, "PM", METADATA_BORNE, b)
    h2 = h2_test(o, "PM", QUESTION_IDS, b)
    meta_items = [j for j in range(N_ITEMS) if class_at(j) in METADATA_BORNE]
    h3 = h3_test(o, meta_items, lambda j: question_for_class(class_at(j)), b)
    adj = holm([h1["p"], h2["p"], h3["p"]])
    h1["p_adj"], h2["p_adj"], h3["p_adj"] = adj

    # H1 verdict
    if h1["p_adj"] < ALPHA and h1["estimate"] > 0:
        h1v = "supported: detection above chance"
    elif h1["p_adj"] < ALPHA and h1["estimate"] < 0:
        h1v = "detection below chance"
    else:
        h1v = "not supported (no significant difference from chance)"
    h1["verdict"] = h1v
    # H2 verdict
    h2["verdict"] = h2_verdict(h2["p_adj"], h2["bss_lo"], h2["bss_hi"])
    # H3 verdict with the FPR guard
    clean = [j for j in range(N_ITEMS) if class_at(j) is None]
    fpr_p = sum(o.maj_no(j, "P", "Q0_valid") for j in clean) / len(clean)
    fpr_pm = sum(o.maj_no(j, "PM", "Q0_valid") for j in clean) / len(clean)
    guard_tripped = fpr_pm - fpr_p > FPR_GUARD
    h3.update({"fpr_P": fpr_p, "fpr_PM": fpr_pm, "fpr_delta": fpr_pm - fpr_p})
    h3["guard"] = "tripped" if guard_tripped else "not tripped"
    if h3["p_adj"] < ALPHA and h3["b"] > h3["c"]:
        h3v = ("detection gain confounded by false positives" if guard_tripped
               else "supported: PM detects more than P")
    elif h3["p_adj"] < ALPHA and h3["c"] > h3["b"]:
        h3v = "significant difference favouring P"
    else:
        h3v = "not supported (no significant difference)"
    h3["verdict"] = h3v

    def put(prefix: str, d: dict[str, Any], keys: Sequence[str]) -> None:
        for k in keys:
            v = d[k]
            if k.startswith("p") and k not in ("pm_rate", "p_rate") and isinstance(v, float):
                out[f"{prefix}.{k}"] = fmt_p(v)
            elif k in ("b", "c", "n"):
                out[f"{prefix}.{k}"] = fmt(int(v))
            else:
                out[f"{prefix}.{k}"] = fmt(v)

    put("H1.PM.pooled", h1, keys_h1)
    put("H2.PM", h2, keys_h2)
    put("H3.meta", h3, keys_h3)

    # Secondary H1: per class (Holm within the four), and pooled in P.
    per = {c: h1_test(o, "PM", (c,), b) for c in METADATA_BORNE}
    for c, p4 in zip(METADATA_BORNE, holm([per[c]["p"] for c in METADATA_BORNE])):
        per[c]["p_holm4"] = p4
        put(f"H1.PM.{c}", per[c], keys_h1c)
    h1p = h1_test(o, "P", METADATA_BORNE, b)
    h1p["p_adj"] = h1p["p"]
    h1p["verdict"] = ("above chance" if h1p["p"] < ALPHA and h1p["estimate"] > 0 else
                      "below chance" if h1p["p"] < ALPHA and h1p["estimate"] < 0 else
                      "no significant difference")
    put("H1.P.pooled", h1p, keys_h1)
    # Secondary H2 (unadjusted p): condition P, and per channel.
    for s, (cond, qids) in h2_scopes.items():
        if s == "PM":
            continue
        r = h2_test(o, cond, qids, b)
        r["p_adj"] = r["p"]
        r["verdict"] = h2_verdict(r["p"], r["bss_lo"], r["bss_hi"])
        put(f"H2.{s}", r, keys_h2)
    # Secondary H3: all 200 corrupted items (own class question), and Q0_valid.
    corrupted = [j for j in range(N_ITEMS) if class_at(j) is not None]
    for s, q_of in (("all", lambda j: question_for_class(class_at(j))), ("Q0", lambda j: "Q0_valid")):
        r = h3_test(o, corrupted, q_of, b)
        r.update({"p_adj": r["p"], "fpr_P": fpr_p, "fpr_PM": fpr_pm, "fpr_delta": fpr_pm - fpr_p,
                  "guard": h3["guard"]})
        r["verdict"] = ("PM detects more" if r["p"] < ALPHA and r["b"] > r["c"] else
                        "P detects more" if r["p"] < ALPHA and r["c"] > r["b"] else
                        "no significant difference")
        put(f"H3.{s}", r, keys_h3)
    return {"evaluated": True, "H1": h1, "H2": h2, "H3": h3}


# --------------------------------------------------------------------- run slots


def run_slots(data: Data, o: Outcomes, out: dict[str, str], evaluated: bool) -> None:
    status = data.run_events[-1]["status"] if data.run_events else "NOT RUN"
    man = data.manifests[-1] if data.manifests else {}
    models = sorted({c["returned_model"] for c in data.calls.values()})
    committed = sum(a["charged_input_tokens"] for a in data.attempts) * USD_PER_INPUT_TOKEN
    out["run.status"] = status
    out["run.spend_usd"] = fmt(sum((a["usage_input_tokens"] or 0) for a in data.attempts)
                               * USD_PER_INPUT_TOKEN, 6)
    out["run.spend_committed_usd"] = fmt(committed, 6)
    out["run.model_versions"] = ", ".join(models) or "none"
    out["run.model_version_changed"] = "MODEL_VERSION_CHANGED" if len(models) > 1 else "no"
    out["run.requested_model"] = man.get("requested_model", "n/a")
    out["run.prompt_sha256"] = man.get("context_sha256", "n/a")
    out["run.questions_sha256"] = man.get("questions_sha256", "n/a")
    out["run.docs_sha256"] = man.get("docs_sha256", "n/a")
    out["run.sdk_version"] = man.get("sdk", {}).get("version", "n/a")
    out["run.engine_pin"] = man.get("engine_pin", {}).get("commit", "n/a")
    out["run.prereg_commit"] = man.get("prereg_commit", "n/a")
    out["run.endpoint"] = man.get("endpoint", "n/a")
    out["run.n_calls"] = fmt(len(data.calls))
    out["run.n_attempts"] = fmt(len(data.attempts))
    out["run.n_retries"] = fmt(len(data.retries))
    out["run.n_segments"] = fmt(len(man.get("segments", [])))
    out["run.items_complete"] = fmt(sum(1 for j in range(N_ITEMS) if all(o.complete(j, c) for c in CONDITIONS)))
    out["run.hypotheses_evaluated"] = "yes" if evaluated else "no"


# ------------------------------------------------------------------------ driver


def compute(cache_path: Path = CACHE_PATH, *, bootstrap_b: int = BOOTSTRAP_B) -> dict[str, str]:
    data = load(cache_path)
    o = Outcomes(data)
    out: dict[str, str] = {}
    detection_slots(o, out)
    calibration_slots(o, out)
    kappa_slots(o, out)
    ops_slots(data, o, out)
    predicate_slots(out)
    ladder_slots(out)
    h = hypothesis_slots(o, out, bootstrap_b)
    run_slots(data, o, out, h["evaluated"])
    out["analysis.bootstrap_b"] = fmt(bootstrap_b)
    out["analysis.bootstrap_seed"] = fmt(BOOTSTRAP_SEED)
    return out


def fill(template: str, slots: dict[str, str]) -> str:
    missing = sorted({m for m in SLOT_RE.findall(template) if m not in slots})
    if missing:
        raise KeyError(f"{len(missing)} slot(s) have no computed value: {missing[:20]}")
    return SLOT_RE.sub(lambda m: slots[m.group(1)], template)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=CACHE_PATH)
    ap.add_argument("--template", type=Path, default=TEMPLATE_PATH)
    ap.add_argument("--out", type=Path, default=RESULTS_PATH)
    ap.add_argument("--slots-json", type=Path, default=SLOTS_JSON_PATH)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    slots = compute(args.cache)
    filled = fill(args.template.read_text(encoding="utf-8"), slots)
    if args.check:
        print(f"analysis: {len(slots)} slots computed; template fills cleanly")
        return 0
    args.out.write_text(filled, encoding="utf-8")
    args.slots_json.write_text(json.dumps(slots, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"analysis: wrote {args.out} ({len(SLOT_RE.findall(args.template.read_text()))} slots filled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
