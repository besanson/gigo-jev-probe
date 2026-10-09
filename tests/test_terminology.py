"""Paper 6 terminology lint: forbidden phrases are caught, and the paper 6 files are clean."""

from __future__ import annotations

from pathlib import Path

import pytest

from lint import terminology

import sensed_authority


@pytest.mark.parametrize("phrase", terminology.FORBIDDEN)
def test_each_forbidden_phrase_is_caught(phrase: str) -> None:
    assert terminology.hits(f"In this setting {phrase.upper()} here.") == [phrase]


def test_phrase_split_across_lines_is_caught() -> None:
    assert terminology.hits("the sensor\n  verdict") == ["sensor verdict"]


def test_clean_text_passes() -> None:
    assert terminology.hits("The sensor writes an observation; the deterministic contract decides.") == []


def test_lint_scans_the_paper_6_files() -> None:
    names = {str(p.relative_to(terminology.ROOT)) for p in terminology.files()}
    assert {"README.md", "NOVELTY.md", "CLAIMS.md", "DECISIONS.md", "FINAL-AUDIT.md",
            "prereg/p6-v1.md", "src/sensed_authority/__init__.py"} <= names


def test_paper_6_files_are_clean() -> None:
    assert terminology.main() == 0


def test_lint_reports_a_hit(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Here the model decides.\n", encoding="utf-8")
    assert terminology.main(tmp_path) == 1


def test_package_init_defines_only_a_version() -> None:
    import ast

    assert sensed_authority.__version__ == "0.0.0"
    tree = ast.parse(Path(sensed_authority.__file__).read_text(encoding="utf-8"))
    assigned = [t.id for node in tree.body if isinstance(node, ast.Assign) for t in node.targets]
    assert assigned == ["__version__"]
    assert not [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef))]


@pytest.mark.parametrize("text, hit", [
    ("The inferred value is admitted.", "inferred value"),
    ("This proves the bound.", "proves"),
    ("It guarantees nothing.", "guarantee"),
    ("We pick the smallest reduct.", "the smallest"),
    ("A pause — then more.", "—"),
    ("The behavior of the sensor.", "behavior"),
    ("We minimize the bound.", "minimize"),
])
def test_manuscript_rules(text: str, hit: str) -> None:
    assert hit in terminology.manuscript_hits(text)


def test_manuscript_rules_skip_code_and_the_quoted_non_claims() -> None:
    claims = (terminology.ROOT / "CLAIMS.md").read_text(encoding="utf-8")
    sentence = claims.rsplit("stated in the paper: ", 1)[1].strip()
    assert terminology.manuscript_hits(f'Non-claims: "{sentence}" and `minimize_cost()`.') == []
    assert "safe in general" in terminology.manuscript_hits("Sensing is safe in general.")


def test_the_manuscript_is_linted() -> None:
    names = {str(p.relative_to(terminology.ROOT)) for p in terminology.files()}
    assert terminology.MANUSCRIPT in names
