from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.contracts.manifest import Manifest


@dataclass(frozen=True, slots=True)
class PipelinePaths:
    run_dir: Path
    manifest_path: Path
    normalized_audio_path: Path
    chunks_dir: Path
    transcript_path: Path
    transcript_segments_path: Path
    minutes_md_path: Path
    minutes_docx_path: Path


def build_pipeline_paths(
    run_dir: Path,
    *,
    manifest_filename: str = "manifest.json",
    normalized_audio_filename: str = "normalized.wav",
    chunks_dirname: str = "chunks",
    transcript_filename: str = "transcript.txt",
    transcript_segments_filename: str = "transcript_segments.json",
    minutes_filename: str = "minutes.md",
    minutes_docx_filename: str = "minutes.docx",
) -> PipelinePaths:
    run_dir = Path(run_dir)
    return PipelinePaths(
        run_dir=run_dir,
        manifest_path=run_dir / manifest_filename,
        normalized_audio_path=run_dir / normalized_audio_filename,
        chunks_dir=run_dir / chunks_dirname,
        transcript_path=run_dir / transcript_filename,
        transcript_segments_path=run_dir / transcript_segments_filename,
        minutes_md_path=run_dir / minutes_filename,
        minutes_docx_path=run_dir / minutes_docx_filename,
    )


def manifest_path_ref(path: Path, *, base_dir: Path) -> str:
    path = Path(path)
    base_dir = Path(base_dir)
    try:
        return path.relative_to(base_dir).as_posix()
    except ValueError:
        return str(path)


def write_text_file(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    _atomic_write_bytes(path, text.encode(encoding))


def write_json_file(path: Path, data: Any) -> None:
    payload = json.dumps(data, indent=2, sort_keys=True, default=str).encode("utf-8")
    _atomic_write_bytes(path, payload)


def persist_manifest(manifest: Manifest, path: Path) -> None:
    manifest.touch()
    write_json_file(path, manifest.to_dict())


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(payload)
            tmp_file.flush()
            try:
                os.fsync(tmp_file.fileno())
            except OSError:
                # Best-effort durability; some environments/sandboxes may not support fsync.
                pass
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


__all__ = [
    "PipelinePaths",
    "build_pipeline_paths",
    "manifest_path_ref",
    "persist_manifest",
    "write_json_file",
    "write_text_file",
]
