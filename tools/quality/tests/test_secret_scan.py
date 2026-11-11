"""A safe working tree must not hide a different credential staged for commit."""

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path


def test_placeholder_exception_checks_index_not_working_tree(tmp_path, monkeypatch):
    directory = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "quality_secret_scan", directory / "secret_scan.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    target = tmp_path / "web-smart-fan-iot/.env.example"
    target.parent.mkdir()
    reviewed = "# reviewed example only\n"
    target.write_text("# different staged content\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    target.write_text(reviewed, encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        module, "PLACEHOLDER_SHA256", hashlib.sha256(reviewed.encode()).hexdigest()
    )
    finding = {
        "File": "web-smart-fan-iot/.env.example",
        "RuleID": "smartfan-credential-assignment",
    }
    assert module.placeholder(finding, "tree")
    assert not module.placeholder(finding, "staged")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    assert module.placeholder(finding, "staged")
    assert not module.placeholder({**finding, "RuleID": "other-rule"}, "staged")
