from __future__ import annotations

from typing import Protocol

from src.contracts.artifacts import ChunksArtifact, TranscriptArtifact


class TranscriptionProvider(Protocol):
    """Provider adapter boundary for chunked transcription."""

    def transcribe(self, chunks: ChunksArtifact) -> TranscriptArtifact:
        """Return a normalized transcript artifact for the given chunks."""


__all__ = ["TranscriptionProvider"]
