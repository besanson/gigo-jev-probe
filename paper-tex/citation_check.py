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
Ported with attribution from sarc-authority-derivation's citation_check.py at the engines.lock
pin (commit cfb321e), itself ported from sarc-suite-one-pass's citation_check.py (commit
782261e). Apache-2.0 (LICENSE-sarc-authority-derivation beside this file). Paper 6 changes:
this docstring; paths resolve from the repository root, so the script runs from any directory;
the default target is the live paper 6 draft, paper/paper6-draft-v0.1.md. The checking logic
is unchanged. Pandoc citation keys ([@key]) are checked separately by gate G8
(gates/run_gates.py), which requires every key to be a verified-citations.json id.

Citation verification gate.

Per the task spec: "a citation may enter the paper only after it is
verified by fetching its source page and recording url, title, first
author, year into verified-citations.json." verified-citations.json
holds exactly that record for each of this artifact's Phase R citations
(fetched via WebSearch/WebFetch, see each entry's verified_via field) --
this pipeline never fabricates a citation to fill a gap. A literature
claim this artifact cannot yet back with a verified source stays an
honest `[CITE: ...]` placeholder and is counted, not invented -- the
count is one of the numbers the human release checklist prints.

Every citation-shaped token (an arXiv ID or a DOI) appearing in a paper
draft must match an entry's arxiv_id/doi here. Whitelist entries that
have neither (some venues never had a DOI assigned) are instead checked
by exact url presence: the entry's own url must appear verbatim in the
paper text, so a citation without a DOI/arXiv id still gets an automated
presence check rather than only a one-time human verification during
research.

One DOI is allowed without a whitelist entry: the repository's own archive DOI, read from the
`doi:` field of CITATION.cff at the repository root (DECISIONS.md, D-E3). It names this
repository, not a cited work, so it has no bibliography entry.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
CITATIONS_PATH = str(ROOT / "verified-citations.json")
CITATION_CFF_PATH = str(ROOT / "CITATION.cff")
DEFAULT_TARGET = str(ROOT / "paper" / "paper6-draft-v0.1.md")

ARXIV_PATTERN = re.compile(r"arXiv[:\s]+(\d{4}\.\d{5})", re.IGNORECASE)
DOI_PATTERN = re.compile(r"\bdoi[:\s]+(10\.\d{4,9}/[^\s,)\]]+)", re.IGNORECASE)
# Raw citation URLs (e.g. a pre-DOI-era paper cited by url only): matches
# a bare http(s) link, trimming common trailing punctuation a sentence
# might leave attached (closing paren, period, comma).
URL_PATTERN = re.compile(r"https?://[^\s)\]]+")
CITE_PLACEHOLDER_PATTERN = re.compile(r"\[CITE[-:][^\]]*\]")


REQUIRED_FIELDS = ("url", "title", "first_author", "year")
SELF_DOI_PATTERN = re.compile(r"^doi:\s*[\"']?(10\.\d{4,9}/[^\s\"']+)", re.MULTILINE)


def self_archive_dois(cff_path: str = CITATION_CFF_PATH) -> set[str]:
    """The repository's own archive DOI from CITATION.cff (empty if absent or commented out)."""
    path = Path(cff_path)
    return set(SELF_DOI_PATTERN.findall(path.read_text())) if path.exists() else set()


def load_whitelist(path: str = CITATIONS_PATH) -> Dict[str, Any]:
    return json.loads(Path(path).read_text())


def verify_whitelist_schema(path: str = CITATIONS_PATH) -> Dict[str, Any]:
    """Every entry must carry what the task spec requires a verified
    citation to record: url, title, first_author, year -- not just the
    machine-matchable arxiv_id/doi token."""
    whitelist = load_whitelist(path)
    incomplete = []
    for citation in whitelist["citations"]:
        missing = [f for f in REQUIRED_FIELDS if f not in citation]
        if missing:
            incomplete.append({"id": citation.get("id"), "missing": missing})
    return {"total": len(whitelist["citations"]), "incomplete": incomplete, "clean": not incomplete}


def check(paper_path: str, whitelist_path: str = CITATIONS_PATH,
          cff_path: str = CITATION_CFF_PATH) -> Dict[str, Any]:
    text = Path(paper_path).read_text()
    whitelist = load_whitelist(whitelist_path)
    allowed_arxiv = {c["arxiv_id"] for c in whitelist["citations"] if "arxiv_id" in c}
    allowed_doi = {c["doi"] for c in whitelist["citations"] if "doi" in c} | self_archive_dois(cff_path)
    allowed_urls = {c["url"] for c in whitelist["citations"] if "url" in c}

    found_arxiv = set(ARXIV_PATTERN.findall(text))
    found_doi = {m.rstrip(".,;:") for m in DOI_PATTERN.findall(text)}
    found_urls = {m.rstrip(".,;") for m in URL_PATTERN.findall(text)}
    unverified_arxiv = sorted(found_arxiv - allowed_arxiv)
    unverified_doi = sorted(found_doi - allowed_doi)
    # A found url is verified if it exactly matches a whitelisted url, OR
    # is itself the doi.org/arxiv.org resolver form of an already-allowed
    # doi/arxiv_id (both forms of the same citation legitimately appear).
    unverified_urls = sorted(
        u for u in found_urls
        if u not in allowed_urls
        and not any(doi in u for doi in allowed_doi)
        and not any(aid in u for aid in allowed_arxiv)
    )
    placeholder_count = len(CITE_PLACEHOLDER_PATTERN.findall(text))

    return {
        "paper_path": paper_path,
        "found_arxiv_ids": sorted(found_arxiv),
        "found_dois": sorted(found_doi),
        "found_urls": sorted(found_urls),
        "unverified_arxiv_ids": unverified_arxiv,
        "unverified_dois": unverified_doi,
        "unverified_urls": unverified_urls,
        "cite_needed_placeholder_count": placeholder_count,
        "clean": not unverified_arxiv and not unverified_doi and not unverified_urls,
    }


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET
    result = check(target)
    print(json.dumps(result, indent=2))
    if not result["clean"]:
        raise SystemExit(1)
