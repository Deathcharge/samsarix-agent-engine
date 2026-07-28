from __future__ import annotations

import io
import json

import pytest

from helix_llm_agent_engine import ProviderError, __version__, cli


def test_cli_runs_offline_without_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "hello"]) == 0
    assert capsys.readouterr().out == "Echo: hello\n"


def test_cli_json_output_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "hello", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["content"] == "Echo: hello"
    assert result["provider"] == "echo"
    assert result["metrics"]["requests"] == 1


def test_cli_text_output_neutralizes_terminal_controls(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["run", "unsafe\x1b[31mtext"]) == 0
    assert capsys.readouterr().out == "Echo: unsafe�[31mtext\n"


def test_cli_reads_bounded_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stdin = io.StringIO("from stdin")
    monkeypatch.setattr(cli.sys, "stdin", stdin)
    assert cli.main(["run"]) == 0
    assert capsys.readouterr().out == "Echo: from stdin\n"


def test_cli_maps_invalid_stdin_limit_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("input"))
    assert cli.main(["run", "--max-input-chars", "-1"]) == 2
    assert "max_input_chars" in capsys.readouterr().err


def test_cli_requires_openai_model(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "hello", "--provider", "openai"]) == 2
    assert "--model is required" in capsys.readouterr().err


def test_cli_requires_key_for_openai_host(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli.main(["run", "hello", "--provider", "openai", "--model", "test"]) == 2
    assert "OPENAI_API_KEY is required" in capsys.readouterr().err


def test_cli_maps_provider_error_to_exit_three(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fail(_: object) -> dict[str, object]:
        raise ProviderError("unavailable")

    monkeypatch.setattr(cli, "_run", fail)
    assert cli.main(["run", "hello"]) == 3
    assert capsys.readouterr().err == "provider error: unavailable\n"


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as captured:
        cli.main(["--version"])
    assert captured.value.code == 0
    assert capsys.readouterr().out == f"helix-agent {__version__}\n"
