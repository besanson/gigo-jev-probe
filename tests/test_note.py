"""The results note is filled from the slots only: no unfilled slot, no hand-typed number,
and regenerating it reproduces the committed note byte for byte."""

from __future__ import annotations

import re

from jev_probe import note

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_.\-]*\d[\w.\-]*")  # H1, Q0_valid, jev-v1, p90


def test_filled_note_has_no_unfilled_slot() -> None:
    filled = note.build()
    assert "{{" not in filled and "}}" not in filled


def test_regenerating_note_is_byte_identical() -> None:
    assert note.build().encode("utf-8") == note.NOTE_PATH.read_bytes()


def test_template_has_no_hand_typed_number() -> None:
    text = note.NOTE_TEMPLATE_PATH.read_text(encoding="utf-8")
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = IDENTIFIER.sub("", text)
    assert re.findall(r"\d", text) == []


def test_note_style() -> None:
    text = note.NOTE_TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "—" not in text
    assert "governs any model" not in text
    assert ("The results provide evidence that the SARC control boundary is not specific to "
            "generative LLMs: the same external-governance pattern applies to a typed "
            "probabilistic model such as Jev.") in text
