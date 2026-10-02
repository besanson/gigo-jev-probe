# Attestation: round-three mechanical replication (R3) of paper 6

| field | value |
|---|---|
| files | `findings.md`, `independent_recompute.py`, `independent-results.json`, `SHA256SUMS.txt` (this directory) |
| reviewer | Perplexity Computer |
| subject | a fresh clone of `besanson/gigo-jev-probe` at commit `8d73b6b` (`8d73b6bad6a9e4f7c5ee19e1b716d51182b05d3c`), with both siblings at their `engines.lock` pins |
| conditions, as the reviewer reports them | no repository source file edited; no API key supplied and no model call made; the repository's Python processes ran under a network guard that blocks socket connections (Tectonic, a native binary, could fetch TeX resources) |
| pack | `p6-review-r3-8d73b6b.zip`, SHA-256 `689ad22eed01b08e01968b3318da6c6f97d8c0cb3ab7b849f4560f5b330ac6dd`, as supplied by the author |
| committed by | the author's Claude Code session, on the author's instruction |

**File hashes.** As listed in `SHA256SUMS.txt` (itself SHA-256
`5ee4ce203cd51c9689625cf3be9d80b3813e50667862f71e8e0b9d4cafddb9ae`), and checked with
`sha256sum -c SHA256SUMS.txt` before committing:

| file | SHA-256 |
|---|---|
| `findings.md` | `6cbc2b0a8bfc015e271c3c10a0a144fe209df6d3d64614466a00ba5ec011a06c` |
| `independent-results.json` | `dedcd3eadaec2016d4afcf17057b6274afaff30338f05b2fbc864bcb36a42c12` |
| `independent_recompute.py` | `ce746a96eded4d2f5862430b6cc5f982de93895843f2de04cbbd8c89c59435d1` |

**Not edited.** The four files are extracted from the pack byte for byte. Nothing in them was
corrected, reformatted or trimmed.

**Not applied.** This commit changes no other file. The reviewer's three toolchain findings
(Pandoc version, Tectonic bundle cache, bootstrap entry point) are addressed in a later commit,
tagged R3-1 to R3-3. `independent_recompute.py` is committed as evidence; it is not run by any
make target and imports no package of this repository.
