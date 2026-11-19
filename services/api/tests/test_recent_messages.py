from types import SimpleNamespace

from services.api.messaging import RecentMessages


def test_previews_are_bounded_redacted_and_expire(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("services.api.messaging.time.monotonic", lambda: clock[0])
    recent = RecentMessages()
    for index in range(110):
        recent.record(
            SimpleNamespace(
                id=str(index),
                tipo="frame.ready",
                metadata=SimpleNamespace(producer="inference"),
                dispositivo="ac_01",
                timestamp="2026-11-14T00:00:00Z",
                conteudo={"secret": "never expose"},
            )
        )
    items = recent.snapshot()["items"]
    assert len(items) == 100 and items[0]["id"] == "109"
    assert "secret" not in str(items) and "conteudo" not in str(items)
    items[0]["type"] = "mutated"
    assert recent.snapshot()["items"][0]["type"] == "frame.ready"
    clock[0] += 301
    assert recent.snapshot()["items"] == []
