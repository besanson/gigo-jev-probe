#!/usr/bin/env python3
# Copyright 2026 SARC Suite Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Ported with attribution from sarc-authority-derivation's paper-tex/generate_refs_bib.py at the
engines.lock pin (commit cfb321e), itself ported from sarc-suite-one-pass's
paper-tex/generate_refs_bib.py (commit 782261e). Apache-2.0; the sibling's licence is copied
beside this file as LICENSE-sarc-authority-derivation. Paper 6 changes: this docstring, and
_BIB_ESCAPES gains the accented Latin letters paper 6's reference list needs (same reasoning as
the sibling's own ł/ń entries: classic accent commands render under any LaTeX engine and font).
CITATIONS_PATH is unchanged in form: ../verified-citations.json, this repository's own file.

Non-negotiable (same as the sibling's own arXiv LaTeX conversion task):
"Every citation in refs.bib is generated from verified-citations.json,
nothing else. No new references. If a reference lacks a BibTeX-required
field, derive it only from the verified record's stored fields."

This script is that generator: it reads exactly verified-citations.json
(../verified-citations.json relative to this file) and writes one BibTeX
entry per citation record. Every BibTeX field below maps 1:1 to a
verified-citations.json key:

  id           -> citation key (BibTeX entry key)
  entry_type   -> @article / @inproceedings / @incollection / @misc
  authors      -> author (full " and "-joined list; falls back to
                  first_author only for a record with no authors array)
  title        -> title
  year         -> year
  journal      -> journal      (article only, if present)
  booktitle    -> booktitle    (inproceedings/incollection only, if present)
  volume       -> volume       (only if present)
  number       -> number       (only if present)
  pages        -> pages        (only if present)
  publisher    -> publisher    (only if present)
  doi          -> doi          (only if present in the record)
  arxiv_id     -> eprint + archivePrefix={arXiv}  (only if present)
  url          -> url
  verified_via -> note (audit trail: how/when this repo verified it)

Deterministic and idempotent: re-running with an unchanged
verified-citations.json produces a byte-identical refs.bib. Run this
script directly, or via `make -C paper-tex/.. arxiv` which regenerates
refs.bib on every build so it can never drift from verified-citations.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CITATIONS_PATH = SCRIPT_DIR.parent / "verified-citations.json"
OUT_PATH = SCRIPT_DIR / "refs.bib"

_BIB_ESCAPES = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    # Classic LaTeX accent commands for characters outside the default
    # Latin Modern / T1 font's directly-encoded glyph set (verified by an
    # actual Tectonic build: "ec-lmr10" cannot render raw U+0142/U+0144
    # even under inputenc utf8) -- render correctly under the standard
    # pdfTeX/T1 toolchain with no special font or engine needed, unlike
    # passing the raw Unicode character through.
    "ł": r"{\l}",   # ł (Zdzisław Pawlak)
    "Ł": r"{\L}",   # Ł
    "ń": r"{\'n}",  # ń (Słowiński, a cited venue editor)
    "Ń": r"{\'N}",  # Ń
    # Paper 6 additions (author names in verified-citations.json).
    "é": r"{\'e}",
    "è": r"{\`e}",
    "á": r"{\'a}",
    "í": r"{\'i}",
    "ó": r"{\'o}",
    "ú": r"{\'u}",
    "ñ": r"{\~n}",
    "ö": r'{\"o}',
    "ü": r'{\"u}',
    "ä": r'{\"a}',
}

_ENTRY_TYPE_TO_BIBTEX = {
    "article": "article",
    "inproceedings": "inproceedings",
    "incollection": "incollection",
    "misc": "misc",
}

# entry_type -> which stored field is this type's venue field, if any.
_VENUE_FIELD_BY_TYPE = {
    "article": "journal",
    "inproceedings": "booktitle",
    "incollection": "booktitle",
}


def _escape(value: str) -> str:
    return "".join(_BIB_ESCAPES.get(ch, ch) for ch in value)


# A bare URL embedded in a long prose note (verified_via's own citation-
# audit-trail text routinely quotes one) has no natural line-break point
# for LaTeX's own text line-breaker -- confirmed directly via a Tectonic
# build: an un-wrapped URL produced an 81.9pt overfull \hbox with no
# hyphenation setting able to fix it, since it is one unbreakable "word".
# \url{} (loaded transitively via hyperref) breaks at /, ., _, and other
# URL-shaped punctuation instead. \url{}'s own argument is read mostly
# verbatim (a special catcode regime, not the normal one _escape's
# backslash-escaping targets), so a URL substring is spliced in raw,
# never passed through _escape, and the surrounding prose is escaped as
# usual on either side of it.
_URL_PATTERN = re.compile(r"https?://\S+")

# A bare sha256 (or similarly long) hex digest -- verified_via routinely
# records one as part of a download-integrity note -- is the same
# no-break-point problem as a URL, confirmed directly: a 64-character
# hex run produced its own separate 150.5pt overfull \hbox, distinct
# from the URL case above (\url{}'s own break points are /, ., _, and
# similar punctuation a pure hex run never contains, so wrapping it in
# \url{} would not have helped). \allowbreak (plain TeX/LaTeX kernel, no
# extra package) inserted periodically gives the line breaker a point to
# use without printing a visible hyphen, appropriate for an identifier
# rather than a hyphenated word.
_HEX_RUN_PATTERN = re.compile(r"\b[0-9a-fA-F]{16,}\b")


def _break_long_hex_runs(value: str) -> str:
    def _insert_breaks(m: re.Match) -> str:
        s = m.group(0)
        return "\\allowbreak ".join(s[i:i + 8] for i in range(0, len(s), 8))

    return _HEX_RUN_PATTERN.sub(_insert_breaks, value)


def _escape_with_url_breaks(value: str) -> str:
    parts = []
    pos = 0
    for m in _URL_PATTERN.finditer(value):
        parts.append(_escape(_break_long_hex_runs(value[pos:m.start()])))
        url = m.group(0).rstrip(").,;'\"")
        trailing = m.group(0)[len(url):]
        parts.append(f"\\url{{{url}}}")
        parts.append(_escape(trailing))
        pos = m.end()
    parts.append(_escape(_break_long_hex_runs(value[pos:])))
    return "".join(parts)


def _author_field(citation: dict) -> str:
    authors = citation.get("authors")
    if authors:
        return " and ".join(_escape(a) for a in authors)
    return _escape(citation["first_author"])


def _entry(citation: dict) -> str:
    key = citation["id"]
    bib_type = _ENTRY_TYPE_TO_BIBTEX.get(citation.get("entry_type"), "misc")
    lines = [f"@{bib_type}{{{key},"]
    lines.append(f"  author = {{{_author_field(citation)}}},")
    lines.append(f"  title = {{{{{_escape(citation['title'])}}}}},")
    lines.append(f"  year = {{{citation['year']}}},")
    venue_field = _VENUE_FIELD_BY_TYPE.get(citation.get("entry_type"))
    if venue_field and venue_field in citation:
        lines.append(f"  {venue_field} = {{{_escape(citation[venue_field])}}},")
    for field in ("volume", "number", "pages", "publisher"):
        if field in citation:
            lines.append(f"  {field} = {{{_escape(str(citation[field]))}}},")
    if "doi" in citation:
        lines.append(f"  doi = {{{citation['doi']}}},")
    if "arxiv_id" in citation:
        lines.append(f"  eprint = {{{citation['arxiv_id']}}},")
        lines.append("  archivePrefix = {arXiv},")
    lines.append(f"  url = {{{citation['url']}}},")
    lines.append(f"  note = {{{_escape_with_url_breaks(citation['verified_via'])}}},")
    lines[-1] = lines[-1].rstrip(",")  # no trailing comma on the last field
    lines.append("}")
    return "\n".join(lines)


def generate() -> str:
    data = json.loads(CITATIONS_PATH.read_text())
    citations = data["citations"]
    header = (
        "% Generated by paper-tex/generate_refs_bib.py from verified-citations.json.\n"
        "% Do not hand-edit -- every field is derived from that file's stored\n"
        "% records alone (arXiv LaTeX conversion task, non-negotiable #2).\n"
        f"% {len(citations)} entries.\n\n"
    )
    return header + "\n\n".join(_entry(c) for c in citations) + "\n"


if __name__ == "__main__":
    data = json.loads(CITATIONS_PATH.read_text())
    text = generate()
    OUT_PATH.write_text(text)
    print(f"wrote {OUT_PATH} ({len(data['citations'])} entries)")
