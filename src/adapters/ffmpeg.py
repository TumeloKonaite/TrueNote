from __future__ import annotations

from os import PathLike
from pathlib import Path
from typing import Protocol


type StrPath = str | PathLike[str]


def _path_str(value: StrPath) -> str:
    return str(Path(value))


def _require_positive_int(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


def build_ffmpeg_normalize_cmd(
    input_path: StrPath,
    output_path: StrPath,
    sample_rate: int = 16000,
    channels: int = 1,
) -> list[str]:
    """Build a deterministic ffmpeg command for PCM WAV normalization."""
    _require_positive_int("sample_rate", sample_rate)
    _require_positive_int("channels", channels)

    return [
        "ffmpeg",
        "-y",
        "-i",
        _path_str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        _path_str(output_path),
    ]


def build_ffmpeg_chunk_cmd(
    input_audio: StrPath,
    chunks_dir: StrPath,
    chunk_seconds: int,
) -> list[str]:
    """Build a deterministic ffmpeg segmenting command for chunked WAV output."""
    _require_positive_int("chunk_seconds", chunk_seconds)
    chunk_pattern = Path(chunks_dir) / "chunk_%04d.wav"

    return [
        "ffmpeg",
        "-y",
        "-i",
        _path_str(input_audio),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-reset_timestamps",
        "1",
        "-map",
        "0:a:0",
        "-c",
        "copy",
        str(chunk_pattern),
    ]


class FfmpegAdapter(Protocol):
    def chunk_audio(self, input_audio: StrPath, chunks_dir: StrPath, chunk_seconds: int) -> None:
        """Split normalized audio into chunked WAV files."""


__all__ = [
    "FfmpegAdapter",
    "build_ffmpeg_normalize_cmd",
    "build_ffmpeg_chunk_cmd",
]
