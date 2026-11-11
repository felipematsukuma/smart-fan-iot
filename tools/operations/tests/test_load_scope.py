import pytest

from tools.operations import load


def test_load_refuses_original_project_before_any_docker_operation(monkeypatch):
    monkeypatch.setattr(
        load, "containers", lambda: pytest.fail("Original project must not be touched")
    )
    with pytest.raises(ValueError, match="restored test project"):
        load.scoped({"name": "smartfan-aiot"})


def test_load_refuses_two_active_full_stacks_on_the_same_machine(monkeypatch):
    monkeypatch.setattr(
        load, "containers", lambda: {"api": {"State": {"Running": True}}}
    )
    with pytest.raises(ValueError, match="Stop the original"):
        load.scoped({"name": "smartfan-restore-" + "a" * 12})


def test_latency_uses_nearest_rank_and_never_fabricates_empty_measurement():
    assert load.percentile(list(range(1, 101))) == 95
    assert load.percentile([]) is None
