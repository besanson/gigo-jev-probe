"""§4: the nine registered questions, verbatim, as typed Noul questions, in order."""

from __future__ import annotations

from typing import Any

QUESTIONS: tuple[tuple[str, str], ...] = (
    (
        "Q0_valid",
        "Is this evidence free of data-quality defects, so that it is valid to act on as-is?",
    ),
    (
        "Q_stale_master_data",
        "Is the price value stale, that is, no longer current as of the day it was retrieved?",
    ),
    (
        "Q_superseded_golden_record",
        "Is the evidence relying on a record version that has been superseded by a newer "
        "version of the same record?",
    ),
    (
        "Q_silent_unit_change",
        "Is the price expressed in a different unit of measure than intended, without the "
        "change being declared?",
    ),
    (
        "Q_duplicate_vendor_conflicting_terms",
        "Are there duplicate vendor records for the same item carrying conflicting terms?",
    ),
    (
        "Q_cross_source_contradiction",
        "Do two or more sources disagree on the same value by more than a small tolerance?",
    ),
    (
        "Q_schema_drift",
        "Has a field been renamed or changed type relative to the expected record schema?",
    ),
    ("Q_missing_mandatory_field", "Is a mandatory field missing from the evidence?"),
    ("Q_plausible_outlier", "Is a value wrong even though it lies within a plausible range?"),
)

QUESTION_IDS: tuple[str, ...] = tuple(qid for qid, _ in QUESTIONS)
CLASS_QUESTIONS: tuple[str, ...] = QUESTION_IDS[1:]


def question_for_class(cls: str) -> str:
    return f"Q_{cls}"


def class_of_question(qid: str) -> str | None:
    return None if qid == "Q0_valid" else qid[len("Q_") :]


def noul_questions() -> dict[str, Any]:
    """The `questions` map for System One: Noul objects keyed by id, no `criteria`."""
    from typesafe_sdk import Noul

    return {qid: Noul(instructions=text) for qid, text in QUESTIONS}


def questions_wire() -> dict[str, dict[str, str]]:
    """The exact wire form of the questions map (what the SDK serialises)."""
    return {qid: {"type": "noul", "instructions": text} for qid, text in QUESTIONS}
