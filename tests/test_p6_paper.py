"""Paper 6 manuscript machinery: slots, numeral lint, figure, flips record, citation checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from lint import typed_numerals

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def populate():
    return _load("paper6_populate", ROOT / "paper" / "populate.py")


@pytest.fixture(scope="module")
def slots(populate):
    return populate.build_slots()


def test_every_manuscript_slot_has_a_value(populate, slots) -> None:
    names = populate.slot_names(populate.DRAFT_PATH.read_text(encoding="utf-8"))
    assert names and names <= set(slots)
    assert "{{" not in populate.populated()


def test_populated_draft_is_current(populate) -> None:
    assert populate.POPULATED_PATH.read_text(encoding="utf-8") == populate.populated()


def test_results_slots_pass_through_unchanged(slots) -> None:
    p6 = json.loads((ROOT / "results" / "p6.slots.json").read_text(encoding="utf-8"))
    assert all(slots[k] == v for k, v in p6.items())


def test_derived_flip_totals_agree_with_the_results_and_the_flips_record(slots) -> None:
    flips = json.loads((ROOT / "results" / "p6-flips.json").read_text(encoding="utf-8"))
    assert int(slots["d.unsafe_total"]) == flips["summary"]["flips"] == len(flips["flips"])
    assert int(slots["d.unsafe_e1"]) == flips["summary"]["flips_by_experiment"]["E1"]
    assert int(slots["d.unsafe_e2"]) == flips["summary"]["flips_by_experiment"]["E2"]
    assert slots["d.verdicts_total"] == f"{int(slots['d.verdicts_e1'].replace(',', '')) + int(slots['d.verdicts_e2'].replace(',', '')):,}"


def test_e0_slots_come_from_the_pinned_tag(slots) -> None:
    assert slots["E0.unsafe_total"] == "0"
    assert int(slots["E0.n_verdicts_total"]) > 0
    assert slots["pin.self"] == "e1fc75b"


def test_proof_status_tags_are_verbatim(slots) -> None:
    for st in json.loads((ROOT / "proof_status.json").read_text(encoding="utf-8"))["statements"]:
        assert slots[f"ps.{st['id']}.tag"] == st["tag"]


@pytest.mark.parametrize("text", [
    "The bound is 0.123 here.",
    "We saw 13 flips.",
    "Ceiling of 2%.",
])
def test_typed_numerals_catches_a_hand_typed_number(text: str) -> None:
    assert typed_numerals.find_violations(text)


@pytest.mark.parametrize("text", [
    "The rate is {{E1.jev.n00.unsafe.rate}}.",
    "Section 7 and papers 1 to 5; arm 2 of E2; seed 20261107.",
    "Reproduced in repository issue #2.",
    "Noise levels 0%, 10% and 30%; ceilings 1% and 5%; a 95% interval at 0.05.",
    "Splits of 150, 300 and 700 items from 1,000; 27,000 tuples; 10,000 witness items.",
    "The tag `prereg-p6-v1.1` and commit `2fac5a4`; Claude Haiku 4.5; SHA-256; within 30 days.",
    'A quoted "value 7" and [@chow1970optimum].',
])
def test_typed_numerals_allows_structural_and_registered_numbers(text: str) -> None:
    assert typed_numerals.find_violations(text) == []


def test_typed_numerals_treats_scientific_notation_as_a_number() -> None:
    assert typed_numerals.residual_numbers("p = 1.69e-21") == ["1.69e-21"]


def test_manuscript_passes_the_numeral_lint() -> None:
    assert typed_numerals.main() == 0


def test_figure_is_current_deterministic_and_has_no_number() -> None:
    fig = _load("fig1_pipeline", ROOT / "paper" / "figs" / "fig1_pipeline.py")
    first, second = fig.render(), fig.render()
    assert first == second
    assert fig.text_has_no_digit(fig.LABELS)
    assert not fig.text_has_no_digit([*fig.LABELS, "verdict 2"])
    assert all(path.read_bytes() == data for path, data in first.items())


def test_citation_comparison_detects_mismatches() -> None:
    vc = _load("verify_citations", ROOT / "paper-tex" / "verify_citations.py")
    rec = {"title": "Rough Sets", "authors": ["Zdzisław Pawlak"], "year": 1982, "pages": "341--356",
           "volume": "11", "verify": {"source": "crossref", "venue": "International Journal of Computer"}}
    good = {"title": "Rough sets", "authors": ["Zdzis?aw Pawlak"], "year": 1982, "pages": "341-356",
            "volume": "11", "venue": "International Journal of Computer &amp; Information Sciences"}
    assert vc.compare(rec, good) == []
    for field, bad in (("title", "Rough Set Theory"), ("authors", ["A. Other"]), ("year", 1983),
                       ("pages", "341-357"), ("venue", "Another Journal")):
        assert [m["field"] for m in vc.compare(rec, {**good, field: bad})] == [field]


def test_every_cited_key_is_verified_and_every_verified_citation_is_cited() -> None:
    gates = _load("run_gates", ROOT / "paper-tex" / "gates" / "run_gates.py")
    keys = gates.cited_keys((ROOT / "paper" / "paper6-draft-v0.1.md").read_text(encoding="utf-8"))
    data = json.loads((ROOT / "verified-citations.json").read_text(encoding="utf-8"))
    assert keys == {c["id"] for c in data["citations"]}
    audit = json.loads((ROOT / "paper-tex" / "bib-audit.json").read_text(encoding="utf-8"))
    assert {r["id"] for r in audit["results"] if r["pass"]} == keys


def test_refs_bib_is_generated_from_the_whitelist() -> None:
    grb = _load("generate_refs_bib", ROOT / "paper-tex" / "generate_refs_bib.py")
    assert (ROOT / "paper-tex" / "refs.bib").read_text() == grb.generate()


def test_arxiv_tarball_is_deterministic(tmp_path: Path) -> None:
    mk = _load("make_arxiv_tarball", ROOT / "paper-tex" / "make_arxiv_tarball.py")
    src = tmp_path / "src"
    src.mkdir()
    for name in mk.ARXIV_FILES:
        (src / name).write_text(f"content of {name}\n")
    a, b = tmp_path / "a.tar.gz", tmp_path / "b.tar.gz"
    mk.build_arxiv_tarball(a, src)
    mk.build_arxiv_tarball(b, src)
    assert a.read_bytes() == b.read_bytes()
