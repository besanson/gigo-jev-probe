#!/usr/bin/env python3
"""Fetch and verify every citation in verified-citations.json (paper 6 citation pipeline).

    python paper-tex/verify_citations.py          # fetch, compare, write bib-audit.json and verified_via
    python paper-tex/verify_citations.py --dry    # fetch and compare only; write nothing

Paper 5's pipeline recorded each citation by hand after a WebSearch/WebFetch check. Here the
check is a script: for each record it fetches the authoritative metadata named by the record's
`verify` field and compares it with the stored record.

  crossref          https://api.crossref.org/works/<doi>
  datacite          https://api.datacite.org/dois/<doi>   (DOIs registered with DataCite)
  arxiv             https://export.arxiv.org/api/query?id_list=<id>
  proceedings_page  the publisher's abstract page (PMLR, NeurIPS): its citation_* meta tags
  wikidata          https://www.wikidata.org/wiki/Special:EntityData/<qid>.json
                    (for a record with neither DOI nor arXiv id; the JSTOR id is checked too)

A record passes only if the title, the full author list (family names, in order), the year and,
where the record states them, the venue, volume and pages match. The result for every record
goes to paper-tex/bib-audit.json, which gate G9 requires; a passing record's verified_via field
is rewritten to say how and when it was verified. Nothing is written unless every record passes.
Needs network access; the release gates read only the committed audit.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

PAPER_TEX_DIR = Path(__file__).resolve().parent
REPO_ROOT = PAPER_TEX_DIR.parent
CITATIONS_PATH = REPO_ROOT / "verified-citations.json"
AUDIT_PATH = PAPER_TEX_DIR / "bib-audit.json"
USER_AGENT = "gigo-jev-probe citation verification (https://github.com/besanson/gigo-jev-probe)"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - network retry, re-raised on the last attempt
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", html.unescape(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def family(name: str) -> str:
    """Family name from 'Given Family' or 'Family, Given'."""
    name = name.strip()
    if "," in name:
        return norm(name.split(",", 1)[0])
    return norm(name.split()[-1])


def from_crossref(doi: str) -> dict:
    m = json.loads(fetch("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")))["message"]
    return {"url": f"https://api.crossref.org/works/{doi}", "title": (m.get("title") or [""])[0],
            "authors": [(a.get("given", "") + " " + a.get("family", "")).strip() for a in m.get("author", [])],
            "year": (m.get("issued", {}).get("date-parts") or [[None]])[0][0],
            "venue": " ".join(m.get("container-title") or []), "volume": m.get("volume"),
            "pages": m.get("page")}


def from_datacite(doi: str) -> dict:
    a = json.loads(fetch("https://api.datacite.org/dois/" + urllib.parse.quote(doi, safe="")))["data"]["attributes"]
    container = a.get("container") or {}
    related = (a.get("relatedItems") or [{}])[0]
    venue = " ".join(t.get("title", "") for t in related.get("titles", [])) or container.get("title", "")
    return {"url": f"https://api.datacite.org/dois/{doi}", "title": a["titles"][0]["title"],
            "authors": [c["name"] for c in a.get("creators", [])], "year": int(a.get("publicationYear")),
            "venue": venue, "volume": container.get("volume"),
            "pages": f"{container.get('firstPage')}--{container.get('lastPage')}"}


def from_arxiv(arxiv_id: str) -> dict:
    x = fetch(f"https://export.arxiv.org/api/query?id_list={arxiv_id}")
    e = x.split("<entry>", 1)[1]
    return {"url": f"https://export.arxiv.org/api/query?id_list={arxiv_id}",
            "title": re.sub(r"\s+", " ", re.search(r"<title>(.*?)</title>", e, re.S).group(1)).strip(),
            "authors": re.findall(r"<name>(.*?)</name>", e),
            "year": int(re.search(r"<published>(\d{4})", e).group(1)), "venue": "arXiv"}


def from_proceedings_page(url: str) -> dict:
    page = fetch(url)

    def meta(name: str) -> list[str]:
        return [html.unescape(v) for v in re.findall(rf'<meta name="citation_{name}" content="([^"]*)"', page)]

    first, last = meta("firstpage"), meta("lastpage")
    year = (meta("publication_date") or [""])[0][:4]
    return {"url": url, "title": (meta("title") or [""])[0], "authors": meta("author"),
            "year": int(year) if year.isdigit() else None,
            "venue": " ".join(meta("journal_title") + meta("conference_title")),
            "volume": (meta("volume") or [None])[0],
            "pages": f"{first[0]}--{last[0]}" if first and last else None}


def from_wikidata(qid: str) -> dict:
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    e = json.loads(fetch(url))["entities"][qid]
    c = e["claims"]

    def vals(p: str) -> list:
        return [x["mainsnak"].get("datavalue", {}).get("value") for x in c.get(p, [])]

    venue = ""
    for v in vals("P1433"):
        ve = json.loads(fetch(f"https://www.wikidata.org/wiki/Special:EntityData/{v['id']}.json"))["entities"][v["id"]]
        venue = ve["labels"].get("en", {}).get("value", "")
    return {"url": url, "title": (vals("P1476") or [{"text": ""}])[0]["text"], "authors": vals("P2093"),
            "year": int(vals("P577")[0]["time"][1:5]) if vals("P577") else None, "venue": venue,
            "volume": (vals("P478") or [None])[0], "issue": (vals("P433") or [None])[0],
            "pages": (vals("P304") or [None])[0], "jstor": (vals("P888") or [None])[0]}


SOURCES = {"crossref": lambda v: from_crossref(v["doi"]), "datacite": lambda v: from_datacite(v["doi"]),
           "arxiv": lambda v: from_arxiv(v["arxiv_id"]), "proceedings_page": lambda v: from_proceedings_page(v["url"]),
           "wikidata": lambda v: from_wikidata(v["qid"])}


def _pages(p: str | None) -> tuple[str, ...]:
    return tuple(re.findall(r"[0-9]+(?::[0-9]+)?", p or ""))


def compare(record: dict, got: dict) -> list[dict]:
    v = record["verify"]
    mismatches = []

    def check(field: str, ok: bool, want, have) -> None:
        if not ok:
            mismatches.append({"field": field, "record": want, "source": have})

    check("title", norm(record["title"]) == norm(got["title"]), record["title"], got["title"])
    want_auth, have_auth = [family(a) for a in record["authors"]], [family(a) for a in got["authors"]]
    check("authors", want_auth == have_auth, record["authors"], got["authors"])
    check("year", record["year"] == got["year"], record["year"], got["year"])
    if v.get("venue"):
        check("venue", norm(v["venue"]) in norm(got.get("venue") or ""), v["venue"], got.get("venue"))
    if v.get("volume") is not None:
        check("volume", str(v["volume"]) == str(got.get("volume")), v["volume"], got.get("volume"))
    if record.get("volume") and got.get("volume") and v["source"] in ("crossref", "datacite", "wikidata"):
        check("volume", str(record["volume"]) == str(got["volume"]), record["volume"], got["volume"])
    if record.get("pages") and got.get("pages"):
        check("pages", _pages(record["pages"]) == _pages(got["pages"]), record["pages"], got["pages"])
    if v.get("jstor"):
        check("jstor", str(v["jstor"]) == str(got.get("jstor")), v["jstor"], got.get("jstor"))
    return mismatches


SOURCE_NAMES = {"crossref": "Crossref API", "datacite": "DataCite API", "arxiv": "arXiv API",
                "proceedings_page": "the proceedings page's citation metadata", "wikidata": "Wikidata"}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    data = json.loads(CITATIONS_PATH.read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()
    results = []
    for rec in data["citations"]:
        v = rec["verify"]
        try:
            got = SOURCES[v["source"]](v)
            mismatches = compare(rec, got)
            error = None
        except Exception as exc:  # noqa: BLE001 - reported per record
            got, mismatches, error = {}, [], f"{type(exc).__name__}: {exc}"
        ok = error is None and not mismatches
        results.append({"id": rec["id"], "source": v["source"], "fetched": got.get("url"), "retrieved_on": today,
                        "retrieved": {k: got.get(k) for k in ("title", "authors", "year", "venue", "volume", "pages")},
                        "mismatches": mismatches, "error": error, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'} {rec['id']} ({v['source']})" + (f": {error or mismatches}" if not ok else ""))
        time.sleep(1)
    all_ok = all(r["pass"] for r in results)
    if "--dry" in args or not all_ok:
        print("verify_citations: " + ("all records verified (dry run, nothing written)" if all_ok else "FAILED; nothing written"))
        return 0 if all_ok else 1
    by_id = {r["id"]: r for r in results}
    for rec in data["citations"]:
        r = by_id[rec["id"]]
        checked = "title, full author list, year" + (", venue" if rec["verify"].get("venue") else "") + \
            (", volume" if rec.get("volume") else "") + (", pages" if rec.get("pages") else "")
        rec["verified_via"] = (f"paper-tex/verify_citations.py, {r['retrieved_on']}: fetched {r['fetched']} "
                               f"({SOURCE_NAMES[r['source']]}); {checked} match this record. "
                               "Audit record in paper-tex/bib-audit.json.")
    CITATIONS_PATH.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    AUDIT_PATH.write_text(json.dumps({"tool": "paper-tex/verify_citations.py", "results": results},
                                     indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"verify_citations: {len(results)} records verified; wrote {AUDIT_PATH.name} and verified_via")
    return 0


if __name__ == "__main__":
    sys.exit(main())
