from __future__ import annotations

from pathlib import Path
import re

from src.adapters.ffmpeg import FfmpegAdapter
from src.contracts.artifacts import AudioArtifact, ChunksArtifact
from src.contracts.errors import ChunkingError, InputValidationError


_CHUNK_NAME_RE = re.compile(r"^chunk_(\d{4})\.wav$")


def _validate_chunk_seconds(chunk_seconds: int) -> None:
    if chunk_seconds <= 0:
        raise InputValidationError("chunk_seconds must be > 0")


def _validate_input_audio(normalized_audio: AudioArtifact) -> None:
    if not normalized_audio.path.exists():
        raise InputValidationError(f"normalized audio not found: {normalized_audio.path}")
    if not normalized_audio.path.is_file():
        raise InputValidationError(f"normalized audio is not a file: {normalized_audio.path}")


def _prepare_out_dir(out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ChunkingError(f"chunk output directory must be empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _collect_chunk_paths(out_dir: Path) -> list[Path]:
    chunk_paths = sorted(path for path in out_dir.iterdir() if path.is_file())
    if not chunk_paths:
        raise ChunkingError(f"ffmpeg produced no chunk files in {out_dir}")

    indices: list[int] = []
    for path in chunk_paths:
        match = _CHUNK_NAME_RE.fullmatch(path.name)
        if match is None:
            raise ChunkingError(f"unexpected chunk filename: {path.name}")
        indices.append(int(match.group(1)))

    expected_indices = list(range(len(indices)))
    if indices != expected_indices:
        raise ChunkingError(
            f"chunk filenames must be contiguous and zero-based in {out_dir}"
        )
    return chunk_paths


def chunk_audio(
    normalized_audio: AudioArtifact,
    chunk_seconds: int,
    out_dir: Path,
    ffmpeg: FfmpegAdapter,
) -> ChunksArtifact:
    _validate_chunk_seconds(chunk_seconds)
    _validate_input_audio(normalized_audio)
    out_dir = _prepare_out_dir(out_dir)

    ffmpeg.chunk_audio(normalized_audio.path, out_dir, chunk_seconds)
    chunk_paths = _collect_chunk_paths(out_dir)

    return ChunksArtifact(
        dir=out_dir,
        chunk_paths=chunk_paths,
        chunk_seconds=chunk_seconds,
        count=len(chunk_paths),
    )


__all__ = ["chunk_audio"]
