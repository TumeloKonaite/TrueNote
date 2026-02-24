from pathlib import Path
import unittest

from src.contracts.artifacts import AudioArtifact, ChunksArtifact, MinutesArtifact, TranscriptArtifact


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
        self.assertIsNone(transcript.timings)

        minutes = MinutesArtifact(markdown="# hi", model="gpt", prompt_version="v1")
        self.assertIsNone(minutes.tokens)


if __name__ == "__main__":
    unittest.main()
