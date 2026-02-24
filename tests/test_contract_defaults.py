from pathlib import Path
import unittest

from src.contracts.artifacts import (
    AudioArtifact,
    ChunksArtifact,
    DocxArtifact,
    MinutesArtifact,
    TranscriptArtifact,
    TranscriptSegment,
)


class ArtifactDefaultsTests(unittest.TestCase):
    def test_artifact_construction_defaults(self) -> None:
        audio = AudioArtifact(path=Path("x.wav"), sha256="0" * 64)
        self.assertIsNone(audio.duration_s)
        self.assertIsNone(audio.sample_rate)
        self.assertIsNone(audio.channels)

        chunks = ChunksArtifact(dir=Path("chunks"), chunk_paths=[], chunk_seconds=30, count=0)
        self.assertEqual(chunks.count, 0)

        transcript = TranscriptArtifact(text="hi", provider="openai", model="gpt", chunk_count=1)
        self.assertIsNone(transcript.language)
        self.assertIsNone(transcript.segments)
        self.assertIsNone(transcript.duration_s)
        self.assertIsNone(transcript.timings)
        self.assertIsNone(transcript.meta)

        segment = TranscriptSegment(index=0, text="hello")
        self.assertIsNone(segment.start_s)
        self.assertIsNone(segment.end_s)
        self.assertIsNone(segment.chunk_index)

        minutes = MinutesArtifact(markdown="# hi", model="gpt", prompt_version="v1")
        self.assertIsNone(minutes.tokens)
        self.assertIsNone(minutes.meta)

        docx = DocxArtifact(path=Path("minutes.docx"), sha256="1" * 64)
        self.assertIsNone(docx.meta)


if __name__ == "__main__":
    unittest.main()
