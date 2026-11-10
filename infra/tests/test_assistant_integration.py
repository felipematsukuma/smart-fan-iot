"""Real PG permissions/rate limits and deterministic upstream cancellation proofs."""
# ruff: noqa: F811

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from smartfan_common.reliability.leases import ResourceLeases
from sqlalchemy import text
from test_api_integration import api, headers, login  # noqa: F401
from test_reliability_integration import database, reset_disposable_rows  # noqa: F401

from services.api.assistant import Assistant
from services.api.assistant_context import ChatRequest
from services.api.errors import Problem
from services.api.main import create_app
from services.api.ollama import Ollama

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists(), reason="Requires isolated PG"
)


@pytest.fixture(autouse=True)
def clear_requests(database):
    with database[0].begin() as conn:
        conn.execute(text("TRUNCATE app.assistant_requests"))


class LocalFixture(Ollama):
    def __init__(self, block=False):
        self.block = block
        self.prompts = []
        self.stopped = False
        self.stop_proof = True
        self.unloads = 0
        self.started = asyncio.Event()

    async def stream(self, messages):
        self.prompts.append(messages)
        self.started.set()
        try:
            yield {"delta": "**Resumo** local."}
            if self.block:
                await asyncio.Event().wait()
            yield {"done": True, "tokens": 5}
        finally:
            self.stopped = True

    async def unload(self):
        self.unloads += 1
        return self.stop_proof

    async def close(self):
        pass


def test_authenticated_stream_summary_and_audit_without_prompt_transcript(
    api, database
):
    _, auth, _, key = api
    local = LocalFixture()
    service = Assistant(database[1]["api"], None, ollama=local)
    with TestClient(
        create_app(database[1]["api"], key, auth=auth, assistant=service)
    ) as chat:
        body = {"device_id": "ac_01", "question": "Resuma o estado do compressor."}
        assert chat.post("/api/v1/assistant/chat", json=body).status_code == 401
        for name in ("admin", "operador", "visualizador"):
            response = chat.post(
                "/api/v1/assistant/chat", json=body, headers=headers(login(api, name))
            )
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert "event: delta" in response.text and "event: done" in response.text
            assert "event: error" not in response.text
    assert all(
        "readings" not in json.dumps(prompt) and "password" not in json.dumps(prompt)
        for prompt in local.prompts
    )
    with database[0].connect() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM app.assistant_requests WHERE outcome='completed' AND tokens=5 AND length(summary_sha256)=64"
                )
            ).scalar_one()
            == 3
        )
        audit = str(
            conn.execute(
                text("SELECT details FROM app.audit WHERE action LIKE 'assistant.%'")
            ).all()
        )
        assert body["question"] not in audit


def test_user_limit_survives_service_restart_and_jobs_block_admission(api, database):
    _, auth, _, key = api
    token = login(api, "visualizador")
    body = {"device_id": "ac_01", "question": "Resuma."}
    for limit in (5, 1):
        service = Assistant(database[1]["api"], None, ollama=LocalFixture())
        with TestClient(
            create_app(database[1]["api"], key, auth=auth, assistant=service)
        ) as client:
            for _ in range(limit):
                response = client.post(
                    "/api/v1/assistant/chat", json=body, headers=headers(token)
                )
                assert response.status_code == (200 if limit == 5 else 429)

    async def occupied():
        lease = ResourceLeases(database[1]["jobs-worker"], "jobs-worker")
        token = lease.acquire(str(uuid4()), "train")
        assert token is not None
        service = Assistant(database[1]["api"], None, ollama=LocalFixture())
        await service.start()
        with pytest.raises(Problem) as failure:
            await service.reserve(
                auth.authenticate(login(api)),
                ChatRequest.model_validate(body),
                str(uuid4()),
            )
        assert failure.value.status == 503
        await service.close()
        assert lease.release_after_confirmed_stop(token)

    asyncio.run(occupied())


def test_disconnect_closes_upstream_and_failed_stop_proof_keeps_resource_fenced(
    api, database
):
    principal = api[1].authenticate(login(api))

    async def scenario():
        local = LocalFixture(block=True)
        local.stop_proof = False
        service = Assistant(database[1]["api"], None, ollama=local)
        await service.start()
        body = ChatRequest(device_id="ac_01", question="Resuma.")
        identity = await service.reserve(principal, body, str(uuid4()))
        stream = service.stream(identity, principal, body, str(uuid4()))
        for _ in range(3):
            await anext(stream)
        await stream.aclose()
        assert local.stopped and local.unloads == 1
        assert service.pending == 0 and not service.ready
        with pytest.raises(Problem):
            await service.reserve(principal, body, str(uuid4()))
        lease = ResourceLeases(database[1]["jobs-worker"], "jobs-worker")
        assert lease.acquire(str(uuid4()), "train") is None
        local.stop_proof = True
        await service.recover()
        assert service.resource()[3] == "released"
        with database[0].connect() as conn:
            assert (
                conn.execute(
                    text("SELECT outcome FROM app.assistant_requests WHERE id=:id"),
                    {"id": identity},
                ).scalar_one()
                == "cancelled"
            )
        await service.close()

    asyncio.run(scenario())


def test_one_active_two_waiting_and_no_fourth_admission(api, database):
    principal = api[1].authenticate(login(api))

    async def scenario():
        local = LocalFixture(block=True)
        service = Assistant(database[1]["api"], None, ollama=local)
        await service.start()
        body = ChatRequest(device_id="ac_01", question="Resuma.")
        streams = []
        for _ in range(3):
            identity = await service.reserve(principal, body, str(uuid4()))
            stream = service.stream(identity, principal, body, str(uuid4()))
            await anext(stream)
            streams.append(stream)
        await local.started.wait()
        with pytest.raises(Problem) as failure:
            await service.reserve(principal, body, str(uuid4()))
        assert failure.value.code == "assistant_queue_full" and len(local.prompts) == 1
        # Cancel waiting streams first; only the active stream must stop upstream.
        for stream in reversed(streams):
            await stream.aclose()
        assert service.pending == 0 and service.resource()[3] == "released"
        await service.close()

    asyncio.run(scenario())


def test_renewal_loss_cancels_generation_before_releasing_resource(
    api, database, monkeypatch
):
    principal = api[1].authenticate(login(api))

    async def scenario():
        local = LocalFixture(block=True)
        service = Assistant(database[1]["api"], None, ollama=local)
        await service.start()

        async def lost(*_):
            await local.started.wait()

        monkeypatch.setattr(service, "renew", lost)
        body = ChatRequest(device_id="ac_01", question="Resuma.")
        identity = await service.reserve(principal, body, str(uuid4()))
        result = b"".join(
            [
                item
                async for item in service.stream(
                    identity, principal, body, str(uuid4())
                )
            ]
        )
        assert b"event: error" in result and b"resource_or_session_lost" in result
        assert (
            local.stopped and local.unloads == 1 and service.resource()[3] == "released"
        )
        await service.close()

    asyncio.run(scenario())


def test_abandoned_headers_release_admission_and_global_limit_is_durable(api, database):
    principal = api[1].authenticate(login(api))

    async def scenario():
        service = Assistant(database[1]["api"], None, ollama=LocalFixture())
        await service.start()
        body = ChatRequest(device_id="ac_01", question="Resuma.")
        for _ in range(5):
            identity = await service.reserve(principal, body, str(uuid4()))
            await service.abandon(identity)
        assert service.pending == 0
        with database[0].begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO app.assistant_requests(id,actor_user_id,instance_id,device_id,question_sha256,summary_sha256,sources,model,outcome) SELECT gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),'ac_01',repeat('a',64),repeat('b',64),'[]','fixture','completed' FROM generate_series(1,15)"
                )
            )
        # Different authenticated actor avoids the per-user limit; global 20 wins.
        other = api[1].authenticate(login(api, "visualizador"))
        with pytest.raises(Problem) as failure:
            await service.reserve(other, body, str(uuid4()))
        assert failure.value.code == "assistant_rate_limit"
        await service.close()

    asyncio.run(scenario())
