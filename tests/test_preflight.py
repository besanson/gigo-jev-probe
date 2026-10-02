import subprocess
from pathlib import Path

import pytest

import preflight

SENTINEL = "sk-SENTINEL-must-never-appear-0123456789"


def test_missing_key_exits_with_message(capsys: pytest.CaptureFixture[str]) -> None:
    assert preflight.main({"JEV_BASE_URL": "https://api.example.invalid"}) == 1
    err = capsys.readouterr().err
    assert "JEV_API_KEY" in err


def test_blank_key_counts_as_missing() -> None:
    assert preflight.check_env({"JEV_API_KEY": "   ", "JEV_BASE_URL": "x"}) == ["JEV_API_KEY"]


def test_sdk_key_alias_is_accepted() -> None:
    assert preflight.check_env({"TYPESAFE_API_KEY": "k", "JEV_BASE_URL": "x"}) == []


@pytest.mark.parametrize(
    "base",
    ["https://api.typesafe.ai", "https://api.typesafe.ai/", "https://api.typesafe.ai/v1"],
)
def test_base_url_resolves_to_documented_endpoint(base: str) -> None:
    assert preflight.resolve_endpoint(base) == preflight.SYSTEM_ONE_ENDPOINT


def test_wrong_base_url_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    env = {"JEV_API_KEY": SENTINEL, "JEV_BASE_URL": "https://api.example.invalid"}
    assert preflight.main(env) == 1
    assert "expected" in capsys.readouterr().err


def test_key_value_never_printed(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preflight, "check_pin", lambda: None)
    base = "https://api.typesafe.ai"
    for env in (
        {"JEV_API_KEY": SENTINEL},
        {"JEV_API_KEY": SENTINEL, "JEV_BASE_URL": "x"},
        {"JEV_API_KEY": SENTINEL, "JEV_BASE_URL": base},
        {"TYPESAFE_API_KEY": SENTINEL, "JEV_BASE_URL": base},
    ):
        preflight.main(env)
        out = capsys.readouterr()
        assert SENTINEL not in out.out + out.err


def test_pin_mismatch_is_reported(tmp_path: Path) -> None:
    lock = tmp_path / "engines.lock"
    lock.write_text('[dqSarc]\nurl = "u"\npath = "missing"\ncommit = "abc"\n', encoding="utf-8")
    assert "not found" in (preflight.check_pin(lock) or "")


def test_second_sibling_is_checked(tmp_path: Path) -> None:
    head = subprocess.run(["git", "-C", str(preflight.ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    lock = tmp_path / "engines.lock"
    lock.write_text(
        f'[dqSarc]\nurl = "u"\npath = "{preflight.ROOT}"\ncommit = "{head}"\n'
        '[sarc-authority-derivation]\nurl = "u2"\npath = "missing"\ncommit = "abc"\n', encoding="utf-8")
    msg = preflight.check_pin(lock) or ""
    assert "sarc-authority-derivation" in msg and "not found" in msg


def test_real_pins_hold() -> None:
    assert preflight.check_pin() is None


def test_paper_report_needs_an_engine_pandoc_and_pdftotext() -> None:
    present = {"tectonic": "/t", "latexmk": None, "pandoc": "/p", "pdftotext": "/x", "pdfinfo": "/i",
               "lmodern.sty": None}
    assert preflight.paper_report(present)[1] is True
    for name in ("tectonic", "pandoc", "pdftotext"):
        assert preflight.paper_report({**present, name: None})[1] is False
    latexmk_only = {**present, "tectonic": None, "latexmk": "/l"}
    assert preflight.paper_report(latexmk_only)[1] is False
    assert preflight.paper_report({**latexmk_only, "lmodern.sty": "/tex/lmodern.sty"})[1] is True


def test_paper_tools_reports_kpsewhich_lookup() -> None:
    which = {"kpsewhich": "/k", "tectonic": "/t"}.get

    class R:
        stdout = "/texlive/lmodern.sty\n"

    tools = preflight.paper_tools(which=which, run=lambda *a, **k: R())
    assert tools["lmodern.sty"] == "/texlive/lmodern.sty" and tools["pandoc"] is None


def test_pandoc_must_be_3_1() -> None:  # R3-1
    assert preflight.pandoc_matches("3.1.3") and preflight.pandoc_matches("3.1.11")
    for bad in ("3.7.0.2", "2.19.2", "3.2", None):
        assert not preflight.pandoc_matches(bad)


def test_tool_version_parses_the_first_dotted_number() -> None:  # R3-1
    class R:
        stdout = "pandoc 3.1.3\nFeatures: +server\n"

    assert preflight.tool_version(["pandoc", "--version"], run=lambda *a, **k: R()) == "3.1.3"

    def missing(*a, **k):
        raise FileNotFoundError

    assert preflight.tool_version(["nope"], run=missing) is None
