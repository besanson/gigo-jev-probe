"""Paper 6 corpora (prereg/p6-v1.1.md §5.2, §5.4, §5.5): items, splits A and B, the registered
generators, both labels, and the contract models for exposure.

Every random draw for an item comes from that item's generator, in the fixed order of
`_draw_e1` / `_draw_e2`, so a record is identical across runs and its noise draws are shared
across noise levels (the perturbed sets are nested: 0% ⊂ 10% ⊂ 30%). The contradicting
statement is drawn whether or not it is shown, for the same reason.
"""

from __future__ import annotations

import dataclasses
import hashlib
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from experiments.constants_p6 import (
    ABSENT_REQUEST_BASE,
    ABSENT_REQUEST_SPAN,
    APPROVAL_DATES,
    DOC_PREFIX,
    E1_BANKS,
    E1_CONTRACT,
    E1_CORPUS_SEED,
    E1_FIELDS,
    E1_N_ITEMS,
    E1_N_VALIDATION,
    E1_POPULATION,
    E1_SAMPLE_SEED,
    E1_SPLIT_SEED,
    E2_ARMS,
    E2_BANKS,
    E2_CORPUS_SEED,
    E2_REDUCTS,
    EXPIRED_K,
    FIELD_VALUES,
    NOISE,
    SLUGS,
    SPLIT_AB_SEED,
    SUBMITTED_BASE,
    SUBMITTED_SPAN,
    VALID_K,
    VALIDITY_DAYS,
    iso,
)
from jev_probe.corpus_v2 import APPROVERS, COMMENTERS, FILLER_BANK
from jev_probe.corpus_v2 import build_items as build_items_v2
from jev_probe.corpus_v2 import sibling_root
from sensed_authority.bound import ContractModel


class DesignMismatch(Exception):
    """The population differs from the registration."""


# ------------------------------------------------------------------ items and splits


@dataclass(frozen=True)
class Item:
    exp: str  # "E1" | "E2"
    i: int  # index into the domain's executable reachable tuples
    split: str  # "validation" | "test"
    part: str  # "A" | "B" | "test"
    t: Any

    def tuple_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self.t)


def split_ab(validation: set[int]) -> tuple[set[int], set[int]]:
    """§5.2: split A is half the validation items (seed 20261107), split B the rest."""
    ordered = sorted(validation)
    a = set(random.Random(SPLIT_AB_SEED).sample(ordered, len(ordered) // 2))
    return a, set(ordered) - a


def _sibling_last() -> None:
    """Keep the sibling checkout at the END of sys.path. jev-v2's loader (frozen) inserts it first,
    and the sibling has its own top-level `checkers` package, which would shadow this repository's."""
    root = str(sibling_root())
    while root in sys.path:
        sys.path.remove(root)
    sys.path.append(root)


@lru_cache(maxsize=1)
def _v8() -> tuple[list[Any], dict[str, Any]]:
    _sibling_last()
    from domain_v8 import executable_reachable_tuples_v8  # type: ignore[import-not-found]
    from losses_v8 import load_loss_registry_v8  # type: ignore[import-not-found]

    return executable_reachable_tuples_v8(), load_loss_registry_v8()


def build_e1_items() -> list[Item]:
    pop = _v8()[0]
    if len(pop) != E1_POPULATION:
        raise DesignMismatch(f"CH-C1 population {len(pop)} != {E1_POPULATION}")
    idx = sorted(random.Random(E1_SAMPLE_SEED).sample(range(E1_POPULATION), E1_N_ITEMS))
    validation = set(random.Random(E1_SPLIT_SEED).sample(idx, E1_N_VALIDATION))
    a, _ = split_ab(validation)
    return [Item("E1", i, "validation" if i in validation else "test",
                 ("A" if i in a else "B") if i in validation else "test", pop[i]) for i in idx]


def build_e2_items() -> list[Item]:
    v2 = build_items_v2()
    _sibling_last()
    a, _ = split_ab({it.i for it in v2 if it.split == "validation"})
    return [Item("E2", it.i, it.split, ("A" if it.i in a else "B") if it.split == "validation" else "test", it.t)
            for it in v2]


def build_items(exp: str) -> list[Item]:
    return build_e1_items() if exp == "E1" else build_e2_items()


# ------------------------------------------------------------------ truth


def e1_truth(item: Item) -> tuple[str, date]:
    """(true approval_assertion, recorded request_date) from the item's generator."""
    d = _draw_e1(item)
    return d["approval_value"], d["request_date"]


def approval_token_from_assertion(assertion: str | None, request_date: date) -> str | None:
    """§5.4 / I2: validity and expiry are computed, never sensed. None (unknown) stays None."""
    if assertion is None:
        return None
    if assertion == "not_recorded":
        return "absent"
    approved = date.fromisoformat(assertion.split(":", 1)[1])
    return "valid" if 0 <= (request_date - approved).days <= VALIDITY_DAYS else "expired"


def truth_values(item: Item, arm: int | None = None) -> dict[str, str]:
    t = item.t
    if item.exp == "E1":
        return {"approval_assertion": e1_truth(item)[0], "data_residency_region": t.data_residency_region}
    second = E2_ARMS[arm]["sensed"]
    return {"approval_assertion": "recorded" if t.approval_token == "valid" else "not_recorded",
            second: getattr(t, second)}


def fields_for(exp: str, arm: int | None = None) -> tuple[str, ...]:
    return E1_FIELDS if exp == "E1" else ("approval_assertion", E2_ARMS[arm]["sensed"])


# ------------------------------------------------------------------ generators


def _bank(exp: str, field: str, value: str, split: str) -> tuple[str, ...]:
    banks = E1_BANKS if exp == "E1" else E2_BANKS
    key = "recorded" if value.startswith("recorded") else value
    validation, test = banks[(field, key)]
    return validation if split == "validation" else test


def _statement(rng: random.Random, exp: str, field: str, value: str, split: str, ref: str) -> tuple[str, str]:
    """(statement text, value it asserts). Draws: phrase, then its placeholders."""
    template = rng.choice(_bank(exp, field, value, split))
    approver = rng.choice(APPROVERS)
    doc = DOC_PREFIX + "".join(str(rng.randrange(10)) for _ in range(4))
    slug = rng.choice(SLUGS)
    d = value.split(":", 1)[1] if value.startswith("recorded:") else ""
    when = iso(rng.choice(APPROVAL_DATES))
    return template.format(approver=approver, d=d, ref=ref, doc=doc, slug=slug, date=when), value


def _noise(rng: random.Random, exp: str, field: str, value: str, split: str, ref: str) -> dict[str, Any]:
    u = rng.random()
    kind = rng.choice(("missing", "contradictory"))
    others = [v for v in FIELD_VALUES[(exp, field)] if v != value]
    opposite_value = rng.choice(others)
    opposite, _ = _statement(rng, exp, field, opposite_value, split, ref)
    actor = rng.choice(COMMENTERS)
    return {"u": u, "kind": kind, "opposite_value": opposite_value, "comment": f"Comment from {actor}: {opposite}"}


def _header(rng: random.Random) -> dict[str, Any]:
    ref = "CR-" + "".join(str(rng.randrange(10)) for _ in range(6))
    submitted = SUBMITTED_BASE + timedelta(days=rng.randint(*SUBMITTED_SPAN))
    return {"ref": ref, "submitted": iso(submitted), "filler": rng.choice(FILLER_BANK)}


@lru_cache(maxsize=None)
def _draw_e1_cached(i: int, approval_token: str, split: str, residency: str) -> dict[str, Any]:
    rng = random.Random(f"p6-v1.1:E1:{E1_CORPUS_SEED}:{i}")
    out = _header(rng)
    if approval_token in ("valid", "expired"):
        approved = rng.choice(APPROVAL_DATES)
        k = rng.randint(*(VALID_K if approval_token == "valid" else EXPIRED_K))
        out["approval_value"] = f"recorded:{iso(approved)}"
        out["request_date"] = approved + timedelta(days=k)
    else:
        out["approval_value"] = "not_recorded"
        out["request_date"] = ABSENT_REQUEST_BASE + timedelta(days=rng.randint(*ABSENT_REQUEST_SPAN))
    fields = {"approval_assertion": out["approval_value"], "data_residency_region": residency}
    out["statements"] = {f: _statement(rng, "E1", f, v, split, out["ref"])[0] for f, v in fields.items()}
    out["noise"] = {f: _noise(rng, "E1", f, v, split, out["ref"]) for f, v in fields.items()}
    out["values"] = fields
    return out


def _draw_e1(item: Item) -> dict[str, Any]:
    return _draw_e1_cached(item.i, item.t.approval_token, item.split, item.t.data_residency_region)


@lru_cache(maxsize=None)
def _draw_e2_cached(i: int, arm: int, split: str, values: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    rng = random.Random(f"p6-v1.1:E2:{arm}:{E2_CORPUS_SEED}:{i}")
    out = _header(rng)
    fields = dict(values)
    out["statements"] = {f: _statement(rng, "E2", f, v, split, out["ref"])[0] for f, v in fields.items()}
    out["noise"] = {f: _noise(rng, "E2", f, v, split, out["ref"]) for f, v in fields.items()}
    out["values"] = fields
    return out


def draws(item: Item, arm: int | None = None) -> dict[str, Any]:
    if item.exp == "E1":
        return _draw_e1(item)
    return _draw_e2_cached(item.i, arm, item.split, tuple(truth_values(item, arm).items()))


def perturbation(item: Item, field: str, noise: str, arm: int | None = None) -> str:
    n = draws(item, arm)["noise"][field]
    return n["kind"] if n["u"] < NOISE[noise] else "none"


def render(item: Item, noise: str, arm: int | None = None) -> str:
    d = draws(item, arm)
    lines = [f"Change request {d['ref']}", f"Submitted: {d['submitted']}", f"Notes: {d['filler']}"]
    comments = []
    for f in fields_for(item.exp, arm):
        kind = perturbation(item, f, noise, arm)
        if kind != "missing":
            lines.append(d["statements"][f])
        if kind == "contradictory":
            comments.append(d["noise"][f]["comment"])
    return "\n".join(lines + comments)


def assertion_labels(item: Item, field: str, noise: str, arm: int | None = None) -> dict[str, bool]:
    """§5.4 F11: for each candidate value, does the rendered record carry a statement from its bank?"""
    d = draws(item, arm)
    kind = perturbation(item, field, noise, arm)
    asserted = set()
    if kind != "missing":
        asserted.add(d["values"][field])
    if kind == "contradictory":
        asserted.add(d["noise"][field]["opposite_value"])
    return {v: v in asserted for v in FIELD_VALUES[(item.exp, field)]}


def record_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generator_sha256() -> str:
    h = hashlib.sha256()
    for p in (Path(__file__), Path(__file__).with_name("constants_p6.py")):
        h.update(p.read_bytes())
    return h.hexdigest()


# ------------------------------------------------------------------ contracts and verdicts


def _verdict_model(tuples: list[Any], losses: dict[str, Any], contract: tuple[str, ...]) -> ContractModel:
    rows = [dict(dataclasses.asdict(t), _deny=any(p(t) for p in losses.values())) for t in tuples]
    domains = {f: sorted({r[f] for r in rows}) for f in contract}
    return ContractModel(contract, rows, lambda r: "deny" if r["_deny"] else "allow", domains)


@lru_cache(maxsize=1)
def e1_model() -> ContractModel:
    pop, losses = _v8()
    return _verdict_model(pop, losses, E1_CONTRACT)


@lru_cache(maxsize=2)
def e2_model(reduct: str) -> ContractModel:
    from jev_probe.corpus_v2 import _engine

    pop, losses = _engine()
    _sibling_last()
    return _verdict_model(pop, losses, E2_REDUCTS[reduct])


def e1_outcome(item: Item, admitted: dict[str, str | None]) -> tuple[bool, bool]:
    """(verdict changed, deny -> allow) on K, with approval_token computed from the admitted assertion."""
    _, request_date = e1_truth(item)
    t = item.tuple_dict()
    sensed = {"approval_token": approval_token_from_assertion(admitted["approval_assertion"], request_date),
              "data_residency_region": admitted["data_residency_region"]}
    return e1_model().outcome(t, sensed)


def e2_outcome(item: Item, reduct: str, admitted: dict[str, str | None]) -> tuple[bool, bool]:
    """(verdict changed, deny -> allow) under one reduct; fields outside the reduct are ignored."""
    t = item.tuple_dict()
    a = admitted["approval_assertion"]
    sensed: dict[str, Any] = {"approval_token": None if a is None else ("valid" if a == "recorded" else "absent")}
    for f in ("branch", "environment"):
        if f in admitted and f in E2_REDUCTS[reduct]:
            sensed[f] = admitted[f]
    return e2_model(reduct).outcome(t, sensed)


def sensed_sets(arm: int) -> dict[str, list[str]]:
    """§5.5: sensed-field set of each reduct in an arm."""
    second = E2_ARMS[arm]["sensed"]
    return {r: ["approval_assertion"] + ([second] if second in fields else []) for r, fields in E2_REDUCTS.items()}


def design_facts(items: list[Item]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part in ("A", "B", "test"):
        s = [it for it in items if it.part == part]
        facts: dict[str, Any] = {"items": len(s)}
        if s and s[0].exp == "E1":
            facts["approval"] = {k: sum(e1_truth(it)[0].startswith(k) for it in s) for k in ("recorded", "not")}
            facts["token"] = {k: sum(it.t.approval_token == k for it in s) for k in ("valid", "expired", "absent")}
            facts["residency"] = {k: sum(it.t.data_residency_region == k for it in s) for k in ("us", "eu", "apac")}
            facts["allow"] = sum(e1_model().table[tuple(it.tuple_dict()[f] for f in E1_CONTRACT)] == "allow"
                                 for it in s)
        elif s:
            facts["approval_valid"] = sum(it.t.approval_token == "valid" for it in s)
        out[part] = facts
    return out
