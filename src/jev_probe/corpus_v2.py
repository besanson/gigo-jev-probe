"""jev-v2 §3–§5: items, the deterministic verdict, the registered corpus generator, and the
keyword extractor (arm C).

The corpus is generated at run time from the seed and is never hand-edited or committed as
data. Every random draw for item `i` comes from `random.Random(f"jev-v2:20261003:{i}")`, in the
fixed order below, so a record is identical across runs and its noise draws are paired across
noise levels (the perturbed sets are nested: 0% ⊂ 10% ⊂ 30%).
"""

from __future__ import annotations

import hashlib
import random
import sys
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jev_probe.constants import ROOT
from jev_probe.constants_v2 import (
    CORPUS_SEED,
    FIELD,
    FIELD_ABSENT,
    FIELD_VALID,
    N_ITEMS,
    N_VALIDATION,
    NOISE,
    POPULATION_SIZE,
    SAMPLE_SEED,
    SIBLING,
    SPLIT_SEED,
)

# §5 approval statement banks (verbatim from the registration)
VALID_BANK = (
    "Approval: granted by {approver} on {date}.",
    "Change approved by {approver} under {ref}.",
    "CAB approval recorded for {ref} on {date}.",
)
ABSENT_BANK = (
    "Approval: none recorded.",
    "Awaiting approval; no approver has signed off.",
    "No CAB approval is on record for this change.",
)
# §5 neutral filler bank: eight sentences, none mentions approval.
FILLER_BANK = (
    "Rollout follows the standard runbook for this service.",
    "Monitoring dashboards were checked before the request was raised.",
    "The change is scoped to the listed repository only.",
    "Unit tests passed on the latest pipeline run.",
    "No customer-facing downtime is expected.",
    "The requester is available on the incident channel during the change.",
    "Related documentation will be updated after the change.",
    "This request supersedes no earlier ticket.",
)
APPROVERS = ("a.okafor", "j.lindqvist", "m.tanaka", "r.castillo", "s.novak", "l.haddad")
COMMENTERS = ("d.moreau", "k.osei", "p.ivanova", "t.brennan", "y.nakamura", "h.silva")

# §6 C: keyword stems
VALID_STEMS = ("Approval: granted", "Change approved by", "CAB approval recorded")
ABSENT_STEMS = ("Approval: none recorded", "Awaiting approval", "No CAB approval")


class DesignMismatch(Exception):
    """§3.5: the population or the design facts differ from the registration."""


def sibling_root() -> Path:
    lock = tomllib.loads((ROOT / "engines.lock").read_text(encoding="utf-8"))[SIBLING]
    return (ROOT / lock["path"]).resolve()


@lru_cache(maxsize=1)
def _engine() -> tuple[Any, Any]:
    root = str(sibling_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    from domain_v4 import executable_reachable_tuples_v4  # type: ignore[import-not-found]
    from losses_v4 import load_loss_registry_v4  # type: ignore[import-not-found]

    return executable_reachable_tuples_v4(), load_loss_registry_v4()


def population() -> list[Any]:
    return _engine()[0]


def verdict(t: Any) -> str:
    """§4: deny iff any registered loss predicate holds."""
    return "deny" if any(pred(t) for pred in _engine()[1].values()) else "allow"


def sensed_verdict(t: Any, sensed: str) -> str:
    """§4: true/false substitute the field; unknown denies (the gate cannot observe it)."""
    if sensed == "true":
        return verdict(t.with_property(FIELD, FIELD_VALID))
    if sensed == "false":
        return verdict(t.with_property(FIELD, FIELD_ABSENT))
    return "deny"


def approval_sensitive(t: Any) -> bool:
    return sensed_verdict(t, "true") != sensed_verdict(t, "false")


@dataclass(frozen=True)
class Item:
    i: int  # index into executable_reachable_tuples_v4()
    split: str  # "validation" | "test"
    t: Any

    @property
    def truth(self) -> str:
        return getattr(self.t, FIELD)

    @property
    def truth_bool(self) -> bool:
        return self.truth == FIELD_VALID


def item_indices() -> tuple[list[int], set[int]]:
    """§3.2–3.3: the capped sample and the validation subset."""
    items = sorted(random.Random(SAMPLE_SEED).sample(range(POPULATION_SIZE), N_ITEMS))
    validation = set(random.Random(SPLIT_SEED).sample(items, N_VALIDATION))
    return items, validation


def build_items() -> list[Item]:
    pop = population()
    if len(pop) != POPULATION_SIZE:
        raise DesignMismatch(f"population {len(pop)} != {POPULATION_SIZE}")
    idx, validation = item_indices()
    return [Item(i, "validation" if i in validation else "test", pop[i]) for i in idx]


def design_facts(items: list[Item]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for split in ("validation", "test"):
        s = [it for it in items if it.split == split]
        out[split] = {
            "items": len(s),
            "valid": sum(it.truth == FIELD_VALID for it in s),
            "allow": sum(verdict(it.t) == "allow" for it in s),
            "sensitive": sum(approval_sensitive(it.t) for it in s),
        }
    out["population_sensitive"] = sum(approval_sensitive(t) for t in population())
    return out


@dataclass(frozen=True)
class Draws:
    ref: str
    filler: str
    statement: str
    u: float
    kind: str  # "missing" | "contradictory"
    comment: str


def draws(item: Item) -> Draws:
    """All random draws for one item, in the registered order."""
    rng = random.Random(f"jev-v2:{CORPUS_SEED}:{item.i}")
    ref = "CR-" + "".join(str(rng.randrange(10)) for _ in range(6))
    filler = rng.choice(FILLER_BANK)
    approver = rng.choice(APPROVERS)
    date = f"2026-{rng.randrange(1, 10):02d}-{rng.randrange(1, 29):02d}"
    bank = VALID_BANK if item.truth == FIELD_VALID else ABSENT_BANK
    statement = rng.choice(bank).format(approver=approver, date=date, ref=ref)
    u = rng.random()
    kind = rng.choice(("missing", "contradictory"))
    opp_bank = ABSENT_BANK if item.truth == FIELD_VALID else VALID_BANK
    opp_approver = rng.choice(APPROVERS)
    opp_date = f"2026-{rng.randrange(1, 10):02d}-{rng.randrange(1, 29):02d}"
    opposite = rng.choice(opp_bank).format(approver=opp_approver, date=opp_date, ref=ref)
    commenter = rng.choice(COMMENTERS)
    return Draws(ref, filler, statement, u, kind, f"Comment from {commenter}: {opposite}")


def perturbation(item: Item, noise: str) -> str:
    """'none', 'missing' or 'contradictory' for this item at this noise level."""
    d = draws(item)
    return d.kind if d.u < NOISE[noise] else "none"


def render(item: Item, noise: str) -> str:
    """§5: the rendered change request for this item at this noise level."""
    d = draws(item)
    t = item.t
    lines = [
        f"Change request {d.ref}",
        f"Requested by: {t.actor_identity}, acting as {t.delegated_role}",
        f"Repository: {t.repository}, branch {t.branch}, environment {t.environment}",
        f"Resource owner: {t.resource_owner}",
        f"Operation: {t.operation}",
        f"Deployment window: {t.deployment_window}",
        f"Data classification: {t.data_classification}",
        f"Notes: {d.filler}",
    ]
    kind = perturbation(item, noise)
    if kind != "missing":
        lines.append(d.statement)
    if kind == "contradictory":
        lines.append(d.comment)
    return "\n".join(lines)


def record_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def keyword_score(text: str) -> float:
    """§6 C: 1.0 only valid stems, 0.0 only absent stems, 0.5 both or neither."""
    v = any(s in text for s in VALID_STEMS)
    a = any(s in text for s in ABSENT_STEMS)
    if v and not a:
        return 1.0
    if a and not v:
        return 0.0
    return 0.5


def generator_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
