from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.adapters.transcription import TranscriptionProvider
from src.contracts.artifacts import ChunksArtifact, TranscriptArtifact, TranscriptSegment
from src.contracts.errors import ProviderResponseError, ProviderRetryExhaustedError


class _OpenAITranscriptionsAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class _OpenAIAudioAPI(Protocol):
    transcriptions: _OpenAITranscriptionsAPI


class OpenAIClientLike(Protocol):
    audio: _OpenAIAudioAPI


@dataclass(frozen=True, slots=True)
class _NormalizedChunkTranscript:
    text: str
    language: str | None
    duration_s: float | None
    segments: list[TranscriptSegment]


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    if hasattr(obj, name):
        return getattr(obj, name)
    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped.get(name, default)
    return default


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_segments(raw_segments: Any) -> list[TranscriptSegment]:
    if raw_segments in (None, ""):
        return []
    if not isinstance(raw_segments, list):
        raise ProviderResponseError("OpenAI transcription 'segments' must be a list when provided")

    segments: list[TranscriptSegment] = []
    for idx, raw in enumerate(raw_segments):
        text = _coerce_text(_field(raw, "text"))
        start_s = _float_or_none(_field(raw, "start"))
        end_s = _float_or_none(_field(raw, "end"))
        if not text and start_s is None and end_s is None:
            continue
        segments.append(
            TranscriptSegment(
                index=idx,
                text=text,
                start_s=start_s,
                end_s=end_s,
            )
        )
    return segments


class OpenAITranscriptionAdapter(TranscriptionProvider):
    """OpenAI-only provider adapter that normalizes responses into TranscriptArtifact."""

    def __init__(
        self,
        client: OpenAIClientLike,
        *,
        model: str,
        language: str | None = None,
        prompt: str | None = None,
        max_retries_per_chunk: int = 2,
        include_segment_timestamps: bool = True,
    ) -> None:
        if not model:
            raise ValueError("model is required")
        if max_retries_per_chunk < 0:
            raise ValueError("max_retries_per_chunk must be >= 0")
        self._client = client
        self._model = model
        self._language = language
        self._prompt = prompt
        self._max_retries_per_chunk = max_retries_per_chunk
        self._include_segment_timestamps = include_segment_timestamps

    def transcribe(self, chunks: ChunksArtifact) -> TranscriptArtifact:
        if chunks.count != len(chunks.chunk_paths):
            raise ProviderResponseError("ChunksArtifact count does not match chunk_paths length")

        stitched_text_parts: list[str] = []
        stitched_segments: list[TranscriptSegment] = []
        selected_language = self._language
        sum_chunk_durations = 0.0
        has_any_duration = False
        global_segment_index = 0

        for chunk_index, chunk_path in enumerate(chunks.chunk_paths):
            normalized = self._transcribe_chunk_with_retry(chunk_path)
            if not selected_language and normalized.language:
                selected_language = normalized.language

            if normalized.text:
                stitched_text_parts.append(normalized.text)

            if normalized.duration_s is not None:
                sum_chunk_durations += normalized.duration_s
                has_any_duration = True

            offset_s = float(chunk_index * chunks.chunk_seconds)
            if normalized.segments:
                for seg in normalized.segments:
                    stitched_segments.append(
                        TranscriptSegment(
                            index=global_segment_index,
                            text=seg.text,
                            start_s=(seg.start_s + offset_s) if seg.start_s is not None else None,
                            end_s=(seg.end_s + offset_s) if seg.end_s is not None else None,
                            chunk_index=chunk_index,
                        )
                    )
                    global_segment_index += 1
            elif normalized.text:
                stitched_segments.append(
                    TranscriptSegment(
                        index=global_segment_index,
                        text=normalized.text,
                        chunk_index=chunk_index,
                    )
                )
                global_segment_index += 1

        full_text = "\n".join(part for part in stitched_text_parts if part).strip()
        if not full_text:
            raise ProviderResponseError("OpenAI adapter produced an empty transcript")

        timestamped_segments = [
            seg for seg in stitched_segments if seg.start_s is not None or seg.end_s is not None
        ]
        timeline_start_s = (
            min(seg.start_s for seg in timestamped_segments if seg.start_s is not None)
            if any(seg.start_s is not None for seg in timestamped_segments)
            else None
        )
        timeline_end_s = (
            max(seg.end_s for seg in timestamped_segments if seg.end_s is not None)
            if any(seg.end_s is not None for seg in timestamped_segments)
            else None
        )

        duration_s: float | None = None
        if timeline_start_s is not None and timeline_end_s is not None:
            duration_s = max(0.0, timeline_end_s - timeline_start_s)
        elif has_any_duration:
            duration_s = sum_chunk_durations

        timings = {
            "segments_count": len(stitched_segments),
            "timestamped_segments_count": len(timestamped_segments),
            "timeline_start_s": timeline_start_s,
            "timeline_end_s": timeline_end_s,
        }

        return TranscriptArtifact(
            text=full_text,
            provider="openai",
            model=self._model,
            chunk_count=chunks.count,
            language=selected_language,
            segments=stitched_segments or None,
            duration_s=duration_s,
            timings=timings,
            meta={"chunk_seconds": chunks.chunk_seconds},
        )

    def _transcribe_chunk_with_retry(self, chunk_path: Path) -> _NormalizedChunkTranscript:
        last_error: Exception | None = None
        attempts = self._max_retries_per_chunk + 1
        for attempt in range(1, attempts + 1):
            try:
                return self._transcribe_chunk(chunk_path)
            except Exception as exc:  # pragma: no cover - exact provider exceptions vary
                last_error = exc
                if attempt >= attempts:
                    break
        message = f"OpenAI transcription failed for chunk {chunk_path} after {attempts} attempts"
        raise ProviderRetryExhaustedError(message) from last_error

    def _transcribe_chunk(self, chunk_path: Path) -> _NormalizedChunkTranscript:
        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "response_format": "verbose_json",
        }
        if self._language:
            request_kwargs["language"] = self._language
        if self._prompt:
            request_kwargs["prompt"] = self._prompt
        if self._include_segment_timestamps:
            request_kwargs["timestamp_granularities"] = ["segment"]

        with Path(chunk_path).open("rb") as fh:
            response = self._client.audio.transcriptions.create(file=fh, **request_kwargs)

        text = _coerce_text(_field(response, "text"))
        segments = _normalize_segments(_field(response, "segments"))
        if not text and segments:
            text = " ".join(seg.text for seg in segments if seg.text).strip()
        if not text:
            raise ProviderResponseError("OpenAI transcription response missing text")

        return _NormalizedChunkTranscript(
            text=text,
            language=_coerce_text(_field(response, "language")) or None,
            duration_s=_float_or_none(_field(response, "duration")),
            segments=segments,
        )


__all__ = ["OpenAIClientLike", "OpenAITranscriptionAdapter"]
