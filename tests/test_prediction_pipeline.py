from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.contracts.artifacts import AudioArtifact, MinutesArtifact, TranscriptArtifact, TranscriptSegment
from src.contracts.errors import PipelineError, TranscriptionError
from src.contracts.manifest import Manifest
from src.pipeline.prediction_pipeline import PipelineConfig, run
from src.utils.hashing import sha256_file


class _FakeNormalizer:
    def normalize_audio(self, input_path: Path, output_path: Path) -> AudioArtifact:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(input_path.read_bytes())
        return AudioArtifact(path=output_path, sha256=sha256_file(output_path), duration_s=12.3, sample_rate=16000, channels=1)


class _FakeFfmpeg:
    def chunk_audio(self, input_audio: str | Path, chunks_dir: str | Path, chunk_seconds: int) -> None:
        out_dir = Path(chunks_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for i in range(2):
            (out_dir / f"chunk_{i:04d}.wav").write_bytes(f"chunk-{i}-{chunk_seconds}".encode("utf-8"))


class _ManifestAwareProvider:
    def __init__(self, manifest_path: Path, *, fail: bool = False) -> None:
        self.manifest_path = manifest_path
        self.fail = fail
        self.saw_chunk_success_in_manifest = False

    def transcribe(self, chunks) -> TranscriptArtifact:  # type: ignore[no-untyped-def]
        if self.manifest_path.exists():
            manifest = Manifest.read_json(self.manifest_path)
            chunk_step = manifest.steps.get("chunk")
            self.saw_chunk_success_in_manifest = chunk_step is not None and chunk_step.status == "success"

        if self.fail:
            raise TranscriptionError("provider misconfig")

        return TranscriptArtifact(
            text="hello world",
            provider="fake-provider",
            model="fake-transcriber",
            chunk_count=chunks.count,
            language="en",
            duration_s=12.3,
            segments=[
                TranscriptSegment(index=0, text="hello", start_s=0.0, end_s=1.0, chunk_index=0),
                TranscriptSegment(index=1, text="world", start_s=1.0, end_s=2.0, chunk_index=0),
            ],
        )


class _FakeMinutesLLM:
    def generate_minutes(self, transcript, *, prompt: str, extra_context=None) -> MinutesArtifact:  # type: ignore[no-untyped-def]
        return MinutesArtifact(
            markdown="# Minutes\n\n- hello world",
            model="fake-minutes-model",
            meta={"request_id": "req_123"},
        )


class _FakeDocxExporter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def markdown_to_docx(
        self,
        input_markdown_path: Path,
        output_docx_path: Path,
        *,
        reference_docx_path: Path | None = None,
        toc: bool = False,
        toc_depth: int = 2,
    ) -> Path:
        self.calls.append(
            {
                "input_markdown_path": input_markdown_path,
                "output_docx_path": output_docx_path,
                "reference_docx_path": reference_docx_path,
                "toc": toc,
                "toc_depth": toc_depth,
            }
        )
        output_docx_path.write_bytes(b"fake-docx")
        return output_docx_path


class PredictionPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.input_path = self.tmp_dir / "input.mp3"
        self.input_path.write_bytes(b"fake-audio")
        self.prompt_path = self.tmp_dir / "minutes_prompt.md"
        self.prompt_path.write_text("Write concise minutes in Markdown.", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _config(self, output_dir: Path, provider: _ManifestAwareProvider, *, include_error_traceback: bool = False) -> PipelineConfig:
        return PipelineConfig(
            output_dir=output_dir,
            normalizer=_FakeNormalizer(),
            ffmpeg=_FakeFfmpeg(),
            transcription_provider=provider,
            minutes_llm=_FakeMinutesLLM(),
            chunk_seconds=30,
            prompt_path=self.prompt_path,
            prompt_version="v-test",
            include_error_traceback=include_error_traceback,
        )

    def test_run_success_persists_manifest_and_outputs(self) -> None:
        output_dir = self.tmp_dir / "artifacts"
        provider = _ManifestAwareProvider(output_dir / "manifest.json")

        manifest = run(self.input_path, self._config(output_dir, provider))

        self.assertTrue(provider.saw_chunk_success_in_manifest)
        self.assertEqual(manifest.steps["validate"].status, "success")
        self.assertEqual(manifest.steps["normalize"].status, "success")
        self.assertEqual(manifest.steps["chunk"].status, "success")
        self.assertEqual(manifest.steps["transcribe"].status, "success")
        self.assertEqual(manifest.steps["generate"].status, "success")
        self.assertEqual(manifest.steps["write_outputs"].status, "success")

        manifest_path = output_dir / "manifest.json"
        self.assertTrue(manifest_path.exists())
        persisted = Manifest.read_json(manifest_path)
        self.assertEqual(persisted.steps["write_outputs"].status, "success")
        self.assertEqual(persisted.artifacts.transcript_path, "transcript.txt")
        self.assertEqual(persisted.artifacts.minutes_md_path, "minutes.md")
        self.assertEqual(persisted.artifacts.transcript_segments_path, "transcript_segments.json")
        self.assertIsNotNone(persisted.artifacts.transcript_sha256)
        self.assertIsNotNone(persisted.artifacts.minutes_sha256)
        self.assertEqual((output_dir / "minutes.md").read_text(encoding="utf-8").strip(), "# Minutes\n\n- hello world")
        self.assertEqual(persisted.steps["export_docx"].status, "skipped")

    def test_run_success_exports_docx_when_enabled(self) -> None:
        output_dir = self.tmp_dir / "artifacts_docx"
        provider = _ManifestAwareProvider(output_dir / "manifest.json")
        docx_exporter = _FakeDocxExporter()
        reference_docx_path = self.tmp_dir / "reference.docx"
        reference_docx_path.write_bytes(b"ref")

        config = self._config(output_dir, provider)
        config = PipelineConfig(
            output_dir=config.output_dir,
            normalizer=config.normalizer,
            ffmpeg=config.ffmpeg,
            transcription_provider=config.transcription_provider,
            minutes_llm=config.minutes_llm,
            chunk_seconds=config.chunk_seconds,
            docx_exporter=docx_exporter,
            prompt_path=config.prompt_path,
            prompt_version=config.prompt_version,
            minutes_extra_context=config.minutes_extra_context,
            export_minutes_docx=True,
            reference_docx_path=reference_docx_path,
            docx_toc=True,
            docx_toc_depth=2,
            include_error_traceback=config.include_error_traceback,
            run_id=config.run_id,
        )

        manifest = run(self.input_path, config)

        self.assertEqual(manifest.steps["export_docx"].status, "success")
        self.assertEqual(manifest.artifacts.minutes_docx_path, "minutes.docx")
        self.assertIsNotNone(manifest.artifacts.minutes_docx_sha256)
        self.assertTrue((output_dir / "minutes.docx").exists())
        self.assertEqual(len(docx_exporter.calls), 1)
        self.assertEqual(docx_exporter.calls[0]["reference_docx_path"], reference_docx_path)
        self.assertIs(docx_exporter.calls[0]["toc"], True)

    def test_run_failure_persists_failed_step_error_context(self) -> None:
        output_dir = self.tmp_dir / "artifacts_fail"
        provider = _ManifestAwareProvider(output_dir / "manifest.json", fail=True)

        with self.assertRaises(PipelineError):
            run(
                self.input_path,
                self._config(output_dir, provider, include_error_traceback=True),
            )

        manifest_path = output_dir / "manifest.json"
        self.assertTrue(manifest_path.exists())
        persisted = Manifest.read_json(manifest_path)

        self.assertTrue(provider.saw_chunk_success_in_manifest)
        self.assertEqual(persisted.steps["validate"].status, "success")
        self.assertEqual(persisted.steps["normalize"].status, "success")
        self.assertEqual(persisted.steps["chunk"].status, "success")
        self.assertEqual(persisted.steps["transcribe"].status, "failed")
        self.assertNotIn("write_outputs", persisted.steps)

        error = persisted.steps["transcribe"].error
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["type"], "TranscriptionError")
        self.assertIn("provider misconfig", error["message"])
        self.assertIn("context", error)
        self.assertEqual(error["context"]["step"], "transcribe")
        self.assertIn("traceback", error)


if __name__ == "__main__":
    unittest.main()
