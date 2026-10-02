# paper-tex: the paper 6 LaTeX release kit

Everything here except this file, `template.tex`, the scripts and the filters is generated; nothing
generated is edited by hand. Ported with attribution from `sarc-authority-derivation` at its
`engines.lock` pin (`cfb321e`); see the licence file beside this one.

## Canonical toolchain (round-three finding R3-1)

| tool | version | role |
|---|---|---|
| Pandoc | 3.1.3 | `build_main_tex.py` renders the populated manuscript into `main.tex` through `template.tex` |
| Tectonic | 0.17.0 | builds `main.pdf` (gate G1), with `SOURCE_DATE_EPOCH=1786609963` and `TZ=UTC` |
| Tectonic bundle | `default_bundle_v33` | TeX formats, packages and fonts; cached by Tectonic, or fetched over the network on first use |
| poppler-utils | any | `pdfinfo`, `pdftotext` for the gates |

Under this toolchain `main.tex`, `main.pdf` and `arxiv.tar.gz` regenerate byte for byte. Pandoc
writers outside 3.1 produce a different `main.tex`; `python preflight.py --paper` refuses them, and
`make release-check` runs it first. `template.tex` defines `\pandocbounded` so that output from a
newer Pandoc still compiles, but such output is not the canonical one.

`make release-check` makes no inference call. It needs the Tectonic bundle either cached or
reachable over the network (R3-2).

## Files

| file | made by |
|---|---|
| `main.tex` | `build_main_tex.py` (Pandoc) from `paper/paper6-draft-v0.1-populated.md` |
| `main.pdf` | Tectonic, through `gates/run_gates.py` (G1 builds twice and requires identical bytes) |
| `fig1-pipeline.pdf` | copied from `paper/figs/` (drawn by `paper/figs/fig1_pipeline.py`) |
| `refs.bib` | `generate_refs_bib.py` from `../verified-citations.json` |
| `bib-audit.json` | `verify_citations.py` (needs network; not run by release-check) |
| `arxiv-abstract.txt`, `arxiv-metadata.txt` | `make_sidecars.py` from the manuscript front matter |
| `arxiv.tar.gz` | `make_arxiv_tarball.py` (deterministic) |
| `parity-report.json` | `gates/run_gates.py` (G1 to G9 and the four lints) |
