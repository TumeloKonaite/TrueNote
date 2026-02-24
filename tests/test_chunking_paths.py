from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.components.chunking import chunk_audio
from src.contracts.artifacts import AudioArtifact
from src.contracts.errors import ChunkingError, InputValidationError


class _FakeFfmpeg:
    def __init__(self, files_to_write: list[str]) -> None:
        self.files_to_write = files_to_write
        self.calls: list[tuple[Path, Path, int]] = []

    def chunk_audio(self, input_audio: str | Path, chunks_dir: str | Path, chunk_seconds: int) -> None:
        input_path = Path(input_audio)
        out_dir = Path(chunks_dir)
        self.calls.append((input_path, out_dir, chunk_seconds))
        for name in self.files_to_write:
            (out_dir / name).write_bytes(b"wav")


class ChunkAudioPathTests(unittest.TestCase):
    def test_returns_sorted_chunk_paths_and_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized = root / "normalized.wav"
            normalized.write_bytes(b"wav")
            out_dir = root / "chunks"
            ffmpeg = _FakeFfmpeg(["chunk_0002.wav", "chunk_0000.wav", "chunk_0001.wav"])

            artifact = chunk_audio(
                normalized_audio=AudioArtifact(path=normalized, sha256="0" * 64),
                chunk_seconds=30,
                out_dir=out_dir,
                ffmpeg=ffmpeg,
            )

            self.assertEqual(ffmpeg.calls, [(normalized, out_dir, 30)])
            self.assertEqual(artifact.dir, out_dir)
            self.assertEqual(artifact.chunk_seconds, 30)
            self.assertEqual(artifact.count, 3)
            self.assertEqual(
                artifact.chunk_paths,
                [
                    out_dir / "chunk_0000.wav",
                    out_dir / "chunk_0001.wav",
                    out_dir / "chunk_0002.wav",
                ],
            )

    def test_rejects_missing_normalized_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(InputValidationError):
                chunk_audio(
                    normalized_audio=AudioArtifact(path=root / "missing.wav", sha256="0" * 64),
                    chunk_seconds=30,
                    out_dir=root / "chunks",
                    ffmpeg=_FakeFfmpeg(["chunk_0000.wav"]),
                )

    def test_rejects_non_contiguous_chunk_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized = root / "normalized.wav"
            normalized.write_bytes(b"wav")

            with self.assertRaises(ChunkingError):
                chunk_audio(
                    normalized_audio=AudioArtifact(path=normalized, sha256="0" * 64),
                    chunk_seconds=30,
                    out_dir=root / "chunks",
                    ffmpeg=_FakeFfmpeg(["chunk_0000.wav", "chunk_0002.wav"]),
                )


if __name__ == "__main__":
    unittest.main()
