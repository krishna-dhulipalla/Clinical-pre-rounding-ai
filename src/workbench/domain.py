from datetime import datetime, timezone
from enum import Enum
from typing import Any
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class CoverageState(str, Enum):
    available = "available"
    empty = "empty"
    unavailable = "unavailable"
    access_denied = "access_denied"
    not_queried = "not_queried"


class Coverage(BaseModel):
    resource_type: str
    state: CoverageState
    count: int = 0
    reason: str = ""
    excluded: int = 0
    unknown_dates: int = 0
    stale_count: int = 0


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9.-]+$")
    encounter_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9.-]+$")
    window_start: datetime
    since: datetime
    as_of: datetime
    scenario: str = Field(default="normal", pattern="^(normal|outage|denied)$")

    @field_validator("window_start", "since", "as_of")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Explicit timezone is required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def valid_window(self):
        if not self.window_start <= self.since < self.as_of:
            raise ValueError("Require window_start <= since < as_of")
        if (self.as_of - self.window_start).total_seconds() > 7 * 86400:
            raise ValueError("Review windows are limited to seven days")
        return self


class EvidenceFact(BaseModel):
    evidence_id: str
    resource_key: str
    version: str
    path: str
    kind: str
    code_system: str = ""
    code: str = ""
    name: str
    value: str
    numeric_value: str | None = None
    comparator: str | None = None
    unit: str | None = None
    unit_system: str | None = None
    timestamp: datetime | None = None
    date_precision: str = "unknown"
    status: str = ""
    stale: bool = False
    resource_hash: str


class Change(BaseModel):
    id: str
    name: str
    previous_id: str
    current_id: str
    previous_value: str
    current_value: str
    delta: str
    unit: str
    direction: str


class Claim(BaseModel):
    id: str
    kind: str
    text: str
    evidence_ids: list[str]
    validation: str = "template_verified"


class Snapshot(BaseModel):
    schema_version: str = "2.0"
    source_base: str = "urn:demo"
    patient_id: str
    encounter_id: str
    window_start: datetime
    since: datetime
    as_of: datetime
    manifest: list[Coverage]
    facts: list[EvidenceFact]
    resources: dict[str, dict]
    changes: list[Change] = []
    claims: list[Claim] = []
    warnings: list[str] = []
    complete: bool = False
    snapshot_hash: str = ""
    engine: str = "evidence-rules-v2"
    prompt_version: str = "rank-claims-v1"
    telemetry: dict = {}


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    selected_claim_ids: list[str] = Field(max_length=200)
    note: str = Field(default="", max_length=5000)
    accept: bool = False
