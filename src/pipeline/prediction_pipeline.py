from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4
import traceback as tb

from src.adapters.ffmpeg import FfmpegAdapter
from src.adapters.transcription import TranscriptionProvider
from src.components.chunking import chunk_audio
from src.components.minutes import MinutesLLM, generate_minutes
from src.components.transcription import transcribe_chunks
from src.contracts.artifacts import AudioArtifact, ChunksArtifact, MinutesArtifact, TranscriptArtifact
from src.contracts.errors import InputValidationError, PipelineError
from src.contracts.manifest import Manifest, StepRecord
from src.pipeline.io import build_pipeline_paths, manifest_path_ref, persist_manifest, write_json_file, write_text_file
from src.utils.hashing import sha256_file


ArtifactManifest = Manifest


class AudioNormalizer(Protocol):
    def normalize_audio(self, input_path: Path, output_path: Path) -> AudioArtifact:
        """Return a normalized audio artifact written at output_path (or equivalent)."""


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    output_dir: Path
    normalizer: AudioNormalizer
    ffmpeg: FfmpegAdapter
    transcription_provider: TranscriptionProvider
    minutes_llm: MinutesLLM
    chunk_seconds: int
    prompt_path: Path | None = None
    prompt_version: str | None = None
    minutes_extra_context: dict[str, str] | None = None
    include_error_traceback: bool = False
    run_id: str | None = None


def run(input_path: Path, config: PipelineConfig) -> ArtifactManifest:
    input_path = Path(input_path)
    paths = build_pipeline_paths(config.output_dir)
    manifest = Manifest(run_id=config.run_id or uuid4().hex)

    normalized_audio: AudioArtifact | None = None
    chunks: ChunksArtifact | None = None
    transcript: TranscriptArtifact | None = None
    minutes: MinutesArtifact | None = None

    def fail_step(step: StepRecord, exc: Exception, *, step_context: dict[str, Any] | None = None) -> None:
        error_context = {
            "step": step.name,
            "input_path": str(input_path),
            "run_dir": str(paths.run_dir),
            "step_context": _json_safe(step_context or {}),
        }
        error_payload: dict[str, Any] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "context": error_context,
        }
        if config.include_error_traceback:
            error_payload["traceback"] = "".join(tb.format_exception(type(exc), exc, exc.__traceback__))

        step.finish(
            status="failed",
            error=error_payload,
            error_type=type(exc).__name__,
            meta={"context": _json_safe(step_context or {})},
        )
        manifest.errors.append(f"{step.name}: {type(exc).__name__}: {exc}")
        persist_manifest(manifest, paths.manifest_path)

        if isinstance(exc, PipelineError):
            raise exc
        raise PipelineError(f"pipeline failed at step '{step.name}': {exc}") from exc

    def complete_step(step: StepRecord, *, step_context: dict[str, Any] | None = None, artifacts: dict[str, Any] | None = None) -> None:
        meta: dict[str, Any] = {}
        if step_context:
            meta["context"] = _json_safe(step_context)
        if artifacts:
            meta["artifacts"] = _json_safe(artifacts)
        step.finish(status="success", meta=meta or None)
        persist_manifest(manifest, paths.manifest_path)

    def start_step(name: str, *, step_context: dict[str, Any] | None = None) -> StepRecord:
        step = manifest.ensure_step(name)
        step.start()
        if step_context:
            step.meta["context"] = _json_safe(step_context)
        return step

    # 1. validate
    validate_context = {"output_dir": str(paths.run_dir)}
    step = start_step("validate", step_context=validate_context)
    try:
        if not input_path.exists():
            raise InputValidationError(f"input not found: {input_path}")
        if not input_path.is_file():
            raise InputValidationError(f"input is not a file: {input_path}")
        if paths.run_dir.exists() and not paths.run_dir.is_dir():
            raise InputValidationError(f"output_dir is not a directory: {paths.run_dir}")

        paths.run_dir.mkdir(parents=True, exist_ok=True)
        manifest.artifacts.input_path = str(input_path)
        manifest.input_sha256 = sha256_file(input_path)
        manifest.artifacts.input_sha256 = manifest.input_sha256

        complete_step(
            step,
            step_context=validate_context,
            artifacts={
                "input_path": manifest.artifacts.input_path,
                "input_sha256": manifest.artifacts.input_sha256,
            },
        )
    except Exception as exc:
        fail_step(step, exc, step_context=validate_context)

    # 2. normalize
    normalize_context = {
        "normalizer": type(config.normalizer).__name__,
        "output_path": str(paths.normalized_audio_path),
    }
    step = start_step("normalize", step_context=normalize_context)
    try:
        normalized_audio = config.normalizer.normalize_audio(input_path, paths.normalized_audio_path)
        manifest.artifacts.normalized_audio_path = manifest_path_ref(normalized_audio.path, base_dir=paths.run_dir)
        manifest.artifacts.normalized_audio_sha256 = normalized_audio.sha256

        complete_step(
            step,
            step_context=normalize_context,
            artifacts={
                "normalized_audio_path": manifest.artifacts.normalized_audio_path,
                "normalized_audio_sha256": manifest.artifacts.normalized_audio_sha256,
            },
        )
    except Exception as exc:
        fail_step(step, exc, step_context=normalize_context)

    # 3. chunk
    chunk_context = {
        "chunk_seconds": config.chunk_seconds,
        "ffmpeg_adapter": type(config.ffmpeg).__name__,
        "chunks_dir": str(paths.chunks_dir),
    }
    step = start_step("chunk", step_context=chunk_context)
    try:
        if normalized_audio is None:
            raise PipelineError("normalize step did not produce an audio artifact")
        chunks = chunk_audio(
            normalized_audio=normalized_audio,
            chunk_seconds=config.chunk_seconds,
            out_dir=paths.chunks_dir,
            ffmpeg=config.ffmpeg,
        )
        manifest.artifacts.chunks_dir = manifest_path_ref(chunks.dir, base_dir=paths.run_dir)
        manifest.artifacts.chunk_paths = [manifest_path_ref(path, base_dir=paths.run_dir) for path in chunks.chunk_paths]
        manifest.artifacts.chunk_seconds = chunks.chunk_seconds

        complete_step(
            step,
            step_context=chunk_context,
            artifacts={
                "chunks_dir": manifest.artifacts.chunks_dir,
                "chunk_paths": manifest.artifacts.chunk_paths,
                "chunk_seconds": manifest.artifacts.chunk_seconds,
            },
        )
    except Exception as exc:
        fail_step(step, exc, step_context=chunk_context)

    # 4. transcribe
    transcribe_context = {
        "provider": type(config.transcription_provider).__name__,
        "chunk_count": chunks.count if chunks is not None else None,
    }
    step = start_step("transcribe", step_context=transcribe_context)
    try:
        if chunks is None:
            raise PipelineError("chunk step did not produce chunk artifacts")
        transcript = transcribe_chunks(chunks, config.transcription_provider)
        manifest.artifacts.transcript_text = transcript.text
        manifest.artifacts.transcript_provider = transcript.provider
        manifest.artifacts.transcript_model = transcript.model
        manifest.artifacts.transcript_language = transcript.language
        manifest.artifacts.transcript_chunk_count = transcript.chunk_count
        manifest.artifacts.transcript_duration_s = transcript.duration_s

        complete_step(
            step,
            step_context=transcribe_context,
            artifacts={
                "transcript_provider": manifest.artifacts.transcript_provider,
                "transcript_model": manifest.artifacts.transcript_model,
                "transcript_chunk_count": manifest.artifacts.transcript_chunk_count,
            },
        )
    except Exception as exc:
        fail_step(step, exc, step_context=transcribe_context)

    # 5. generate
    generate_context = {
        "llm": type(config.minutes_llm).__name__,
        "prompt_path": str(config.prompt_path) if config.prompt_path is not None else None,
        "prompt_version": config.prompt_version,
    }
    step = start_step("generate", step_context=generate_context)
    try:
        if transcript is None:
            raise PipelineError("transcribe step did not produce a transcript artifact")
        generate_kwargs: dict[str, Any] = {
            "llm": config.minutes_llm,
            "prompt_version": config.prompt_version,
            "extra_context": config.minutes_extra_context,
        }
        if config.prompt_path is not None:
            generate_kwargs["prompt_path"] = config.prompt_path

        minutes = generate_minutes(transcript, **generate_kwargs)
        manifest.artifacts.minutes_markdown = minutes.markdown
        manifest.artifacts.minutes_model = minutes.model
        manifest.artifacts.minutes_prompt_version = minutes.prompt_version
        if minutes.meta:
            prompt_path_value = minutes.meta.get("prompt_path")
            prompt_hash_value = minutes.meta.get("prompt_hash")
            if prompt_path_value is not None:
                manifest.artifacts.minutes_prompt_path = str(prompt_path_value)
            if prompt_hash_value is not None:
                manifest.artifacts.minutes_prompt_hash = str(prompt_hash_value)

        complete_step(
            step,
            step_context=generate_context,
            artifacts={
                "minutes_model": manifest.artifacts.minutes_model,
                "minutes_prompt_version": manifest.artifacts.minutes_prompt_version,
                "minutes_prompt_path": manifest.artifacts.minutes_prompt_path,
            },
        )
    except Exception as exc:
        fail_step(step, exc, step_context=generate_context)

    # 6. write outputs
    write_context = {
        "transcript_path": str(paths.transcript_path),
        "transcript_segments_path": str(paths.transcript_segments_path),
        "minutes_md_path": str(paths.minutes_md_path),
    }
    step = start_step("write_outputs", step_context=write_context)
    try:
        if transcript is None:
            raise PipelineError("write_outputs requires a transcript artifact")
        if minutes is None:
            raise PipelineError("write_outputs requires a minutes artifact")

        write_text_file(paths.transcript_path, transcript.text.rstrip() + "\n")
        manifest.artifacts.transcript_path = manifest_path_ref(paths.transcript_path, base_dir=paths.run_dir)
        manifest.artifacts.transcript_sha256 = sha256_file(paths.transcript_path)

        if transcript.segments is not None:
            segments_payload = [asdict(segment) for segment in transcript.segments]
            write_json_file(paths.transcript_segments_path, segments_payload)
            manifest.artifacts.transcript_segments_path = manifest_path_ref(paths.transcript_segments_path, base_dir=paths.run_dir)
            manifest.artifacts.transcript_segments_count = len(transcript.segments)

        write_text_file(paths.minutes_md_path, minutes.markdown.rstrip() + "\n")
        manifest.artifacts.minutes_md_path = manifest_path_ref(paths.minutes_md_path, base_dir=paths.run_dir)
        manifest.artifacts.minutes_sha256 = sha256_file(paths.minutes_md_path)

        complete_step(
            step,
            step_context=write_context,
            artifacts={
                "transcript_path": manifest.artifacts.transcript_path,
                "transcript_sha256": manifest.artifacts.transcript_sha256,
                "minutes_md_path": manifest.artifacts.minutes_md_path,
                "minutes_sha256": manifest.artifacts.minutes_sha256,
                "transcript_segments_path": manifest.artifacts.transcript_segments_path,
            },
        )
    except Exception as exc:
        fail_step(step, exc, step_context=write_context)

    return manifest


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return repr(value)


__all__ = [
    "ArtifactManifest",
    "AudioNormalizer",
    "PipelineConfig",
    "run",
]
