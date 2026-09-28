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


def test_key_value_never_printed(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preflight, "check_pin", lambda: None)
    for env in ({"JEV_API_KEY": SENTINEL}, {"JEV_API_KEY": SENTINEL, "JEV_BASE_URL": "x"}):
        preflight.main(env)
        out = capsys.readouterr()
        assert SENTINEL not in out.out + out.err


def test_pin_mismatch_is_reported(tmp_path: Path) -> None:
    lock = tmp_path / "engines.lock"
    lock.write_text('[dqSarc]\nurl = "u"\npath = "missing"\ncommit = "abc"\n', encoding="utf-8")
    assert "not found" in (preflight.check_pin(lock) or "")
