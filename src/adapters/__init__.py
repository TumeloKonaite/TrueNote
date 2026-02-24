from __future__ import annotations

from .ffmpeg import FfmpegAdapter, build_ffmpeg_chunk_cmd, build_ffmpeg_normalize_cmd
from .openai_transcription import OpenAIClientLike, OpenAITranscriptionAdapter
from .pandoc import PandocAdapter, build_pandoc_markdown_to_docx_cmd, resolve_pandoc_executable
from .transcription import TranscriptionProvider

__all__ = [
    "FfmpegAdapter",
    "build_ffmpeg_normalize_cmd",
    "build_ffmpeg_chunk_cmd",
    "PandocAdapter",
    "build_pandoc_markdown_to_docx_cmd",
    "resolve_pandoc_executable",
    "TranscriptionProvider",
    "OpenAIClientLike",
    "OpenAITranscriptionAdapter",
]
