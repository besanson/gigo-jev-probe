"""§2 item frame and §3 views, built only from functions of the pinned engine.

Ground truth stays on the Item for scoring and never enters `state`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from sarc_dq.records import EvidenceRecord
from sarc_dq.substrate import episode_seed, make_episode
from sarc_dq.taxonomy.classes import TAXONOMY_V0

from jev_probe.constants import (
    BASE_SEED,
    CHANNEL_OF,
    CONTEXT,
    N_CLEAN,
    N_ITEMS,
    PER_CLASS,
    TEST_SPLIT_REMAINDER,
)
from jev_probe.questions import QUESTION_IDS, question_for_class


class ItemConstructionError(RuntimeError):
    """An item failed to construct at the pin: the run aborts before any model call."""


@dataclass(frozen=True)
class Item:
    j: int
    i: int
    seed: int
    cls: str | None  # None for clean items
    evidence: tuple[EvidenceRecord, ...]

    @property
    def channel(self) -> str | None:
        return None if self.cls is None else CHANNEL_OF[self.cls]

    def view(self, condition: str) -> list[dict[str, Any]]:
        if condition == "P":
            return [r.payload_view() for r in self.evidence]
        if condition == "PM":
            return [r.full_view() for r in self.evidence]
        raise ValueError(f"unknown condition {condition!r}")

    def state(self, condition: str) -> dict[str, Any]:
        return {"context": CONTEXT, "evidence": self.view(condition)}

    def truth(self) -> dict[str, bool]:
        """True answer per question: Q0_valid yes iff clean; Q_c yes iff class == c."""
        out = {"Q0_valid": self.cls is None}
        for qid in QUESTION_IDS[1:]:
            out[qid] = self.cls is not None and qid == question_for_class(self.cls)
        return out


def eligible_indices(n: int = N_ITEMS) -> list[int]:
    out: list[int] = []
    i = 0
    while len(out) < n:
        if episode_seed(BASE_SEED, i) % 3 == TEST_SPLIT_REMAINDER:
            out.append(i)
        i += 1
    return out


def class_for_position(j: int) -> str | None:
    if j < N_CLEAN:
        return None
    return TAXONOMY_V0[(j - N_CLEAN) % len(TAXONOMY_V0)].name


def build_item(j: int, i: int) -> Item:
    seed = episode_seed(BASE_SEED, i)
    episode = make_episode(seed, i)
    clean = episode.clean_price_record()
    if j < N_CLEAN:
        if clean.ground_truth.get("corrupted") is not False:
            raise ItemConstructionError(f"j={j}: clean record not tagged clean")
        return Item(j, i, seed, None, (clean,))
    cls = TAXONOMY_V0[(j - N_CLEAN) % len(TAXONOMY_V0)]
    result = cls.inject(clean, episode, random.Random(seed + 1))
    evidence = result.evidence_set()
    gt = result.primary.ground_truth
    if gt.get("corrupted") is not True or gt.get("corruption_class") != cls.name:
        raise ItemConstructionError(f"j={j}: ground-truth tag {gt!r} does not match {cls.name}")
    return Item(j, i, seed, cls.name, evidence)


def build_items() -> list[Item]:
    """The 300 registered items; raises ItemConstructionError if any item fails."""
    items: list[Item] = []
    for j, i in enumerate(eligible_indices()):
        try:
            items.append(build_item(j, i))
        except ItemConstructionError:
            raise
        except Exception as exc:  # any engine failure aborts the run (§2.5)
            raise ItemConstructionError(f"j={j} i={i}: {type(exc).__name__}: {exc}") from exc
    counts: dict[str | None, int] = {}
    for it in items:
        counts[it.cls] = counts.get(it.cls, 0) + 1
    if len(items) != N_ITEMS or counts.get(None) != N_CLEAN:
        raise ItemConstructionError(f"frame has wrong shape: {counts}")
    if any(counts.get(c.name) != PER_CLASS for c in TAXONOMY_V0):
        raise ItemConstructionError(f"frame is not {PER_CLASS} per class: {counts}")
    return items
