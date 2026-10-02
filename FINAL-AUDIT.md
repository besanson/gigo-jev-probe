# Final audit (paper 6)

Every item must be met, with evidence, before release. Status at the v1.0 release candidate
(manuscript v0.1.2 plus the round-three toolchain declaration): every item met except the
external human reproduction, which is pending.

| # | item | status | evidence |
|---|---|---|---|
| 1 | Invention-log entry made before paper 6 material is public (brief §8). | met | On the author's attestation; the invention log is kept outside this repository and was not inspected by the session that wrote this table. |
| 2 | External novelty review of `NOVELTY.md` and `prereg/p6-v1.md` committed under `review-secondary/` and adjudicated. | met | `review-secondary/p6-fence-review-2026-10-01/` (review and attestation); adjudicated by re-registering as `prereg/p6-v1.1.md`, findings marked `[F1]` to `[F13]`. |
| 3 | `prereg-p6-v1` tagged by the author before any paper 6 experiment code or model call. | met | Tag `prereg-p6-v1` on `ddcddf4` (2026-09-30 21:10 UTC) precedes the first paper 6 code commit `93737db` and the first p6 cache commit `881fbb2`; the binding registration is `prereg-p6-v1.1` on `2fac5a4`. |
| 4 | Propositions S1, S2, S3 and N6: finite checkers committed, each statement tagged `machine-checked`, `checked-scope-only` or `pending-human-review`. | met | `checkers/`, `out/p6/checkers/*.json` (all hold; B12 includes the empty contract after round-two F12), `proof_status.json`, `python -m checkers.proof_status_lint` green. |
| 5 | E1 to E5 run in registered order, each with a validation cache, frozen thresholds committed before its test split, and a test cache. | met | E1: `881fbb2` (validation, thresholds) then `7d002a7` (test); E2: `29d5f2b` then `beb03d5`. E3 to E5 make no call and are computed from the E1 and E2 caches by `experiments/analysis_p6.py`. |
| 6 | Arm health rule enforced before every test split; any `ARM_INVALID` stop recorded in the run manifest. | met | `responses/manifest-p6-E1.json`, `responses/manifest-p6-E2.json`: smoke and validation checks with 0 invalid replies per sensor; no `ARM_INVALID` stop occurred. |
| 7 | Total spend within the USD 60 cap, from the committed caches. | met | USD 8.26 across E1 and E2 (`results/p6.slots.json`: `E1.spend_usd`, `E2.spend_usd`). |
| 8 | Every number in the results and the paper is a slot filled from the caches; regeneration is byte-identical. | met | `make release-check` (analysis, flips, populated manuscript, figure, sidecars, `main.tex`, `main.pdf`, `arxiv.tar.gz` all regenerate byte for byte under the canonical toolchain); typed-numerals lint and gate G3; independently recomputed in `review-secondary/p6-replication-r3/` (52 table rows, no difference). |
| 9 | Every departure from the registration logged in `prereg/DEVIATIONS.md` before the affected data are analysed. | met | `prereg/DEVIATIONS.md`: "p6 (v1.1): no deviations". Post hoc material (round-two F4 and F7) is labelled descriptive or post hoc in the results and the paper, not registered. |
| 10 | Terminology lint green on every paper 6 file. | met | `python -m lint.terminology` (gate row L_terminology). |
| 11 | Frozen Jev probe paths unchanged since `jev-probes-final`. | met | `git diff jev-probes-final HEAD -- src/jev_probe results/jev-* responses/jev-v*.jsonl docs/jev-note* prereg/jev-*` is empty. |
| 12 | Independent human reproduction of at least E1 or E2 from a fresh environment, filed as an issue. | **external reproduction: pending** | Not yet filed. The round-three replication (`review-secondary/p6-replication-r3/`) is a mechanical replication by Perplexity Computer, not the independent human reproduction this item requires. |
