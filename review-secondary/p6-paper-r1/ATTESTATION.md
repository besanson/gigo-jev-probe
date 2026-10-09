# Attestation: round-one review (R1) of the paper 6 manuscript, 2026-10-02

| field | value |
|---|---|
| file | `review-r1.md` (this directory) |
| SHA-256 | `c172813a1a5c7c750f3acbb70ea8e5b922e07d75a6a564527918e0539e93aa49` |
| reviewer | the author's adjudicating model session (Claude), as the file itself states. It is a separate session from the Claude Code session that committed it. |
| date of review | 2026-10-02 |
| subject | `paper/paper6-draft-v0.1-populated.md` and `paper-tex/main.pdf` at commit `8c838c6` |
| committed by | the author's Claude Code session, on the author's instruction |

**Not edited.** `review-r1.md` is committed byte for byte as supplied by the author; its SHA-256
is given above. Nothing in it was corrected, reformatted or trimmed.

**Not applied.** The review itself changes no file. Its seven findings (F1 to F7; none of
severity 1) were reimplemented through the pipeline in commit `7530e13` ("paper 6 v0.1.1:
round-one findings"), editing the manuscript template, `paper/populate.py`, the figure script,
the `paper-tex/` tooling, `preflight.py` and the README, with every number filled from slots.

**Order of commits.** The review file reached the committing session only after `7530e13` had
been made and pushed: the author's instruction listed F1 to F7, and the attachment did not
arrive with it. The findings were therefore applied from the author's instruction, and this file
is committed afterwards. The instruction and the review agree finding by finding. The review
also states the series numbering used for F5 (paper 3 = SARC-DQ, arXiv 2607.26313; paper 4 =
One Gate Is Not Enough, arXiv 2608.18360), which `7530e13` had inferred and which matches.
