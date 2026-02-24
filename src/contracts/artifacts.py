from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AudioArtifact:
    path: Path
    sha256: str
    duration_s: float | None = None
    sample_rate: int | None = None
    channels: int | None = None


@dataclass(frozen=True, slots=True)
class ChunksArtifact:
    dir: Path
    chunk_paths: list[Path]
    chunk_seconds: int
    count: int


@dataclass(frozen=True, slots=True)
class TranscriptArtifact:
    text: str
    provider: str
    model: str
    chunk_count: int
    language: str | None = None
    timings: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MinutesArtifact:
    markdown: str
    model: str
    prompt_version: str
    tokens: dict[str, Any] | None = None
