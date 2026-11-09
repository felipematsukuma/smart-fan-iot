import base64
import hashlib
import json
import re

import pytest

from infra.prepare import EVENT_KEYS, prepare, rabbit_password_hash


def test_repeat_bootstrap_preserves_credentials_and_never_outputs_them(
    tmp_path, capsys
):
    summary = prepare(tmp_path)
    before = {
        p.name: p.read_bytes()
        for p in tmp_path.iterdir()
        if not p.name.endswith((".json", "passwords"))
    }
    second = prepare(tmp_path)
    assert summary["created_credentials"] > 0
    assert second["created_credentials"] == 0
    assert all(
        (tmp_path / name).read_bytes() == value for name, value in before.items()
    )
    assert len(set(before.values())) == len(before)
    assert not capsys.readouterr().out


def test_no_guest_and_queues_are_quorum_with_service_boundaries(tmp_path):
    prepare(tmp_path)
    data = json.loads((tmp_path / "rabbitmq-definitions.json").read_text())
    assert "guest" not in {u["name"] for u in data["users"]}
    assert len(data["queues"]) == 8
    assert all(q["arguments"]["x-queue-type"] == "quorum" for q in data["queues"])
    assert all(
        p["configure"] == "^$" for p in data["permissions"] if p["user"] != "bootstrap"
    )
    for role, key in [
        ("api", "command.ac_01"),
        ("writer", "persisted.quarto.hvac.ac_01"),
    ]:
        assert re.fullmatch(EVENT_KEYS[role], key)
    assert not re.fullmatch(EVENT_KEYS["writer"], "command.ac_01")
    assert not re.fullmatch(EVENT_KEYS["gateway"], "telemetry.quarto.hvac.ac_01.extra")
    assert not re.fullmatch(EVENT_KEYS["api"], "command.ac_01.extra")


def test_password_hash_matches_rabbit_algorithm():
    password = "synthetic-test-password-only"
    decoded = base64.b64decode(rabbit_password_hash(password))
    assert decoded[4:] == hashlib.sha256(decoded[:4] + password.encode()).digest()


def test_invalid_existing_credential_is_not_replaced(tmp_path):
    (tmp_path / "rabbit_gateway").write_text("bad\n")
    with pytest.raises(ValueError, match="Invalid local credential"):
        prepare(tmp_path)
    assert (tmp_path / "rabbit_gateway").read_text() == "bad\n"
