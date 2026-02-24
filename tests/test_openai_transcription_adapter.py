from __future__ import annotations

from pathlib import Path
import shutil
import unittest

from src.adapters.openai_transcription import OpenAITranscriptionAdapter
from src.components.transcription import transcribe_chunks
from src.contracts.artifacts import ChunksArtifact, TranscriptArtifact
from src.contracts.errors import ProviderRetryExhaustedError, TranscriptionError


class _Obj:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeTranscriptionsAPI:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        file_handle = kwargs["file"]
        self.calls.append(
            {
                "filename": Path(file_handle.name).name,
                "model": kwargs.get("model"),
                "response_format": kwargs.get("response_format"),
                "timestamp_granularities": kwargs.get("timestamp_granularities"),
                "language": kwargs.get("language"),
            }
        )
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


class _FakeAudioAPI:
    def __init__(self, transcriptions: _FakeTranscriptionsAPI) -> None:
        self.transcriptions = transcriptions


class _FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.audio = _FakeAudioAPI(_FakeTranscriptionsAPI(responses))


class _WrongCountProvider:
    def transcribe(self, chunks: ChunksArtifact) -> TranscriptArtifact:
        return TranscriptArtifact(
            text="bad",
            provider="x",
            model="m",
            chunk_count=max(0, chunks.count - 1),
        )


class OpenAITranscriptionAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path("tests") / ".tmp_openai_transcription_adapter"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_paths = []
        for idx in range(2):
            path = self.tmp_dir / f"chunk_{idx:04d}.wav"
            path.write_bytes(b"RIFF")
            self.chunk_paths.append(path)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _chunks_artifact(self) -> ChunksArtifact:
        return ChunksArtifact(
            dir=self.tmp_dir,
            chunk_paths=list(self.chunk_paths),
            chunk_seconds=30,
            count=2,
        )

    def test_openai_adapter_retries_and_normalizes_stitched_transcript(self) -> None:
        responses = [
            RuntimeError("transient"),
            {
                "text": "hello world",
                "language": "en",
                "duration": 12.5,
                "segments": [
                    {"text": "hello", "start": 0.0, "end": 0.6},
                    {"text": "world", "start": 0.7, "end": 1.2},
                ],
            },
            _Obj(
                text="second chunk",
                language="en",
                duration=10.0,
                segments=[
                    _Obj(text="second", start=0.2, end=0.8),
                    _Obj(text="chunk", start=0.9, end=1.4),
                ],
            ),
        ]
        client = _FakeClient(responses)
        adapter = OpenAITranscriptionAdapter(
            client,
            model="gpt-4o-mini-transcribe",
            language="en",
            max_retries_per_chunk=2,
        )

        transcript = transcribe_chunks(self._chunks_artifact(), adapter)

        self.assertEqual(transcript.provider, "openai")
        self.assertEqual(transcript.model, "gpt-4o-mini-transcribe")
        self.assertEqual(transcript.chunk_count, 2)
        self.assertEqual(transcript.language, "en")
        self.assertEqual(transcript.text, "hello world\nsecond chunk")
        self.assertIsNotNone(transcript.segments)
        assert transcript.segments is not None
        self.assertEqual(len(transcript.segments), 4)
        self.assertEqual(transcript.segments[0].chunk_index, 0)
        self.assertEqual(transcript.segments[2].chunk_index, 1)
        self.assertAlmostEqual(transcript.segments[2].start_s or 0.0, 30.2, places=3)
        self.assertAlmostEqual(transcript.segments[3].end_s or 0.0, 31.4, places=3)
        self.assertAlmostEqual(transcript.duration_s or 0.0, 31.4, places=3)
        self.assertEqual(transcript.timings["segments_count"], 4)
        self.assertEqual(transcript.timings["timestamped_segments_count"], 4)
        self.assertEqual(transcript.meta["chunk_seconds"], 30)

        calls = client.audio.transcriptions.calls
        self.assertEqual(len(calls), 3)  # first chunk retried once
        self.assertEqual(calls[0]["filename"], "chunk_0000.wav")
        self.assertEqual(calls[1]["filename"], "chunk_0000.wav")
        self.assertEqual(calls[2]["filename"], "chunk_0001.wav")
        self.assertEqual(calls[0]["response_format"], "verbose_json")
        self.assertEqual(calls[0]["timestamp_granularities"], ["segment"])

    def test_openai_adapter_raises_after_retry_exhausted(self) -> None:
        client = _FakeClient([RuntimeError("down"), RuntimeError("still down")])
        adapter = OpenAITranscriptionAdapter(client, model="gpt", max_retries_per_chunk=1)

        with self.assertRaises(ProviderRetryExhaustedError):
            adapter.transcribe(
                ChunksArtifact(
                    dir=self.tmp_dir,
                    chunk_paths=[self.chunk_paths[0]],
                    chunk_seconds=30,
                    count=1,
                )
            )

    def test_component_enforces_provider_contract_chunk_count(self) -> None:
        with self.assertRaises(TranscriptionError):
            transcribe_chunks(self._chunks_artifact(), _WrongCountProvider())


if __name__ == "__main__":
    unittest.main()
