# Paper 6, round-one review (R1)

Reviewer: the author's adjudicating model session (Claude), reading `paper/paper6-draft-v0.1-populated.md` and `paper-tex/main.pdf` at commit `8c838c6` on 2026-10-02. Gates and lints were re-run on a second machine with latexmk as the compiler: all thirteen pass; the PDF differs byte-wise from the committed Tectonic build, as expected across compilers.

Findings only. Severity 1 blocks the release candidate; 2 must be fixed before round two; 3 is editorial. No severity-1 finding.

| # | sev | finding | section | fix |
|---|---|---|---|---|
| F1 | 2 | H1 has almost no power. The Clopper-Pearson floor puts every B+ at or above 0.0395; a cell would need about 28 flips in 700 to violate it. The text says "valid, not tight" but does not say that H1 could fail only under a gross violation. | Limitations, Results E1 | Add a slot-driven table of the minimum number of flips in 700 that would exceed B+ per E1 cell, and the sentence "H1 can fail only under a violation of that size." |
| F2 | 2 | Portability. `make release-check` compares the committed `paper-tex/fig1-pipeline.pdf` byte for byte, and `rsvg-convert` output depends on the installed librsvg, so the check fails on another machine. Tectonic and `lmodern.sty` are undeclared by preflight. This blocks independent reproduction (Phase F) the way BSD tar blocked paper 5's. | build tooling | Generate the figure PDF deterministically (matplotlib with fixed metadata and SOURCE_DATE_EPOCH) or exclude the derived PDF from the diff and check the SVG source only. Preflight reports a TeX engine, `lmodern.sty`, pandoc, pdftotext. README lists them. |
| F3 | 2 | Boolean slots rendered as "(yes)" in prose: "all on contradictory approval statement: yes", "attained: yes", "globally deny-ward: no". Reads as a leaked template. | Results (flips), Appendix A | Render booleans as words in the main text through populate.py; keep the raw form in Appendix A only. |
| F4 | 3 | The E1 column "no unsafe change" is ambiguous. The registration says the column reports whether S3's global condition held on the test split. | Results E1 | Rename to "S3 condition held" and say in one sentence what it reports. |
| F5 | 3 | "Paper 3", "paper 4", "paper 5" appear without citation after first mention. An arXiv reader has no series. | Introduction, Invariants, Related work | Cite each at first mention: paper 3 = SARC-DQ, arXiv 2607.26313; paper 4 = One Gate Is Not Enough, arXiv 2608.18360; paper 5 = Compiling Sufficient Governance Context, arXiv 2609.26016. |
| F6 | 3 | "This programme had recorded no deny-to-allow change before this paper." True only for sensing. | Results (flips), Abstract | "no deny-to-allow change from sensing". |
| F7 | 3 | For nested sensed-field sets S2 fixes the pick a priori, so H2 tests whether measured exposure follows the bound's ordering, not whether the rule works. The body says it once; the hypotheses section does not. | Results, Hypotheses | Add the sentence under the H2 rows, with the four b values as slots. |

What holds up and should not change: every number traces to a slot; the flips section traces 13 flips to 3 contradictory records and names the mechanism; the Haiku `not_recorded` threshold failure is reported and explained; the fence, claims table, non-claims and limitations are consistent with CLAIMS.md.
