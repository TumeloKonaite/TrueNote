from pathlib import Path
import unittest

from src.contracts.manifest import Manifest, should_skip_step


class ManifestRoundtripTests(unittest.TestCase):
    def test_manifest_roundtrip(self) -> None:
        tmp_dir = Path("tests") / ".tmp_manifest_roundtrip"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = tmp_dir / "manifest.json"

        m = Manifest(version="1", run_id="abc", input_sha256="1" * 64)
        m.artifacts.input_path = "in.wav"
        m.artifacts.input_sha256 = "1" * 64
        m.ensure_step("normalize").status = "success"
        m.artifacts.normalized_audio_path = "artifacts/normalized.wav"
        m.write_json(manifest_path)

        m2 = Manifest.read_json(manifest_path)
        self.assertEqual(m2.version, "1")
        self.assertEqual(m2.run_id, "abc")
        self.assertEqual(m2.artifacts.input_path, "in.wav")
        self.assertEqual(m2.steps["normalize"].status, "success")
        self.assertEqual(m2.artifacts.normalized_audio_path, "artifacts/normalized.wav")
        self.assertTrue(should_skip_step(m2, "normalize", require_artifact_paths=["normalized_audio_path"]))

        manifest_path.unlink(missing_ok=True)
        tmp_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
