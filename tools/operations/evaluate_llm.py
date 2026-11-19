"""Bounded 1B/3B comparison through the existing assistant, never a model search."""

import argparse
import asyncio
import copy
import hashlib
import json
import secrets
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

CURRENT = (
    "llama3.2:1b-instruct-q4_K_M",
    "22bc6b92eb0160c4629782fca05a9032c59d306ab2058b7dacc8a4644fbafa02",
)
CANDIDATE = (
    "llama3.2:3b",
    "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72",
)
QUESTIONS = (
    (
        "rul",
        "O que significa RUL? Com o mesmo uso, 10 h ou 100 h indicam maior urgência? Informe a RUL atual só se disponível.",
    ),
    (
        "health",
        "Saúde do equipamento e qualidade de regressão são a mesma coisa? Cite a saúde atual só se houver previsão.",
    ),
    (
        "metrics",
        "Explique MAE, RMSE e R² e cite os MAEs de teste desta versão com unidades.",
    ),
    (
        "architecture",
        "O sistema é local? Descreva o fluxo MQTT até a tela e as funções de Mosquitto, RabbitMQ, PostgreSQL, InfluxDB e Ollama.",
    ),
    (
        "missing",
        "Neste caso de previsão indisponível e leituras ausentes, pode estimar números de saúde/RUL, concluir normalidade ou limpar o alerta?",
    ),
)


def save(path: Path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


async def worker(directory: Path):
    from smartfan_common.influx_v2 import InfluxHTTP
    from smartfan_common.reliability.database import engine_for
    from sqlalchemy import text

    import services.api.assistant as assistant_module
    import services.api.ollama as ollama_module
    from services.api.assistant import Assistant
    from services.api.assistant_context import ChatRequest, compact, messages, summary
    from services.api.auth import AuthService

    engine = engine_for("api", Path("/run/secrets/postgres_api"))
    auth = AuthService(
        engine, Path("/run/secrets/jwt_signing_key").read_bytes().strip()
    )
    admin = auth.authenticate(
        auth.login(
            "admin",
            Path("/run/secrets/eval_admin_password").read_text().strip(),
            "127.0.0.1",
            str(uuid4()),
        )["access_token"]
    )
    with engine.connect() as conn:
        if conn.execute(
            text("SELECT count(*) FROM app.jobs WHERE status IN ('queued','running')")
        ).scalar_one():
            raise RuntimeError("Pending heavy jobs prevent evaluation")
    frozen = summary(engine, "ac_01", InfluxHTTP(Path("/run/influx/token"), timeout=10))
    cases = []
    for identity, question in QUESTIONS:
        context = copy.deepcopy(frozen)
        if identity == "missing":
            context.update(
                evaluation_case="Fixture explícita de indisponibilidade, não estado atual",
                live="stale",
                prediction={"status": "insufficient_data"},
                past_5min={"status": "unavailable"},
            )
        prepared = copy.deepcopy(context)
        prompt, _ = messages(
            ChatRequest(device_id="ac_01", question=question), prepared
        )
        cases.append(
            {
                "id": identity,
                "question": question,
                "source": "explicit_missing_fixture"
                if identity == "missing"
                else "frozen_real_backend_summary",
                "context": context,
                "sent_context": prepared,
                "prompt": prompt,
                "sha256": hashlib.sha256(compact(prompt).encode()).hexdigest(),
            }
        )
    report = {
        "started": datetime.now(UTC).isoformat(),
        "models": [CURRENT, CANDIDATE],
        "cases": cases,
        "results": [],
        "semantic_review": "manual_required",
        "limits": {
            "first_token_seconds": 30,
            "total_seconds": 90,
            "num_ctx": 2048,
            "num_predict": 256,
            "num_thread": 4,
            "use_mmap": True,
            "temperature": 0.2,
            "seed": 42,
        },
    }
    save(directory / "results.json", report)
    original_summary = assistant_module.summary
    actors = []
    try:
        for model, digest in (CURRENT, CANDIDATE):
            # Only this isolated evaluator process changes bindings. Production
            # files, the running API configuration and model caches are preserved.
            ollama_module.MODEL, ollama_module.MODEL_DIGEST = model, digest
            assistant_module.MODEL = model
            service = Assistant(engine, None, Path("/runtime/assistant"))
            await service.start()  # same exclusive flock as the stopped API
            try:
                if not await service.ollama.unload():
                    raise RuntimeError("Could not prove previous model unloaded")
                password = secrets.token_urlsafe(24)
                username = "eval_" + uuid4().hex[:16]
                actor = auth.create_user(
                    admin, username, password, "visualizador", str(uuid4())
                )
                actors.append(actor["id"])
                principal = auth.authenticate(
                    auth.login(username, password, "127.0.0.1", str(uuid4()))[
                        "access_token"
                    ]
                )
                for index, case in enumerate(cases):
                    save(directory / "phase.json", {"model": model, "case": case["id"]})
                    assistant_module.summary = lambda *_args, captured=case["context"]: (
                        copy.deepcopy(captured)
                    )
                    body = ChatRequest(device_id="ac_01", question=case["question"])
                    correlation = str(uuid4())
                    started = time.monotonic()
                    identity = await service.reserve(principal, body, correlation)
                    result = {
                        "model": model,
                        "case": case["id"],
                        "cold": index == 0,
                        "prompt_sha256": case["sha256"],
                        "request_id": identity,
                        "answer": "",
                        "outcome": "incomplete",
                    }
                    async for packet in service.stream(
                        identity, principal, body, correlation
                    ):
                        raw = packet.decode()
                        if raw.startswith(":"):
                            continue
                        kind = raw.splitlines()[0].removeprefix("event: ")
                        value = json.loads(raw.split("data: ", 1)[1])
                        if kind == "meta" and "summary" in value:
                            if value["summary"] != case["sent_context"]:
                                raise RuntimeError("Comparison context drifted")
                        elif kind == "delta":
                            result["answer"] += value["text"]
                        elif kind == "done":
                            result.update(
                                outcome="completed",
                                first_token_ms=value["first_token_ms"],
                                tokens=value["tokens"],
                            )
                        elif kind == "error":
                            result.update(outcome="failed", reason=value["code"])
                    result["total_ms"] = round((time.monotonic() - started) * 1000)
                    loaded = await service.ollama.client.get("/api/ps", timeout=3)
                    result["loaded_models"] = [
                        {key: row.get(key) for key in ("name", "size", "size_vram")}
                        for row in loaded.json().get("models", [])
                    ]
                    report["results"].append(result)
                    save(directory / "results.json", report)
                    print(
                        json.dumps(
                            {
                                key: result.get(key)
                                for key in (
                                    "model",
                                    "case",
                                    "outcome",
                                    "first_token_ms",
                                    "total_ms",
                                    "reason",
                                )
                            }
                        ),
                        flush=True,
                    )
            finally:
                report["last_unload_confirmed"] = await service.ollama.unload()
                await service.close()
    finally:
        assistant_module.summary = original_summary
        for identity in actors:
            auth.update_user(admin, identity, {"enabled": False}, str(uuid4()))
        report["finished"] = datetime.now(UTC).isoformat()
        report["test_users_disabled"] = len(actors)
        save(directory / "results.json", report)
        engine.dispose()


def host():
    from tools.operations.common import ROOT, compose, exclusive, private

    with exclusive():
        directory = (
            ROOT / "evidence" / "llm" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        )
        private(directory)
        limits = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "inspect",
                    "smartfan-aiot-ollama-1",
                    "--format",
                    "{{json .HostConfig}}",
                ],
                text=True,
            )
        )
        save(
            directory / "limits.json",
            {key: limits[key] for key in ("Memory", "NanoCpus")},
        )
        samples = []
        process = None
        worker_name = "smartfan-llm-eval-" + directory.name.lower()
        try:
            compose("stop", "api")
            command = [
                "docker",
                "compose",
                "run",
                "--rm",
                "--no-deps",
                "--pull",
                "never",
                "--name",
                worker_name,
                "-v",
                f"{ROOT / 'tools'}:/app/tools:ro",
                "-v",
                f"{directory}:/evaluation",
                "-v",
                f"{ROOT / 'secrets/initial_admin_password'}:/run/secrets/eval_admin_password:ro",
                "api",
                "python",
                "-m",
                "tools.operations.evaluate_llm",
                "--worker",
            ]
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            while process.poll() is None:
                phase = directory / "phase.json"
                if phase.exists():
                    sampled = subprocess.run(
                        [
                            "docker",
                            "compose",
                            "exec",
                            "-T",
                            "ollama",
                            "sh",
                            "-c",
                            "cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.stat",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                    )
                    if sampled.returncode == 0:
                        rows = sampled.stdout.splitlines()
                        current = int(rows[0])
                        stats = dict(row.split() for row in rows[1:])
                        samples.append(
                            {
                                **json.loads(phase.read_text()),
                                "utc": datetime.now(UTC).isoformat(),
                                "cgroup_bytes": current,
                                "working_set_bytes": current
                                - int(stats.get("inactive_file", 0)),
                                "anon_bytes": int(stats.get("anon", 0)),
                            }
                        )
                        save(directory / "memory.json", samples)
                time.sleep(1)
            output, _errors = process.communicate()
            print(output)
            if process.returncode:
                raise RuntimeError(
                    "Evaluator failed; raw stderr withheld to protect credentials"
                )
        finally:
            if process is not None and process.poll() is None:
                subprocess.run(
                    ["docker", "stop", "--time", "10", worker_name],
                    capture_output=True,
                    check=False,
                )
                process.wait(timeout=15)
            for model, _digest in (CURRENT, CANDIDATE):
                compose("exec", "-T", "ollama", "ollama", "stop", model)
            compose("start", "api")
            print("Evidence: " + str(directory), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    arguments = parser.parse_args()
    if arguments.worker:
        asyncio.run(worker(Path("/evaluation")))
    else:
        host()
