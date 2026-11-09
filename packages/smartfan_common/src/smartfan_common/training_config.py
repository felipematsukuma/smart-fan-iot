"""Training inputs and trusted immutable worker task references."""

from typing import Annotated

from pydantic import Field, model_validator

from .contracts import UUIDString, WireModel
from .contracts_v2 import Digest
from .lab_config import LabConfig

ModelVersion = Annotated[str, Field(pattern=r"^mdl_[a-f0-9]{32}$")]
TRAINING_FAILURE_REASONS = frozenset(
    {
        "insufficient_equipment_groups",
        "insufficient_observed_failures",
        "health_score_insufficient_variation",
        "rul_calendar_hours_insufficient_variation",
        "training_data_or_artifact_invalid",
    }
)


class TrainingRequest(WireModel):
    dataset_id: UUIDString
    seed: Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)] = 42
    benchmark_seed: Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)] = 31415
    max_feature_rows: Annotated[int, Field(strict=True, ge=1000, le=200000)] = 100000
    benchmark_feature_rows: Annotated[int, Field(strict=True, ge=1000, le=50000)] = 30000
    importance_rows: Annotated[int, Field(strict=True, ge=100, le=2000)] = 1000


class TrainingTask(WireModel):
    request: TrainingRequest
    model_version: ModelVersion
    dataset_sha256: Digest
    source_config: LabConfig
    active_model_version: ModelVersion | None = None
    active_bundle_sha256: Digest | None = None

    @model_validator(mode="after")
    def independent_benchmark_and_reference(self) -> "TrainingTask":
        if self.request.benchmark_seed == self.source_config.seed:
            raise ValueError("Benchmark must use an independent seed")
        if (self.active_model_version is None) != (self.active_bundle_sha256 is None):
            raise ValueError("Active version and hash must be paired")
        return self

    @property
    def total(self) -> int:
        return 100

    @property
    def estimated_bytes(self) -> int:
        return (
            self.source_config.estimated_bytes
            + self.request.max_feature_rows * 18 * 16
            + 64 * 1024**2
        )
