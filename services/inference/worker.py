"""One committed prediction per source; retries reuse the exact original derived bytes."""

from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from smartfan_common.contracts_v2 import (
    FrameReadyV2,
    InsightPredictedV2,
    ModelAvailableV2,
    TelemetryPersistedV2,
    parse_event_v2,
    payload_sha256,
    serialize_event_v2,
)
from smartfan_common.features import FEATURE_VERSION
from smartfan_common.provenance_v2 import telemetry_digest
from smartfan_common.reliability.amqp import authenticated_publisher
from smartfan_common.reliability.store import Delivery, DurableStore, Outbound
from smartfan_common.routing_v2 import routing_key_v2
from sqlalchemy import text

from .models import ModelRuntime
from .window import Windows


def fresh(event, now: datetime) -> bool:
    age = (now - datetime.fromisoformat(event.timestamp)).total_seconds()
    observed = datetime.fromisoformat(event.metadata.observed_at)
    return (
        0 <= age <= 6
        and datetime.fromisoformat(event.timestamp) <= observed <= now
        and (now - observed).total_seconds() <= 6
    )


class Inference:
    def __init__(self, store: DurableStore, models: ModelRuntime, windows: Windows):
        if store.owner != "inference":
            raise ValueError("Inference role required")
        self.store = store
        self.models = models
        self.windows = windows
        self.pending: OrderedDict[
            str, tuple[bytes, bytes, int | None, tuple[float, ...] | None]
        ] = OrderedDict()

    def provenance(self, conn, event: TelemetryPersistedV2) -> None:
        original = conn.execute(
            text(
                "SELECT observed_at,sampled_at,device_id,boot_id,sequence,data_sha256,zone FROM transport.receipts WHERE event_id=:id"
            ),
            {"id": event.conteudo.source_event_id},
        ).first()
        if (
            original is None
            or original[0] != datetime.fromisoformat(event.metadata.observed_at)
            or original[1] != datetime.fromisoformat(event.timestamp)
            or original[2] != event.dispositivo
            or str(original[3]) != event.metadata.boot_id
            or original[4] != event.metadata.sequence
            or original[5] != telemetry_digest(event.conteudo)
            or original[6] != event.metadata.zone
        ):
            raise ValueError("Persisted source differs from original telemetry")

    def receive(
        self, raw: bytes, route: str, user_id: str | None, message_id: str | None
    ) -> None:
        try:
            event = parse_event_v2(raw)
            if (
                not isinstance(event, (TelemetryPersistedV2, ModelAvailableV2))
                or not authenticated_publisher(event, user_id)
                or message_id != event.id
                or routing_key_v2(event)[1] != route
            ):
                raise ValueError("Invalid inference provenance")
            with self.store.transaction() as conn:
                if isinstance(event, TelemetryPersistedV2):
                    self.provenance(conn, event)
                    # Source is already durably persisted. Old input gets a durable
                    # dedupe receipt, not a fabricated retrospective live forecast.
                    if (
                        datetime.now(UTC) - datetime.fromisoformat(event.timestamp)
                    ).total_seconds() > 6:
                        inserted = conn.execute(
                            text(
                                "INSERT INTO transport.inbox(owner,event_id,sha256,payload,route,state,finished_at,reason_code) VALUES('inference',:id,:hash,NULL,:route,'completed',clock_timestamp(),'stale_prediction_source') ON CONFLICT(owner,event_id) DO NOTHING RETURNING event_id"
                            ),
                            {
                                "id": event.id,
                                "hash": payload_sha256(raw),
                                "route": route,
                            },
                        ).scalar_one_or_none()
                        if inserted is None:
                            previous = conn.execute(
                                text(
                                    "SELECT sha256 FROM transport.inbox WHERE owner='inference' AND event_id=:id"
                                ),
                                {"id": event.id},
                            ).scalar_one()
                            if previous != payload_sha256(raw):
                                raise ValueError("Stale identity conflict")
                        return
                self.store.receive(event.id, raw, route, connection=conn)
        except ValueError:
            self.store.quarantine(raw, route[:256], "invalid_inference_event")

    def calculate(
        self, event: TelemetryPersistedV2
    ) -> tuple[bytes, bytes, int | None, tuple[float, ...] | None]:
        result = self.windows.push(event)
        with self.models.lock:
            loaded = self.models.current if self.models.synchronized else None
            version = loaded.version if loaded else None
            insight: dict[str, Any] = {
                "status": "model_unavailable",
                "model_version": version,
                "feature_version": FEATURE_VERSION,
                "health_score": None,
                "rul_calendar_hours": None,
            }
            if loaded is not None and result.status != "valid":
                insight["status"] = (
                    "stale" if result.status == "ignored" else result.status
                )
            elif loaded is not None:
                import numpy as np
                from smartfan_common.ml_pipeline import predict_target

                X = np.asarray([result.values], dtype=np.float64)
                with self.store.engine.connect() as conn:
                    drift = conn.execute(
                        text(
                            "SELECT active FROM app.drift_states WHERE device_id=:id AND model_version=:version"
                        ),
                        {"id": event.dispositivo, "version": version},
                    ).scalar_one_or_none()
                if drift:
                    insight["status"] = "out_of_domain"
                else:
                    insight.update(
                        status="valid",
                        health_score=float(
                            predict_target(
                                loaded.bundle["models"]["health_score"],
                                X,
                                "health_score",
                            )[0]
                        ),
                        rul_calendar_hours=float(
                            predict_target(
                                loaded.bundle["models"]["rul_calendar_hours"],
                                X,
                                "rul_calendar_hours",
                            )[0]
                        ),
                    )
        metadata = event.metadata.model_dump()
        metadata.update(producer="inference", causation_id=event.id)
        shared = {
            "schema_version": "2.1",
            "timestamp": event.timestamp,
            "dispositivo": event.dispositivo,
            "correlation_id": event.correlation_id,
            "metadata": metadata,
        }
        source = event.conteudo.source_event_id
        frame = FrameReadyV2.model_validate(
            {
                **shared,
                "id": str(uuid5(NAMESPACE_URL, "smartfan:frame:" + source)),
                "tipo": "frame.ready",
                "conteudo": {
                    "source_event_id": source,
                    "telemetry": event.conteudo.model_dump(),
                    "insight": insight,
                },
            }
        )
        predicted = InsightPredictedV2.model_validate(
            {
                **shared,
                "id": str(uuid5(NAMESPACE_URL, "smartfan:insight:" + source)),
                "tipo": "insight.predicted",
                "conteudo": {"source_event_id": source, **insight},
            }
        )
        return (
            serialize_event_v2(frame),
            serialize_event_v2(predicted),
            loaded.revision if loaded else None,
            result.values,
        )

    def drift(
        self, conn, event: TelemetryPersistedV2, version: str, values: tuple[float, ...]
    ) -> None:
        import numpy as np

        with self.models.lock:
            loaded = self.models.current
            if loaded is None or loaded.version != version:
                return
            array = np.asarray(values)
            outside = float(
                np.mean(
                    (array < loaded.bundle["drift_low"])
                    | (array > loaded.bundle["drift_high"])
                )
            )
        conn.execute(
            text(
                "INSERT INTO app.drift_states(device_id,model_version) VALUES(:id,:version) ON CONFLICT(device_id) DO NOTHING"
            ),
            {"id": event.dispositivo, "version": version},
        )
        row = (
            conn.execute(
                text("SELECT * FROM app.drift_states WHERE device_id=:id FOR UPDATE"),
                {"id": event.dispositivo},
            )
            .mappings()
            .one()
        )
        same = row["model_version"] == version
        samples = row["samples"] + 1 if same else 1
        outside_sum = row["outside_sum"] + outside if same else outside
        bad = row["bad_windows"] if same else 0
        good = row["good_windows"] if same else 0
        active = row["active"]
        if samples >= 1000:
            if outside_sum / samples > 0.2:
                bad += 1
                good = 0
            else:
                good += 1
                bad = 0
            if bad >= 3:
                active = True
            elif good >= 3:
                active = False
            samples = 0
            outside_sum = 0
        conn.execute(
            text(
                "UPDATE app.drift_states SET model_version=:version,samples=:samples,outside_sum=:outside,bad_windows=:bad,good_windows=:good,active=:active,updated_at=clock_timestamp() WHERE device_id=:id"
            ),
            {
                "id": event.dispositivo,
                "version": version,
                "samples": samples,
                "outside": outside_sum,
                "bad": bad,
                "good": good,
                "active": active,
            },
        )

    def process(self, delivery: Delivery) -> None:
        event = parse_event_v2(delivery.payload)
        if isinstance(event, ModelAvailableV2):
            self.models.synchronize(expected_version=event.conteudo.model_version)
            self.store.finish(delivery)
            return
        if not isinstance(event, TelemetryPersistedV2):
            raise TypeError("Wrong inference input")
        now = datetime.now(UTC)
        if not fresh(event, now):
            self.store.finish(delivery)
            return
        with self.store.engine.connect() as conn:
            device = conn.execute(
                text(
                    "SELECT d.enabled,d.zone,p.boot_id FROM app.device_registry d JOIN transport.device_status p ON p.device_id=d.id WHERE d.id=:id"
                ),
                {"id": event.dispositivo},
            ).first()
            existing = conn.execute(
                text(
                    "SELECT frame_payload,insight_payload,activation_revision FROM app.inference_results WHERE source_event_id=:id"
                ),
                {"id": event.conteudo.source_event_id},
            ).first()
        if (
            not device
            or not device[0]
            or device[1] != event.metadata.zone
            or str(device[2]) != event.metadata.boot_id
        ):
            self.store.finish(delivery)
            return
        source = event.conteudo.source_event_id
        candidate: tuple[bytes, bytes, int | None, tuple[float, ...] | None]
        if existing:
            candidate = (bytes(existing[0]), bytes(existing[1]), existing[2], None)
        else:
            if source not in self.pending:
                self.pending[source] = self.calculate(event)
            candidate = self.pending[source]
        frame_raw, insight_raw, revision, values = candidate
        frame = parse_event_v2(frame_raw)
        predicted = parse_event_v2(insight_raw)
        assert isinstance(frame, FrameReadyV2) and isinstance(
            predicted, InsightPredictedV2
        )

        def effects(conn):
            inserted = conn.execute(
                text(
                    "INSERT INTO app.inference_results(source_event_id,persisted_event_id,device_id,boot_id,sequence,sampled_at,observed_at,model_version,activation_revision,insight_sha256,frame_payload,insight_payload) VALUES(:source,:persisted,:device,:boot,:sequence,:sample,:observed,:version,:revision,:hash,:frame,:insight) ON CONFLICT(source_event_id) DO NOTHING RETURNING source_event_id"
                ),
                {
                    "source": source,
                    "persisted": event.id,
                    "device": event.dispositivo,
                    "boot": event.metadata.boot_id,
                    "sequence": event.metadata.sequence,
                    "sample": datetime.fromisoformat(event.timestamp),
                    "observed": datetime.fromisoformat(event.metadata.observed_at),
                    "version": predicted.conteudo.model_version,
                    "revision": revision,
                    "hash": payload_sha256(insight_raw),
                    "frame": frame_raw,
                    "insight": insight_raw,
                },
            ).scalar_one_or_none()
            winner = conn.execute(
                text(
                    "SELECT frame_payload,insight_payload FROM app.inference_results WHERE source_event_id=:source"
                ),
                {"source": source},
            ).one()
            for raw in (bytes(winner[0]), bytes(winner[1])):
                output = parse_event_v2(raw)
                exchange, route = routing_key_v2(output)
                self.store.enqueue(
                    Outbound(output.id, raw, exchange, route), connection=conn
                )
            if (
                inserted is not None
                and values is not None
                and predicted.conteudo.model_version
            ):
                self.drift(conn, event, predicted.conteudo.model_version, values)

        self.store.finish(delivery, effects=effects)
        self.pending.pop(source, None)
        while len(self.pending) > 256:
            self.pending.popitem(last=False)
