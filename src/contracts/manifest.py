from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .errors import ContractError
from src.utils.time import now_unix_s

StepStatus = Literal["pending", "skipped", "success", "failed"]


@dataclass(slots=True)
class StepRecord:
    name: str
    status: StepStatus = "pending"
    started_at_s: float | None = None
    ended_at_s: float | None = None
    duration_ms: int | None = None
    attempts: int = 0
    meta: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | dict[str, Any] | None = None
    error_type: str | None = None

    def start(self, *, at_s: float | None = None) -> None:
        self.started_at_s = now_unix_s() if at_s is None else at_s
        self.status = "pending"
        self.attempts += 1

    def finish(
        self,
        *,
        status: StepStatus,
        at_s: float | None = None,
        error: str | dict[str, Any] | None = None,
        error_type: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.ended_at_s = now_unix_s() if at_s is None else at_s
        self.status = status
        self.error = error
        self.error_type = error_type
        if meta:
            self.meta.update(meta)
        self.duration_ms = self.compute_duration_ms()

    def compute_duration_ms(self) -> int | None:
        if self.started_at_s is None or self.ended_at_s is None:
            return None
        return max(0, int(round((self.ended_at_s - self.started_at_s) * 1000)))


@dataclass(slots=True)
class ArtifactRefs:
    """
    Persistable references to produced artifacts.
    Keep these as paths/strings/metadata, not large blobs.
    """

    input_path: str | None = None
    input_sha256: str | None = None

    normalized_audio_path: str | None = None
    normalized_audio_sha256: str | None = None

    chunks_dir: str | None = None
    chunk_paths: list[str] = field(default_factory=list)
    chunk_seconds: int | None = None

    transcript_path: str | None = None
    transcript_sha256: str | None = None
    transcript_text: str | None = None
    transcript_provider: str | None = None
    transcript_model: str | None = None
    transcript_language: str | None = None
    transcript_chunk_count: int | None = None
    transcript_duration_s: float | None = None
    transcript_segments_path: str | None = None
    transcript_segments_count: int | None = None

    minutes_md_path: str | None = None
    minutes_sha256: str | None = None
    minutes_docx_path: str | None = None
    minutes_docx_sha256: str | None = None
    minutes_markdown: str | None = None
    minutes_model: str | None = None
    minutes_prompt_version: str | None = None
    minutes_prompt_path: str | None = None
    minutes_prompt_hash: str | None = None


@dataclass(slots=True)
class Manifest:
    """
    Persistable workflow manifest and resume contract.
    """

    version: str = "1"
    run_id: str | None = None
    created_at_s: float | None = None
    updated_at_s: float | None = None
    input_sha256: str | None = None
    artifacts: ArtifactRefs = field(default_factory=ArtifactRefs)
    steps: dict[str, StepRecord] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def ensure_step(self, name: str) -> StepRecord:
        if name not in self.steps:
            self.steps[name] = StepRecord(name=name)
        return self.steps[name]

    def touch(self, *, at_s: float | None = None) -> None:
        ts = now_unix_s() if at_s is None else at_s
        if self.created_at_s is None:
            self.created_at_s = ts
        self.updated_at_s = ts

    def validate_artifact_refs(
        self,
        *,
        required: list[str] | None = None,
        optional: list[str] | None = None,
    ) -> None:
        required = required or []
        optional = optional or []
        for attr in required + optional:
            if not hasattr(self.artifacts, attr):
                raise ContractError(f"Unknown artifact ref '{attr}'")
        for attr in required:
            value = getattr(self.artifacts, attr)
            if value in (None, "", [], {}):
                raise ContractError(f"Missing required artifact ref '{attr}'")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Manifest":
        try:
            artifacts = ArtifactRefs(**(data.get("artifacts") or {}))
            steps_raw = data.get("steps") or {}
            steps: dict[str, StepRecord] = {}
            for step_name, step_data in steps_raw.items():
                if "name" not in step_data:
                    step_data = {"name": step_name, **step_data}
                step = StepRecord(**step_data)
                step.duration_ms = step.compute_duration_ms() if step.duration_ms is None else step.duration_ms
                steps[step_name] = step

            manifest = cls(
                version=str(data.get("version", "1")),
                run_id=data.get("run_id"),
                created_at_s=data.get("created_at_s"),
                updated_at_s=data.get("updated_at_s"),
                input_sha256=data.get("input_sha256"),
                artifacts=artifacts,
                steps=steps,
                warnings=list(data.get("warnings") or []),
                errors=list(data.get("errors") or []),
            )
            return manifest
        except TypeError as exc:
            raise ContractError(f"Invalid manifest shape: {exc}") from exc

    def write_json(self, path: Path) -> None:
        self.touch()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def read_json(cls, path: Path) -> "Manifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def load_json(cls, path: Path) -> "Manifest":
        return cls.read_json(path)


def should_skip_step(
    manifest: Manifest,
    step_name: str,
    *,
    require_artifact_paths: list[str] | None = None,
    expected_inputs_hashes: dict[str, str] | None = None,
) -> bool:
    """
    Idempotency helper:
    - Step must be marked success
    - Required artifact refs must be present
    - If expected hashes are provided, they must match manifest hashes
    """
    rec = manifest.steps.get(step_name)
    if not rec or rec.status != "success":
        return False

    if expected_inputs_hashes:
        for key, expected in expected_inputs_hashes.items():
            if key == "input_sha256":
                actual = manifest.input_sha256 or manifest.artifacts.input_sha256
            elif hasattr(manifest.artifacts, key):
                actual = getattr(manifest.artifacts, key)
            else:
                raise ContractError(f"Unknown hash field '{key}' required by {step_name}")
            if actual != expected:
                return False

    if not require_artifact_paths:
        return True

    for attr in require_artifact_paths:
        if not hasattr(manifest.artifacts, attr):
            raise ContractError(f"Unknown artifact ref '{attr}' required by {step_name}")
        if getattr(manifest.artifacts, attr) in (None, "", [], {}):
            return False

    return True
