"""Immutable training requests and transactional selection; never publishes as a worker."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from smartfan_common.contracts_v2 import (
    JobRequestedV2,
    payload_sha256,
    serialize_event_v2,
)
from smartfan_common.lab_config import LabConfig
from smartfan_common.model_policy import promotion_reasons
from smartfan_common.reliability.store import DurableStore, Outbound
from smartfan_common.routing_v2 import routing_key_v2
from smartfan_common.training_config import TrainingRequest, TrainingTask
from sqlalchemy import text

from .auth import Principal, audit
from .errors import Problem
from .lab import Lab


class Models:
    def __init__(self, store: DurableStore):
        self.store = store

    def train(
        self, request: TrainingRequest, principal: Principal, key: str, correlation: str
    ) -> dict:
        request_raw = json.dumps(
            request.model_dump(), sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(request_raw.encode()).hexdigest()
        with self.store.transaction() as conn:
            conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": "lab-request:" + principal.id + ":" + key},
            )
            previous = conn.execute(
                text(
                    "SELECT id,request_hash FROM app.jobs WHERE actor_user_id=:actor AND idempotency_key=:key"
                ),
                {"actor": principal.id, "key": key},
            ).first()
            if previous:
                if previous[1] != digest:
                    raise Problem(
                        409,
                        "idempotency_conflict",
                        "Chave já utilizada com outro pedido.",
                    )
                job_id = str(previous[0])
            else:
                conn.execute(text("SELECT pg_advisory_xact_lock(734121)"))
                if (
                    conn.execute(
                        text(
                            "SELECT count(*) FROM app.jobs WHERE status IN ('queued','running')"
                        )
                    ).scalar_one()
                    >= 10
                ):
                    raise Problem(
                        409, "job_queue_full", "Fila de jobs atingiu o limite."
                    )
                dataset = (
                    conn.execute(
                        text("SELECT * FROM app.datasets WHERE id=:id"),
                        {"id": request.dataset_id},
                    )
                    .mappings()
                    .first()
                )
                if (
                    dataset is None
                    or dataset["status"] != "completed"
                    or not dataset["sha256"]
                ):
                    raise Problem(
                        409,
                        "dataset_not_ready",
                        "Treino exige dataset completo verificado.",
                    )
                source_config = LabConfig.model_validate(dataset["configuration"])
                if (
                    source_config.equipment_count < 10
                    or request.benchmark_seed == source_config.seed
                ):
                    raise Problem(
                        409,
                        "training_diversity",
                        "Use pelo menos dez equipamentos e seed de benchmark diferente da geração.",
                    )
                selection = (
                    conn.execute(
                        text(
                            "SELECT * FROM app.model_selection WHERE singleton FOR SHARE"
                        )
                    )
                    .mappings()
                    .one()
                )
                active = selection["active_version"]
                bundle_hash = None
                if active:
                    manifest = conn.execute(
                        text(
                            "SELECT manifest FROM app.models WHERE version=:version AND approved AND status='completed'"
                        ),
                        {"version": active},
                    ).scalar_one_or_none()
                    if not manifest:
                        raise Problem(
                            409,
                            "active_not_comparable",
                            "Registro ativo indisponível para comparação.",
                        )
                    bundle_hash = manifest["content"]["files"]["bundle.joblib"]
                job_id = str(uuid4())
                version = "mdl_" + uuid4().hex
                task = TrainingTask(
                    request=request,
                    model_version=version,
                    dataset_sha256=dataset["sha256"],
                    source_config=source_config,
                    active_model_version=active,
                    active_bundle_sha256=bundle_hash,
                )
                task_raw = json.dumps(
                    task.model_dump(), sort_keys=True, separators=(",", ":")
                )
                event = JobRequestedV2.model_validate(
                    {
                        "id": job_id,
                        "schema_version": "2.1",
                        "timestamp": datetime.now(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "tipo": "job.train",
                        "dispositivo": None,
                        "correlation_id": correlation,
                        "metadata": {"producer": "api", "causation_id": None},
                        "conteudo": {
                            "job_id": job_id,
                            "dataset_id": request.dataset_id,
                            "config_version": 1,
                        },
                    }
                )
                payload = serialize_event_v2(event)
                conn.execute(
                    text(
                        "INSERT INTO app.jobs(id,dataset_id,kind,actor_user_id,idempotency_key,request_hash,event_sha256,correlation_id,total) VALUES(:id,:dataset,'train',:actor,:key,:hash,:event_hash,:correlation,100)"
                    ),
                    {
                        "id": job_id,
                        "dataset": request.dataset_id,
                        "actor": principal.id,
                        "key": key,
                        "hash": digest,
                        "event_hash": payload_sha256(payload),
                        "correlation": correlation,
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO app.training_requests(job_id,configuration,configuration_sha256) VALUES(:id,CAST(:config AS jsonb),:hash)"
                    ),
                    {
                        "id": job_id,
                        "config": task_raw,
                        "hash": hashlib.sha256(task_raw.encode()).hexdigest(),
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO app.models(version,dataset_id,job_id) VALUES(:version,:dataset,:job)"
                    ),
                    {"version": version, "dataset": request.dataset_id, "job": job_id},
                )
                exchange, route = routing_key_v2(event)
                self.store.enqueue(
                    Outbound(event.id, payload, exchange, route), connection=conn
                )
                audit(
                    conn,
                    principal.id,
                    "training.requested",
                    "model",
                    version,
                    correlation,
                    {"job_id": job_id, "dataset_id": request.dataset_id},
                )
        return Lab(self.store).job(UUID(job_id))

    def list(self, limit: int = 50, before: str | None = None) -> dict:
        with self.store.engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT version,dataset_id,job_id,status,approved,artifact_sha256,created_at FROM app.models WHERE (:before IS NULL OR (created_at,version)<(SELECT created_at,version FROM app.models WHERE version=:before)) ORDER BY created_at DESC,version DESC LIMIT :limit"
                    ),
                    {"limit": limit + 1, "before": before},
                )
                .mappings()
                .all()
            )
            selection = (
                conn.execute(
                    text(
                        "SELECT desired_version,active_version,activation_revision,active_revision FROM app.model_selection WHERE singleton"
                    )
                )
                .mappings()
                .one()
            )
        return {
            "items": [dict(row) for row in rows[:limit]],
            "selection": dict(selection),
            "next_cursor": rows[limit - 1]["version"] if len(rows) > limit else None,
        }

    def get(self, version: str) -> dict:
        with self.store.engine.connect() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM app.models WHERE version=:version"),
                    {"version": version},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise Problem(404, "model_not_found", "Modelo não encontrado.")
        result = dict(row)
        if result["report"]:
            with self.store.engine.connect() as conn:
                active = conn.execute(
                    text(
                        "SELECT active_version FROM app.model_selection WHERE singleton"
                    )
                ).scalar_one()
            result["promotion_reasons"] = promotion_reasons(result["report"], active)
        return result

    def promote(
        self,
        version: str,
        request_id: UUID,
        expected_revision: int,
        principal: Principal,
        correlation: str,
    ) -> dict:
        digest = hashlib.sha256(
            json.dumps(
                {"version": version, "expected_revision": expected_revision},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with self.store.transaction() as conn:
            selection = (
                conn.execute(
                    text("SELECT * FROM app.model_selection WHERE singleton FOR UPDATE")
                )
                .mappings()
                .one()
            )
            old = conn.execute(
                text(
                    "SELECT version,request_hash,revision FROM app.activation_notifications WHERE id=:id"
                ),
                {"id": str(request_id)},
            ).first()
            if old:
                if old[0] != version or old[1] != digest:
                    raise Problem(
                        409,
                        "idempotency_conflict",
                        "Pedido de promoção já usado com outro conteúdo.",
                    )
                return {
                    "desired_version": old[0],
                    "activation_revision": old[2],
                    "active_version": selection["active_version"],
                    "status": "already_requested",
                }
            if selection["activation_revision"] != expected_revision:
                raise Problem(
                    409,
                    "selection_changed",
                    "Seleção mudou; atualize antes de promover.",
                )
            model = (
                conn.execute(
                    text("SELECT * FROM app.models WHERE version=:version FOR UPDATE"),
                    {"version": version},
                )
                .mappings()
                .first()
            )
            if (
                model is None
                or model["status"] != "completed"
                or not model["manifest"]
                or not model["report"]
            ):
                raise Problem(
                    409, "model_not_ready", "Candidato ainda não está completo."
                )
            reasons = promotion_reasons(model["report"], selection["active_version"])
            if reasons:
                raise Problem(
                    409,
                    "promotion_rejected",
                    "Candidato não atende à política: " + ", ".join(reasons),
                )
            revision = selection["activation_revision"] + 1
            conn.execute(
                text(
                    "UPDATE app.models SET approved=true,approved_against_version=:active,approved_by=:actor,approved_at=clock_timestamp() WHERE version=:version"
                ),
                {
                    "version": version,
                    "active": selection["active_version"],
                    "actor": principal.id,
                },
            )
            conn.execute(
                text(
                    "UPDATE app.model_selection SET desired_version=:version,activation_revision=:revision,updated_at=clock_timestamp() WHERE singleton"
                ),
                {"version": version, "revision": revision},
            )
            conn.execute(
                text(
                    "INSERT INTO app.activation_notifications(id,version,revision,request_hash,actor_user_id,correlation_id) VALUES(:id,:version,:revision,:hash,:actor,:correlation)"
                ),
                {
                    "id": str(request_id),
                    "version": version,
                    "revision": revision,
                    "hash": digest,
                    "actor": principal.id,
                    "correlation": correlation,
                },
            )
            audit(
                conn,
                principal.id,
                "model.promotion_requested",
                "model",
                version,
                correlation,
                {
                    "activation_revision": revision,
                    "active_reference_version": selection["active_version"],
                },
            )
        return {
            "desired_version": version,
            "activation_revision": revision,
            "active_version": selection["active_version"],
            "status": "awaiting_inference",
        }
