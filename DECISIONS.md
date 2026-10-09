# Decisions (paper 6)

## ADR-000: paper 6 lives in this repository; the Jev results are frozen at `jev-probes-final`

- **Status:** accepted, 2026-09-30.
- **Context.** Paper 6 (*Probabilistic Sensing, Deterministic Authority*) grows out of the
  jev-v1, jev-v2 and jev-v3 probes in this repository. The brief names a separate repository
  (`sarc-sensed-authority`) as a working name.
- **Decision.** Paper 6 is developed in this repository (`besanson/gigo-jev-probe`). The Jev
  probe results that paper 6 quotes (experiment E0) are frozen at the tag `jev-probes-final`
  (commit `e1fc75b`), recorded as the `[self]` entry in `engines.lock`. Paper 6 cites them
  through that tag only.
- **Frozen paths.** `src/jev_probe/`, `responses/`, `results/`, `docs/jev-note.md` and
  `prereg/jev-v*.md` are not modified by paper 6 work. Paper 6 code lives in
  `src/sensed_authority/`; its registration is `prereg/p6-v1.md`.
- **Consequences.** One repository carries both the frozen probe record and the paper 6
  pipeline. Any later change to a frozen path is a deviation logged in
  `prereg/DEVIATIONS.md`, and the paper keeps quoting the tagged commit.

## D-E3: the paper 6 release tag is v1.0.1; the concept DOI is cited

- **Status:** accepted, 2026-10-07.
- **Decision.** Tag v1.0 was created on e1fc75b (main) in error and does not contain paper 6. It
  is left in place. The paper 6 release tag is v1.0.1. Zenodo record 23224017 (version 1 of
  concept record 23224016) archives e1fc75b and is marked as created in error. The paper and
  CITATION.cff cite the concept DOI 10.5281/zenodo.23224016, which resolves to the latest
  version.
- **Addendum.** Tag v1.0 at e1fc75b coincides with jev-probes-final, the E0 source. Release
  v1.0.1 archived as Zenodo version 2, record 23224577. arXiv 2610.10978, primary cs.SE,
  cross-list cs.AI.
