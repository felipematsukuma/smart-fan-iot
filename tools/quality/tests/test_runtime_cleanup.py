"""A failed QA startup still stops services and never prints its credentials."""

import importlib.util
import secrets
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_startup_failure_is_redacted_and_stops_services(tmp_path, monkeypatch, capsys):
    directory = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "qa_runtime_probe", directory / "runtime.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    unit = tmp_path / "evidence/coverage/python-unit/.coverage"
    unit.parent.mkdir(parents=True)
    unit.touch()
    secret_folder = tmp_path / "secrets"
    secret_folder.mkdir()
    credential = secrets.token_urlsafe(32)
    (secret_folder / "postgres_bootstrap").write_text(credential, encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "prepare_coverage_directory", lambda _: None)
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        if "up" in args:
            raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(module, "run", run)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="bootstrap failed: " + credential, stderr=""
        ),
    )
    with pytest.raises(subprocess.CalledProcessError):
        module.main()
    output = capsys.readouterr().out
    assert credential not in output
    assert "[REDACTED]" in output
    assert calls[-1] == (*module.QA, "stop")
