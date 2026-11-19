import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from services.api.assistant import sse
from services.api.assistant_context import (
    ARCHITECTURE,
    ChatRequest,
    compact,
    messages,
    model_metrics,
)
from services.api.errors import Problem
from services.api.ollama import MODEL, MODEL_DIGEST, Ollama


def test_metrics_are_finite_and_tied_to_exact_version():
    report: dict[str, Any] = {
        "model_version": "mdl_test",
        "targets": {
            name: {"test": {"mae": 1.2, "rmse": 2.3, "r2": 0.8}, "private": "omit"}
            for name in ("health_score", "rul_calendar_hours")
        },
    }
    assert model_metrics(report, "mdl_other")["status"] == "unavailable"
    result = model_metrics(report, "mdl_test")
    assert result["status"] == "test_synthetic" and "private" not in str(result)
    context: dict[str, Any] = {"model_metrics": result, "architecture": ARCHITECTURE}
    prompt, _ = messages(
        ChatRequest(
            device_id="ac_01", question="Explique as métricas e a arquitetura."
        ),
        context,
    )
    assert "mdl_test" in prompt[1]["content"] and "RabbitMQ" in prompt[1]["content"]
    report["targets"]["health_score"]["test"]["r2"] = float("nan")
    assert model_metrics(report, "mdl_test")["status"] == "unavailable"


def test_context_does_not_mix_regression_metrics_with_equipment_health():
    context: dict[str, Any] = {
        "prediction": {"status": "inactive"},
        "model_metrics": {"version": "mdl_test"},
        "architecture": ARCHITECTURE,
        "sources": ["source"],
        "past_5min": {"temperature_mean": 28.3},
    }
    messages(ChatRequest(device_id="ac_01", question="O que significa RUL?"), context)
    assert context["prediction"]["status"] == "inactive"
    assert "model_metrics" not in context and "architecture" not in context
    assert "past_5min" not in context
    assert context["sources"] == ["source"]
    context = {
        "prediction": {"status": "valid", "saude_compressor_percentual": 87},
        "model_metrics": {"version": "mdl_test"},
    }
    messages(ChatRequest(device_id="ac_01", question="Explique MAE e RMSE."), context)
    assert (
        "prediction" not in context
        and context["model_metrics"]["version"] == "mdl_test"
    )


def test_summary_budget_history_roles_and_unicode_question_limits():
    body = ChatRequest.model_validate(
        {
            "device_id": "ac_01",
            "question": "O que foi observado?",
            "history": [{"question": "Olá", "answer": "Resumo anterior."}],
        }
    )
    context: dict[str, Any] = {"device": "ac_01", "live": "stale", "sources": []}
    result, turns = messages(body, context)
    assert turns == 1 and result[0]["role"] == "system"
    assert result[-1]["content"] == body.question
    assert sum(len(item["content"].encode()) for item in result) <= 1700
    with pytest.raises(Problem):
        messages(ChatRequest(device_id="ac_01", question="界" * 1000), context)
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "device_id": "ac_01",
                "question": "x",
                "history": [{"question": "x", "answer": "y", "role": "system"}],
            }
        )


def test_sse_escapes_newlines_without_inserting_events():
    wire = sse("delta", {"text": "x\n\nevent: done\n<script>"})
    assert wire.count(b"\n\n") == 1
    assert json.loads(wire.decode().split("data: ", 1)[1])["text"].endswith("<script>")


def test_ollama_protocol_rejects_incomplete_stream_and_unknown_digest():
    async def scenario():
        seen = []
        approved = True

        def handler(request):
            seen.append(request)
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={
                        "models": [
                            {
                                "name": MODEL,
                                "digest": MODEL_DIGEST if approved else "unknown",
                            }
                        ]
                    },
                )
            payload = json.loads(request.content)
            assert payload["options"]["num_ctx"] == 2048
            assert "tools" not in payload
            return httpx.Response(
                200, content=compact({"message": {"content": "Olá"}}).encode() + b"\n"
            )

        ollama = Ollama(httpx.MockTransport(handler))
        received = []
        with pytest.raises(ValueError, match="Incomplete"):
            async for packet in ollama.stream([{"role": "user", "content": "Oi"}]):
                received.append(packet)
        assert received == [{"delta": "Olá"}]
        assert all(request.url.host == "ollama" for request in seen)
        approved = False
        with pytest.raises(ValueError, match="digest"):
            async for _ in ollama.stream([{"role": "user", "content": "Oi"}]):
                pass
        assert sum(request.url.path == "/api/chat" for request in seen) == 1
        await ollama.close()

    asyncio.run(scenario())
