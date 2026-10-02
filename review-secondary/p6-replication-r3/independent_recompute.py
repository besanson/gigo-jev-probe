"""Independent audit: no imports from gigo-jev-probe.

Inputs: raw response bodies, frozen admission thresholds, registered seeds,
and the pinned sibling's domain/loss definitions (the experimental specification).
Statistics use SciPy beta/binomial distributions, not repository functions.
Manuscript templates are used only AFTER computation to locate comparison cells.
"""
import dataclasses
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import re
import sys
from datetime import date, timedelta

import numpy as np
from scipy.stats import beta, binom

BASE = Path(__file__).resolve().parent
ROOT = BASE / "gigo-jev-probe"
sys.path.insert(0, str(BASE / "sarc-authority-derivation"))
from domain_v8 import executable_reachable_tuples_v8
from losses_v8 import load_loss_registry_v8
from domain_v4 import executable_reachable_tuples_v4
from losses_v4 import load_loss_registry_v4

CONTRACTS = {
    "K": ("approval_token", "data_residency_region", "delegated_role",
          "destination_endpoint_class", "evidence_retention_class", "network_zone",
          "operation", "resource_environment", "workflow_stage"),
    "R_branch": ("approval_token", "branch", "data_classification", "delegated_role",
                 "operation", "repository", "resource_owner"),
    "R_env": ("approval_token", "environment", "data_classification", "delegated_role",
              "operation", "repository", "resource_owner"),
}
DATES = [date.fromisoformat(d) for d in
         ("2026-06-01", "2026-06-15", "2026-07-01", "2026-07-15", "2026-08-01", "2026-08-15")]
NOISES = ("n00", "n10", "n30")
SENSORS = ("jev", "llm")
VALUES = {
    "E1": {
        "approval_assertion": ["not_recorded"] + [f"recorded:{d}" for d in DATES],
        "data_residency_region": ["us", "eu", "apac"],
    },
    "E2": {
        "approval_assertion": ["recorded", "not_recorded"],
        "branch": ["main", "staging", "feature"],
        "environment": ["production", "staging", "development"],
    },
}
computed = {}
raw = {}
cache_checks = {}


def fmt(x):
    if isinstance(x, (int, np.integer)):
        return str(x)
    if isinstance(x, (float, np.floating)):
        return f"{x:.4f}"
    return str(x)


def put(key, x):
    computed[key] = fmt(x)
    raw[key] = float(x) if isinstance(x, np.floating) else x


def put_p(key, p):
    computed[key] = f"{p:.2e}" if p < .0001 else f"{p:.4f}"
    raw[key] = p


def upper(k, n, alpha=.05):
    return 1.0 if k == n else float(beta.ppf(1-alpha, k+1, n-k))


def rates(prefix, k, n):
    lo = 0.0 if k == 0 else float(beta.ppf(.025, k, n-k+1))
    hi = 1.0 if k == n else float(beta.ppf(.975, k+1, n-k))
    for suffix, value in [("k", k), ("n", n), ("rate", k/n), ("lo", lo), ("hi", hi)]:
        put(f"{prefix}.{suffix}", value)


def key(r):
    return r["exp"], r["arm"], r["i"], r["noise"], r["field"]


def parse_raw(attempt, exp):
    body = json.loads(attempt["response_body"])
    field = attempt["field"]
    vals = VALUES[exp][field]
    if attempt["arm"] == "jev":
        def qid(v):
            if field == "approval_assertion":
                return ("Q_appr_none" if v == "not_recorded" else
                        "Q_appr_recorded" if v == "recorded" else
                        "Q_appr_" + v.split(":")[1].replace("-", ""))
            return {"data_residency_region": "Q_residency_", "branch": "Q_branch_",
                    "environment": "Q_env_"}[field] + v
        return {v: body["answers"][qid(v)]["noul"] for v in vals}
    text = "".join(c["text"] for c in body["content"] if c["type"] == "text")
    text = "{" + text
    text = re.sub(r"```(?:json)?", "", text).replace("```", "")
    obj = json.JSONDecoder().raw_decode(text[text.index("{"):])[0]
    return {v: obj["p_" + (v.split(":")[1].replace("-", "_") if ":" in v else v)]
            for v in vals}


def load_cache(exp):
    calls, attempts = {}, {}
    score_mismatch = []
    rows = [json.loads(line) for line in (ROOT / f"responses/p6-{exp}.jsonl").open()]
    for r in rows:
        if r["kind"] == "attempt":
            attempts[key(r)] = r
        if r["kind"] == "call":
            assert key(r) not in calls, ("duplicate call", key(r))
            if r["score"] is not None:
                score = parse_raw(attempts[key(r)], exp)
                if score != r["score"]:
                    score_mismatch.append(key(r))
                r["score"] = score
            calls[key(r)] = r
    assert not score_mismatch, score_mismatch
    cache_checks[exp] = {
        "calls": len(calls), "invalid": sum(c["score"] is None for c in calls.values()),
        "raw_body_vs_cached_score_mismatches": len(score_mismatch),
        "cache_sha256": hashlib.sha256((ROOT / f"responses/p6-{exp}.jsonl").read_bytes()).hexdigest(),
    }
    return calls


def admit(scores, thresholds):
    if scores is None:
        return None
    candidates = [v for v, score in scores.items() if score >= thresholds[v]["tau_true"]]
    return candidates[0] if len(candidates) == 1 else None


populations = {
    "E1": executable_reachable_tuples_v8(),
    "E2": executable_reachable_tuples_v4(),
}
losses = {"E1": load_loss_registry_v8(), "E2": load_loss_registry_v4()}
assert len(populations["E1"]) == 27000
assert len(populations["E2"]) == 15120
tables = {}
tuples = {}
true_deny = {}
samples = {}
split_b = {}
test = {}
truth = {}
request_dates = {}

for exp, pop in populations.items():
    tuples[exp] = [dataclasses.asdict(t) for t in pop]
    true_deny[exp] = [any(pred(t) for pred in losses[exp].values()) for t in pop]
    seed_sample, seed_split = ((20261101, 20261102) if exp == "E1" else (20261001, 20261002))
    samples[exp] = sorted(random.Random(seed_sample).sample(range(len(pop)), 1000))
    validation = set(random.Random(seed_split).sample(samples[exp], 300))
    a = set(random.Random(20261107).sample(sorted(validation), 150))
    split_b[exp] = sorted(validation-a)
    test[exp] = [i for i in samples[exp] if i not in validation]
    for name in (("K",) if exp == "E1" else ("R_branch", "R_env")):
        fields = CONTRACTS[name]
        table = {}
        for i, t in enumerate(tuples[exp]):
            projection = tuple(t[f] for f in fields)
            value = true_deny[exp][i]
            assert projection not in table or table[projection] == value
            table[projection] = value
        tables[name] = table
    for i in samples[exp]:
        t = tuples[exp][i]
        if exp == "E1":
            rng = random.Random(f"p6-v1.1:E1:20261103:{i}")
            for _ in range(6):
                rng.randrange(10)  # registered CR number
            rng.randint(0, 30)    # submitted date
            rng.choice(range(8)) # neutral filler bank
            if t["approval_token"] in ("valid", "expired"):
                approved = rng.choice(DATES)
                offset = rng.randint(0, 30) if t["approval_token"] == "valid" else rng.randint(31, 90)
                request_dates[i] = approved + timedelta(days=offset)
                approval = f"recorded:{approved}"
            else:
                approval = "not_recorded"
                request_dates[i] = date(2026, 6, 1) + timedelta(days=rng.randint(0, 120))
            truth[exp, i] = {"approval_assertion": approval,
                            "data_residency_region": t["data_residency_region"]}
        else:
            truth[exp, i] = {"approval_assertion": "recorded" if t["approval_token"] == "valid" else "not_recorded",
                            "branch": t["branch"], "environment": t["environment"]}


def outcome(exp, name, i, admitted):
    t = tuples[exp][i]
    sensed = dict(admitted)
    a = sensed.pop("approval_assertion")
    if a is None:
        token = None
    elif a == "not_recorded":
        token = "absent"
    elif exp == "E2":
        token = "valid"
    else:
        days = (request_dates[i] - date.fromisoformat(a.split(":")[1])).days
        token = "valid" if 0 <= days <= 30 else "expired"
    sensed["approval_token"] = token
    projection = tuple(sensed.get(f, t[f]) for f in CONTRACTS[name])
    observed_deny = True if None in projection else tables[name].get(projection, True)
    original = true_deny[exp][i]
    return observed_deny != original, original and not observed_deny


estimates = {}
outcomes = {}
h1 = []
h2 = {}
for exp in ("E1", "E2"):
    calls = load_cache(exp)
    policies = json.loads((ROOT / f"results/p6-{exp}.tau.json").read_text())["sensors"]
    for label, arm, second in ([("E1", None, "data_residency_region")] if exp == "E1" else
                               [("E2.1", 1, "branch"), ("E2.2", 2, "environment")]):
        fields = ["approval_assertion", second]
        for sensor in SENSORS:
            frozen = policies[sensor]["policy"]["thresholds"]
            # Thresholds are pooled by field; split-B estimates are arm-specific.
            field_thresholds = {f: frozen[f] for f in fields}
            for noise in NOISES:
                readings = {}
                for i in samples[exp]:
                    readings[i] = {
                        f: admit(calls[label, sensor, i, noise, f]["score"], field_thresholds[f])
                        for f in fields
                    }
                    expected_split = "test" if i in test[exp] else "validation"
                    assert all(calls[label, sensor, i, noise, f]["split"] == expected_split for f in fields)
                counts = {}
                for f in fields:
                    wrong = sum(readings[i][f] is not None and readings[i][f] != truth[exp, i][f] for i in split_b[exp])
                    unknown = sum(readings[i][f] is None for i in split_b[exp])
                    counts[f] = (wrong, unknown, len(split_b[exp]))
                estimates[label, sensor, noise] = counts
                if exp == "E1":
                    q = f"E1.{sensor}.{noise}"
                    pairs = [outcome(exp, "K", i, readings[i]) for i in test[exp]]
                    outcomes[label, sensor, noise, "K"] = pairs
                    for j, name in enumerate(("change", "unsafe")):
                        rates(q+"."+name, sum(p[j] for p in pairs), len(pairs))
                    bplus = sum(upper(w, n) for w, u, n in counts.values())
                    b = sum(upper(w, n)+upper(u, n) for w, u, n in counts.values())
                    for name, value in [("unsafe_bound", bplus), ("change_bound", b),
                                        ("unsafe_bound_simul", sum(upper(w, n, .025) for w, u, n in counts.values())),
                                        ("change_bound_simul", sum(upper(w, n, .0125)+upper(u, n, .0125) for w, u, n in counts.values()))]:
                        put(q+"."+name, value)
                        put(q+"."+name+".label", " vacuous" if value > 1 else "")
                    for f in fields:
                        put(q+f".{f}.wrong", sum(readings[i][f] is not None and readings[i][f] != truth[exp, i][f] for i in test[exp])/700)
                        put(q+f".{f}.unknown", sum(readings[i][f] is None for i in test[exp])/700)
                    h1.append(float(binom.sf(sum(p[1] for p in pairs)-1, 700, bplus)))
                else:
                    for name in ("R_branch", "R_env"):
                        selected_fields = [f for f in fields if f == "approval_assertion" or f in CONTRACTS[name]]
                        c = [counts[f] for f in selected_fields]
                        q = f"E2.{sensor}.{label}"
                        put(q+f".{noise}.posthoc.{name}.unsafe_bound", sum(upper(w, n) for w, u, n in c))
                        put(q+f".{noise}.posthoc.{name}.change_bound", sum(upper(w, n)+upper(u, n) for w, u, n in c))
                        if noise == "n30":
                            put(q+f".estimated_bound.{name}", sum(upper(w, n)+upper(u, n) for w, u, n in c))
                        outcomes[label, sensor, noise, name] = [outcome(exp, name, i, readings[i]) for i in test[exp]]
            if exp == "E2":
                q = f"E2.{sensor}.{label}"
                pick = min(("R_branch", "R_env"),
                           key=lambda name: (raw[q+f".estimated_bound.{name}"],
                                             1+int(second in CONTRACTS[name]), name))
                other = next(name for name in ("R_branch", "R_env") if name != pick)
                put(q+".picked", pick)
                for noise in NOISES:
                    for role, name in (("picked", pick), ("other", other)):
                        pairs = outcomes[label, sensor, noise, name]
                        for j, metric in enumerate(("change", "unsafe")):
                            rates(q+f".{noise}.{role}.{metric}", sum(p[j] for p in pairs), len(pairs))
                        put(f"d.e2.{sensor}.{label}.{noise}.{name}.unsafe_k", sum(p[1] for p in pairs))
                left = [p[0] for p in outcomes[label, sensor, "n30", pick]]
                right = [p[0] for p in outcomes[label, sensor, "n30", other]]
                b = sum(l and not r for l, r in zip(left, right))
                c = sum(r and not l for l, r in zip(left, right))
                diffs = [int(l)-int(r) for l, r in zip(left, right)]
                rng = random.Random(20261104)
                draws = [sum(diffs[rng.randrange(700)] for _ in range(700))/700 for _ in range(10000)]
                lo, hi = np.quantile(draws, [.025, .975], method="linear")
                p = min(1., 2*float(binom.cdf(min(b, c), b+c, .5))) if b+c else 1.
                h2[f"{sensor}.{label}"] = p
                for suffix, value in [("b", b), ("c", c), ("n", 700),
                                      ("estimate", sum(diffs)/700), ("ci_lo", lo), ("ci_hi", hi)]:
                    put(f"H2.{sensor}.{label}.{suffix}", value)

pvals = {"H1": min(1., 6*min(h1)), **{f"H2.{k}": p for k, p in h2.items()}}
running = 0.
for rank, (name, p) in enumerate(sorted(pvals.items(), key=lambda kv: kv[1])):
    running = max(running, min(1., (len(pvals)-rank)*p))
    put_p(name+".p", p)
    put_p(name+".p_adj", running)
    put(name+".verdict", ("not refuted: no violation detected" if running >= .05 else "refuted: bound violated")
        if name == "H1" else ("supported: picked reduct lower" if running < .05 and raw[name+".estimate"] < 0
                              else "refuted: picked reduct higher" if running < .05 and raw[name+".estimate"] > 0
                              else "not refuted: no significant difference"))
put("d.cells_e1", 6)
put("analysis.bootstrap_b", 10000)
put("analysis.bootstrap_seed", 20261104)

# Exhaustive global condition, computed by equivalence classes of recorded fields.
# For each deny tuple, some assignment of sensed fields permits allow iff an allow
# projection has the same recorded coordinates. No repository contract evaluator is used.
for name, sets in {
    "K": {"approval_residency": ["approval_token", "data_residency_region"]},
    "R_branch": {"approval": ["approval_token"], "approval_branch": ["approval_token", "branch"]},
    "R_env": {"approval": ["approval_token"], "approval_environment": ["approval_token", "environment"]},
}.items():
    exp = "E1" if name == "K" else "E2"
    for label, sensed in sets.items():
        recorded = [f for f in CONTRACTS[name] if f not in sensed]
        allowed_classes = {tuple(t[f] for f in recorded) for i, t in enumerate(tuples[exp]) if not true_deny[exp][i]}
        denies = [t for i, t in enumerate(tuples[exp]) if true_deny[exp][i]]
        flippable = sum(tuple(t[f] for f in recorded) in allowed_classes for t in denies)
        q = f"denyward.{name}.{label}"
        put(q, "yes" if flippable == 0 else "no")
        put(q+".deny_tuples", len(denies))
        put(q+".witness_tuples", flippable)
        put(q+".used_in", "E1" if name == "K" else "E2 arm " + str(
            2 if (name == "R_branch" and label == "approval") or
                 (name == "R_env" and label != "approval") else 1))

# Paper 5's historical choice is specified by its pinned artifact, not by P6 analysis.
chb2 = json.loads((BASE / "sarc-authority-derivation/out/checkers/ch_b2_check.json").read_text())
costs = chb2["cost_model"]["observation_costs"]
paper5 = min(("R_branch", "R_env"), key=lambda name: sum(costs[f] for f in CONTRACTS[name]))
assert set(CONTRACTS[paper5]) == set(chb2["minimum_cost_contract"])
put("E2.paper5_pick", paper5)

# Select every row of every requested table, not all occurrences of a number in prose.
template_lines = (ROOT / "paper/paper6-draft-v0.1.md").read_text().splitlines()
manuscript_lines = (ROOT / "paper/paper6-draft-v0.1-populated.md").read_text().splitlines()
assert len(template_lines) == len(manuscript_lines[:len(template_lines)])  # appendix expands later
target = False
rows, mismatches, uncomputed = [], [], []
names = set()
table_count = 0
inside_table = False
for lineno, line in enumerate(template_lines, 1):
    if line.startswith("# "):
        target = False
        inside_table = False
    if line.startswith("## "):
        target = line.startswith(("## E1:", "## E2:", "## Hypotheses"))
        inside_table = False
    if not target:
        continue
    if not line.startswith("|"):
        inside_table = False
        continue
    if not inside_table:
        table_count += 1
        inside_table = True
    slots = re.findall(r"\{\{([^}]+)\}\}", line)
    if not slots:
        continue
    names.update(slots)
    missing = [s for s in slots if s not in computed]
    if missing:
        uncomputed.extend(missing)
        continue
    rebuilt = re.sub(r"\{\{([^}]+)\}\}", lambda m: computed[m.group(1)], line)
    original = manuscript_lines[lineno-1]
    row = {"line": lineno, "match": rebuilt == original, "manuscript": original, "independent": rebuilt}
    rows.append(row)
    if rebuilt != original:
        mismatches.append(row)

assert not uncomputed, uncomputed
assert not any(k.startswith(("experiments", "jev_probe", "sensed_authority")) for k in sys.modules)
result = {
    "method": __doc__, "cache_checks": cache_checks, "tables_checked": table_count,
    "table_data_rows_checked": len(rows), "distinct_slots_checked": len(names),
    "slot_occurrences_checked": sum(len(re.findall(r"\{\{([^}]+)\}\}", template_lines[r["line"]-1])) for r in rows),
    "mismatch_count": len(mismatches), "mismatches": mismatches,
    "h1_cell_pvalues": h1,
    "computed": {k: computed[k] for k in sorted(names)},
    "raw_values": raw, "split_b_counts": {"|".join(k): v for k, v in estimates.items()},
    "rows": rows,
}
(BASE / "independent-results.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
print(json.dumps({k: result[k] for k in ("cache_checks", "tables_checked", "table_data_rows_checked",
                                        "distinct_slots_checked", "slot_occurrences_checked", "mismatch_count", "mismatches")}, indent=2))
sys.exit(bool(mismatches))
