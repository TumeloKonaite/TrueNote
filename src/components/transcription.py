from __future__ import annotations

from src.adapters.transcription import TranscriptionProvider
from src.contracts.artifacts import ChunksArtifact, TranscriptArtifact
from src.contracts.errors import InputValidationError, TranscriptionError


def _validate_chunks(chunks: ChunksArtifact) -> None:
    if chunks.count != len(chunks.chunk_paths):
        raise InputValidationError("chunks.count must match len(chunks.chunk_paths)")
    if chunks.count == 0:
        raise InputValidationError("at least one chunk is required for transcription")
    for path in chunks.chunk_paths:
        if not path.exists():
            raise InputValidationError(f"chunk not found: {path}")
        if not path.is_file():
            raise InputValidationError(f"chunk is not a file: {path}")


def transcribe_chunks(chunks: ChunksArtifact, provider: TranscriptionProvider) -> TranscriptArtifact:
    """
    Provider-agnostic transcription component.
    Adapters own provider retries/response normalization/chunk stitching.
    """
    _validate_chunks(chunks)
    transcript = provider.transcribe(chunks)
    if transcript.chunk_count != chunks.count:
        raise TranscriptionError(
            f"provider returned chunk_count={transcript.chunk_count}, expected {chunks.count}"
        )
    return transcript


__all__ = ["transcribe_chunks"]
