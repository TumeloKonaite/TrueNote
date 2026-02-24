from __future__ import annotations

from pathlib import Path
import shutil
import unittest

from src.components.minutes import generate_minutes, load_minutes_prompt
from src.contracts.artifacts import MinutesArtifact, TranscriptArtifact
from src.utils.hashing import sha256_file


class _FakeMinutesLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate_minutes(
        self,
        transcript: TranscriptArtifact,
        *,
        prompt: str,
        extra_context: dict[str, str] | None = None,
    ) -> MinutesArtifact:
        self.calls.append(
            {
                "transcript": transcript,
                "prompt": prompt,
                "extra_context": extra_context,
            }
        )
        return MinutesArtifact(
            markdown="# Minutes\n\n- Item",
            model="fake-minutes-model",
            tokens={"total": 42},
            meta={"request_id": "req_123"},
        )


class PromptLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path("tests") / ".tmp_prompt_loading"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_load_minutes_prompt_reads_text_and_sha256(self) -> None:
        prompt_path = self.tmp_dir / "minutes_prompt.md"
        prompt_text = "Line 1\nLine 2\n"
        prompt_path.write_text(prompt_text, encoding="utf-8")

        loaded = load_minutes_prompt(prompt_path)

        self.assertEqual(loaded.path, prompt_path)
        self.assertEqual(loaded.text, prompt_text)
        self.assertEqual(loaded.prompt_hash, sha256_file(prompt_path))

    def test_generate_minutes_includes_prompt_provenance_in_meta(self) -> None:
        prompt_path = self.tmp_dir / "minutes_prompt.md"
        prompt_text = "Write concise minutes in Markdown."
        prompt_path.write_text(prompt_text, encoding="utf-8")

        transcript = TranscriptArtifact(
            text="Chair opened the meeting. Motion passed.",
            provider="openai",
            model="gpt-4o-mini-transcribe",
            chunk_count=1,
        )
        llm = _FakeMinutesLLM()

        minutes = generate_minutes(
            transcript,
            llm=llm,
            prompt_path=prompt_path,
            prompt_version="v2026-02-24",
            extra_context={"jurisdiction": "Denver"},
        )

        self.assertEqual(minutes.model, "fake-minutes-model")
        self.assertEqual(minutes.prompt_version, "v2026-02-24")
        self.assertEqual(minutes.tokens, {"total": 42})
        self.assertIsNotNone(minutes.meta)
        assert minutes.meta is not None
        self.assertEqual(minutes.meta["request_id"], "req_123")
        self.assertEqual(minutes.meta["prompt_path"], str(prompt_path))
        self.assertEqual(minutes.meta["prompt_hash"], sha256_file(prompt_path))
        self.assertEqual(minutes.meta["prompt_version"], "v2026-02-24")

        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(llm.calls[0]["prompt"], prompt_text)
        self.assertEqual(llm.calls[0]["extra_context"], {"jurisdiction": "Denver"})
        self.assertIs(llm.calls[0]["transcript"], transcript)


if __name__ == "__main__":
    unittest.main()
