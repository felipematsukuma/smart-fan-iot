"""Atomic model pointer swaps under the same SQL fence used by the promoter."""

import hashlib
import io
import json
import pickle
import re
import threading
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from smartfan_common.contracts_v2 import ModelActivatedV2, serialize_event_v2
from smartfan_common.features import FEATURE_NAMES, FEATURE_VERSION, FeatureConfig
from smartfan_common.model_policy import promotion_reasons
from smartfan_common.reliability.store import DurableStore, Outbound
from smartfan_common.routing_v2 import routing_key_v2
from sqlalchemy import text


@dataclass(frozen=True)
class LoadedModel:
    version: str
    revision: int
    sha256: str
    bundle: dict


class ModelRuntime:
    def __init__(self, store: DurableStore, root: Path):
        if store.owner != "inference":
            raise ValueError("Inference account required")
        self.store = store
        self.root = root
        self.current: LoadedModel | None = None
        self.lock = threading.RLock()
        self.synchronized = True
        self.last_error: str | None = None

    def selection(self):
        with self.store.engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT s.desired_version,s.activation_revision,s.active_version,s.active_revision,m.* FROM app.model_selection s LEFT JOIN app.models m ON m.version=s.desired_version WHERE s.singleton"
                    )
                )
                .mappings()
                .one()
            )
        return dict(row)

    @staticmethod
    def approved(row: dict) -> bool:
        return bool(
            row.get("desired_version") == row.get("version")
            and row.get("status") == "completed"
            and row.get("approved")
            and row.get("report")
            and not promotion_reasons(row["report"], row["approved_against_version"])
        )

    def load(self, row: dict) -> LoadedModel:
        import joblib
        import numpy as np
        from smartfan_common.ml_pipeline import predict_target

        version = row["version"]
        if not re.fullmatch(r"mdl_[a-f0-9]{32}", version):
            raise ValueError("Invalid registry version")
        manifest = row["manifest"]
        content = manifest["content"]
        if (
            content["report"] != row["report"]
            or content["model_version"] != version
            or content["feature_version"] != FEATURE_VERSION
            or content["rul_unit"] != "calendar_hours"
        ):
            raise ValueError("Registry report differs from artifact")
        canonical = json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
        if (
            manifest["sha256"] != row["artifact_sha256"]
            or hashlib.sha256(canonical).hexdigest() != row["artifact_sha256"]
        ):
            raise ValueError("Registry manifest hash mismatch")
        path = self.root / "models" / version / "bundle.joblib"
        with path.open("rb") as stream:
            raw = stream.read(64 * 1024**2 + 1)
        if (
            len(raw) > 64 * 1024**2
            or hashlib.sha256(raw).hexdigest() != content["files"]["bundle.joblib"]
        ):
            raise ValueError("Bundle hash mismatch")
        # Only worker-owned, hashed files; no upload/path from a request is accepted.
        bundle = joblib.load(io.BytesIO(raw))
        if (
            bundle["feature_names"] != list(FEATURE_NAMES)
            or bundle["feature_version"] != FEATURE_VERSION
            or bundle["feature_config"] != asdict(FeatureConfig())
            or bundle["rul_unit"] != "calendar_hours"
            or bundle["model_version"] != version
            or set(bundle["models"]) != {"health_score", "rul_calendar_hours"}
        ):
            raise ValueError("Incompatible feature or target contract")
        low = np.asarray(bundle["drift_low"])
        high = np.asarray(bundle["drift_high"])
        if (
            low.shape != (len(FEATURE_NAMES),)
            or high.shape != low.shape
            or not np.isfinite(low).all()
            or not np.isfinite(high).all()
            or np.any(low > high)
        ):
            raise ValueError("Invalid drift reference")
        for target in ("health_score", "rul_calendar_hours"):
            prediction = predict_target(
                bundle["models"][target], np.zeros((1, len(FEATURE_NAMES))), target
            )
            if prediction.shape != (1,) or not np.isfinite(prediction).all():
                raise ValueError("Model smoke prediction failed")
        return LoadedModel(
            version, row["activation_revision"], row["artifact_sha256"], bundle
        )

    def synchronize(
        self, expected_version: str | None = None, before_swap=None
    ) -> bool:
        row = self.selection()
        with self.lock:
            previous = self.current
        if previous is not None:
            with self.store.engine.connect() as conn:
                previous_row = (
                    conn.execute(
                        text("SELECT * FROM app.models WHERE version=:version"),
                        {"version": previous.version},
                    )
                    .mappings()
                    .first()
                )
            valid = (
                previous_row is not None
                and previous_row["approved"]
                and previous_row["status"] == "completed"
                and previous_row["artifact_sha256"] == previous.sha256
                and not promotion_reasons(
                    previous_row["report"], previous_row["approved_against_version"]
                )
            )
            if (
                not valid
                or row["active_version"] != previous.version
                or row["active_revision"] != previous.revision
            ):
                with self.lock:
                    self.current = None
                    self.synchronized = True
                if not valid:
                    with self.store.transaction() as conn:
                        conn.execute(
                            text(
                                "UPDATE app.model_selection SET active_version=NULL,updated_at=clock_timestamp() WHERE singleton AND active_version=:version AND active_revision=:revision"
                            ),
                            {
                                "version": previous.version,
                                "revision": previous.revision,
                            },
                        )
        if not self.approved(row) or (
            expected_version is not None
            and expected_version != row.get("desired_version")
        ):
            self.last_error = "no_approved_selection"
            return False
        with self.lock:
            if (
                self.synchronized
                and self.current
                and self.current.version == row["version"]
                and self.current.revision == row["activation_revision"]
                and self.current.sha256 == row["artifact_sha256"]
            ):
                return False
        try:
            candidate = self.load(row)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            ImportError,
            AttributeError,
            EOFError,
            pickle.UnpicklingError,
            IndexError,
            zlib.error,
        ):
            self.last_error = "model_artifact_invalid"
            return False
        if before_swap:
            before_swap()  # Test hook exercises a real concurrent promotion between load and commit.
        with self.lock:
            previous = self.current
            try:
                with self.store.transaction() as conn:
                    selected = (
                        conn.execute(
                            text(
                                "SELECT * FROM app.model_selection WHERE singleton FOR UPDATE"
                            )
                        )
                        .mappings()
                        .one()
                    )
                    current_row = (
                        conn.execute(
                            text("SELECT * FROM app.models WHERE version=:version"),
                            {"version": candidate.version},
                        )
                        .mappings()
                        .one()
                    )
                    authority = {
                        **dict(current_row),
                        "desired_version": selected["desired_version"],
                    }
                    if (
                        selected["desired_version"] != candidate.version
                        or selected["activation_revision"] != candidate.revision
                        or current_row["artifact_sha256"] != candidate.sha256
                        or not self.approved(authority)
                    ):
                        self.last_error = "selection_changed"
                        return False
                    self.current = candidate
                    self.synchronized = False
                    created = (
                        conn.execute(
                            text(
                                "INSERT INTO app.model_activations(revision,version,artifact_sha256) VALUES(:revision,:version,:hash) ON CONFLICT(revision) DO NOTHING"
                            ),
                            {
                                "revision": candidate.revision,
                                "version": candidate.version,
                                "hash": candidate.sha256,
                            },
                        ).rowcount
                        == 1
                    )
                    activation = conn.execute(
                        text(
                            "SELECT version,artifact_sha256,activated_at FROM app.model_activations WHERE revision=:revision"
                        ),
                        {"revision": candidate.revision},
                    ).one()
                    if (
                        activation[0] != candidate.version
                        or activation[1] != candidate.sha256
                    ):
                        raise ValueError("Activation revision conflict")
                    event = ModelActivatedV2.model_validate(
                        {
                            "id": str(
                                uuid5(
                                    NAMESPACE_URL,
                                    f"smartfan:model-activated:{candidate.version}:{candidate.revision}",
                                )
                            ),
                            "schema_version": "2.1",
                            "timestamp": activation[2]
                            .isoformat()
                            .replace("+00:00", "Z"),
                            "tipo": "model.activated",
                            "dispositivo": None,
                            "correlation_id": None,
                            "metadata": {"producer": "inference", "causation_id": None},
                            "conteudo": {
                                "model_version": candidate.version,
                                "feature_version": FEATURE_VERSION,
                                "dataset_id": current_row["report"]["dataset_id"],
                                "sha256": candidate.sha256,
                            },
                        }
                    )
                    exchange, route = routing_key_v2(event)
                    self.store.enqueue(
                        Outbound(event.id, serialize_event_v2(event), exchange, route),
                        connection=conn,
                    )
                    conn.execute(
                        text(
                            "INSERT INTO app.audit(id,actor_user_id,action,entity_type,entity_id,correlation_id,details,outcome,created_at) SELECT :id,NULL,'model.activated','model',:version,:correlation,CAST(:details AS jsonb),'success',:at WHERE :created"
                        ),
                        {
                            "id": event.id,
                            "created": created,
                            "version": candidate.version,
                            "correlation": event.id,
                            "details": json.dumps(
                                {
                                    "activation_revision": candidate.revision,
                                    "artifact_sha256": candidate.sha256,
                                }
                            ),
                            "at": activation[2],
                        },
                    )
                    conn.execute(
                        text(
                            "UPDATE app.model_selection SET active_version=:version,active_revision=:revision,updated_at=:at WHERE singleton"
                        ),
                        {
                            "version": candidate.version,
                            "revision": candidate.revision,
                            "at": activation[2],
                        },
                    )
                self.synchronized = True
                self.last_error = None
                return True
            except BaseException:
                # Even an unknown COMMIT outcome cannot let an unconfirmed pointer predict.
                self.current = previous
                self.synchronized = False
                raise
