"""The combined results note is filled from the slot files only: no unfilled slot, no
hand-typed result, and regenerating it reproduces the committed note byte for byte."""

from __future__ import annotations

import re

from jev_probe import note_all

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_.\-]*\d[\w.\-]*")  # H1, Q0_valid, jev-v1, CH-B1, p90
# Registered design parameters, not results: noise levels, the false-positive ceiling, the
# interval level, and the model's name.
DESIGN_LITERALS = ("Haiku 4.5", "95%", "30%", "10%", "0%", "1%")


def test_filled_note_has_no_unfilled_slot() -> None:
    filled = note_all.build()
    assert "{{" not in filled and "}}" not in filled


def test_regenerating_note_is_byte_identical() -> None:
    assert note_all.build().encode("utf-8") == note_all.NOTE_PATH.read_bytes()


def test_template_has_no_hand_typed_number() -> None:
    text = note_all.TEMPLATE_PATH.read_text(encoding="utf-8")
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = IDENTIFIER.sub("", text)
    for lit in DESIGN_LITERALS:
        text = text.replace(lit, "")
    assert re.findall(r"\d", text) == []


def test_note_style() -> None:
    text = note_all.TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "—" not in text
    assert "governs any model" not in text
    for sentence in (
        "Across two sensors, three noise levels and {{n_verdicts_total}} test verdicts, the admission policy "
        "never mapped a sensing error from deny to allow ({{unsafe_total}} of {{n_verdicts_total}}). "
        "Every verdict change was fail-closed.",
        "The results provide evidence that the SARC control boundary is not specific to generative LLMs: "
        "the same external-governance pattern applies to a typed probabilistic model such as Jev.",
        "Haiku's threshold τ_true = {{tau_true_llm}} was forced by the 1% false-positive ceiling on a "
        "compressed score distribution; 'Jev better' means Jev's scores separate better under that ceiling, "
        "not that Haiku cannot read a record.",
        "All corpora are constructed. No prevalence claim is made.",
        "Every registration from jev-v3 onward includes an arm health check with a hard stop before the test split.",
    ):
        assert sentence in text, sentence
    prose = [line for line in text.splitlines() if line.strip() and not line.startswith(("#", ">"))]
    assert prose[0].startswith("Across two sensors")  # the lead sentence is the note's first line of prose
    for us in ("analyze", "behavior", "labeled", "color", "center"):
        assert us not in text.lower(), us
