"""Historical projections are authorized, bounded and separate from live values."""
# ruff: noqa: F811

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_api_integration import api, headers, login  # noqa: F401
from test_models_integration import reset_models  # noqa: F401
from test_reliability_integration import database, reset_disposable_rows  # noqa: F401

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists(),
    reason="Requires isolated PostgreSQL roles",
)


def test_history_keeps_original_model_nulls_and_paginates_without_raw_access(
    api, database
):
    client = api[0]
    now = datetime.now(UTC)
    sources = []
    with database[0].begin() as conn:
        for index, age in enumerate((1, 2, 26 * 3600)):
            identity = str(uuid4())
            sources.append(identity)
            conn.execute(
                text(
                    "INSERT INTO app.inference_results(source_event_id,persisted_event_id,device_id,boot_id,sequence,sampled_at,observed_at,model_version,insight_sha256,insight_payload) VALUES(:id,:persisted,'ac_01',:boot,:sequence,:at,:at,:version,:hash,:payload)"
                ),
                {
                    "id": identity,
                    "persisted": str(uuid4()),
                    "boot": str(uuid4()),
                    "sequence": index,
                    "at": now - timedelta(seconds=age),
                    "version": "original-model",
                    "hash": "a" * 64,
                    "payload": json.dumps(
                        {
                            "conteudo": {
                                "status": "valid"
                                if index == 0
                                else "model_unavailable",
                                "health_score": 61 if index == 0 else None,
                                "rul_calendar_hours": 25 if index == 0 else None,
                            }
                        }
                    ).encode(),
                },
            )
    path = "/api/v1/devices/ac_01/insights/history"
    assert client.get(path).status_code == 401
    for name in ("admin", "operador", "visualizador"):
        auth = headers(login(api, name))
        response = client.get(path + "?hours=24&limit=1", headers=auth)
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "historical_predictions"
        assert body["items"][0]["source_event_id"] == sources[0]
        assert body["items"][0]["model_version"] == "original-model"
        assert body["items"][0]["health_score"] == 61
        assert "insight_payload" not in body["items"][0]
        second = client.get(
            path + "?hours=24&limit=1&before=" + body["next_cursor"], headers=auth
        ).json()
        assert second["items"][0]["health_score"] is None
        assert second["next_cursor"] is None
        assert client.get(path + "?hours=25", headers=auth).status_code == 422
        assert client.get(path + "?limit=501", headers=auth).status_code == 422
    with database[1]["api"].connect() as conn, pytest.raises(DBAPIError):
        conn.execute(text("SELECT insight_payload FROM app.inference_results"))
