"""Fixed local origin/model; bounded NDJSON and explicit stop confirmation."""

import json

import httpx
from smartfan_common.local_llm import MODEL, MODEL_DIGEST


class Ollama:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.client = httpx.AsyncClient(
            base_url="http://ollama:11434",
            timeout=httpx.Timeout(connect=3, read=None, write=3, pool=3),
            trust_env=False,
            transport=transport,
        )

    async def stream(self, messages):
        tags = await self.client.get("/api/tags", timeout=3)
        tags.raise_for_status()
        if not any(
            model.get("name") == MODEL and model.get("digest") == MODEL_DIGEST
            for model in tags.json().get("models", [])
        ):
            raise ValueError("Local model digest differs from approved model")
        async with self.client.stream(
            "POST",
            "/api/chat",
            json={
                "model": MODEL,
                "messages": messages,
                "stream": True,
                "keep_alive": "10m",
                "options": {
                    "num_ctx": 2048,
                    "num_predict": 256,
                    "num_thread": 4,
                    "use_mmap": True,
                    "temperature": 0.2,
                    "seed": 42,
                },
            },
        ) as response:
            response.raise_for_status()
            pending = b""
            size = 0
            async for chunk in response.aiter_bytes():
                pending += chunk
                if len(pending) > 65536:
                    raise ValueError("Oversized local model packet")
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if not line.strip():
                        continue
                    packet = json.loads(line)
                    if not isinstance(packet, dict) or not isinstance(
                        packet.get("message", {}), dict
                    ):
                        raise TypeError("Invalid local model packet")
                    if packet.get("error"):
                        raise ValueError("Local generation failed")
                    content = packet.get("message", {}).get("content", "")
                    if not isinstance(content, str):
                        raise TypeError("Invalid local model packet")
                    size += len(content.encode())
                    if size > 32768:
                        raise ValueError("Local answer exceeds budget")
                    if content:
                        yield {"delta": content}
                    if packet.get("done") is True:
                        yield {"done": True, "tokens": int(packet.get("eval_count", 0))}
                        return
            raise ValueError("Incomplete local stream")

    async def unload(self) -> bool:
        try:
            response = await self.client.post(
                "/api/generate",
                json={"model": MODEL, "keep_alive": 0, "stream": False},
                timeout=4,
            )
            response.raise_for_status()
            response = await self.client.get("/api/ps", timeout=2)
            response.raise_for_status()
            return not response.json().get("models", [])
        except (httpx.HTTPError, ValueError):
            return False

    async def close(self):
        await self.client.aclose()
