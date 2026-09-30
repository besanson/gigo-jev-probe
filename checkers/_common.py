"""Shared finite models and output for the paper 6 checkers (prereg/p6-v1.1.md §3).

Finite model families (all exhaustive):
- B12: binary fields, n = 1 and 2, every nonempty reachable set R of {0,1}^n, every verdict
  function g: R -> {allow, deny}, every sufficient contract C (a subset of the fields that
  determines g on R).
- B3: three binary fields, R = {0,1}^3, every g, the full contract.
- T2: two ternary fields, R = {0,1,2}^2, every g, the full contract.

For each model, every sensed-field set F_s within C is considered, every true tuple t in R, and
every admitted vector over F_s whose entries are any declared value or None (unknown).
"""

from __future__ import annotations

import contextlib
import itertools
import json
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from checkers._provenance import head_sha, inputs_hash
from sensed_authority.bound import ContractModel

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out" / "p6" / "checkers"
PROVENANCE = ("sarc-suite-one-pass: checkers/_provenance.py ported verbatim with attribution "
              "(sarc-suite-one-pass@782261e via sarc-authority-derivation@cfb321e)")
CORE_INPUTS = [ROOT / "checkers" / "_common.py", ROOT / "checkers" / "_provenance.py",
               ROOT / "src" / "sensed_authority" / "bound.py"]


@dataclass(frozen=True)
class FiniteModel:
    family: str
    model: ContractModel


def _verdicts(reachable: Sequence[dict[str, Any]]) -> Iterator[dict[tuple[Any, ...], str]]:
    keys = [tuple(t.values()) for t in reachable]
    for bits in itertools.product(("allow", "deny"), repeat=len(keys)):
        yield dict(zip(keys, bits, strict=True))


def _sufficient_subsets(fields: Sequence[str], reachable: Sequence[dict[str, Any]],
                        table: dict[tuple[Any, ...], str]) -> Iterator[tuple[str, ...]]:
    for r in range(1, len(fields) + 1):
        for sub in itertools.combinations(fields, r):
            seen: dict[tuple[Any, ...], str] = {}
            if all(seen.setdefault(tuple(t[f] for f in sub), table[tuple(t.values())]) == table[tuple(t.values())]
                   for t in reachable):
                yield sub


def finite_models() -> Iterator[FiniteModel]:
    for n in (1, 2):
        fields = [f"f{i}" for i in range(1, n + 1)]
        cube = [dict(zip(fields, v, strict=True)) for v in itertools.product((0, 1), repeat=n)]
        for size in range(1, len(cube) + 1):
            for reach in itertools.combinations(cube, size):
                for table in _verdicts(reach):
                    for contract in _sufficient_subsets(fields, reach, table):
                        yield FiniteModel("B12", ContractModel(
                            contract, reach, lambda t, tb=table: tb[tuple(t.values())], {f: (0, 1) for f in fields}))
    for fields, values, family in ((["f1", "f2", "f3"], (0, 1), "B3"), (["f1", "f2"], (0, 1, 2), "T2")):
        cube = [dict(zip(fields, v, strict=True)) for v in itertools.product(values, repeat=len(fields))]
        for table in _verdicts(cube):
            yield FiniteModel(family, ContractModel(
                fields, cube, lambda t, tb=table: tb[tuple(t.values())], {f: values for f in fields}))


def sensed_sets(contract: Sequence[str]) -> Iterator[tuple[str, ...]]:
    for r in range(len(contract) + 1):
        yield from itertools.combinations(contract, r)


def admitted_vectors(model: ContractModel, sensed: Sequence[str]) -> Iterator[dict[str, Any]]:
    for combo in itertools.product(*((*model.domains[f], None) for f in sensed)):
        yield dict(zip(sensed, combo, strict=True))


def write_output(name: str, statement: str, inputs: list[Path], result: dict[str, Any],
                 out_dir: Path = OUT_DIR) -> Path:
    with contextlib.chdir(ROOT):  # the ported helpers hash repo-relative paths and read HEAD
        stamp = {"inputs_hash": inputs_hash([p.relative_to(ROOT) for p in sorted(set(CORE_INPUTS + inputs))]),
                 "generated_at_head_sha": head_sha()}
    body = {"checker": name, "statement": statement, "provenance": PROVENANCE, **stamp, **result}
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def out_dir_from_argv() -> Path:
    return Path(sys.argv[1]) if len(sys.argv) > 1 else OUT_DIR
