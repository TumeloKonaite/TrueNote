import unittest

from src.contracts.errors import ContractError
from src.contracts.manifest import Manifest, should_skip_step


class ManifestValidationAndIdempotencyTests(unittest.TestCase):
    def test_required_vs_optional_artifact_validation(self) -> None:
        m = Manifest()
        m.artifacts.input_path = "input.mp4"

        m.validate_artifact_refs(required=["input_path"], optional=["minutes_md_path"])

        with self.assertRaises(ContractError):
            m.validate_artifact_refs(required=["normalized_audio_path"])

        with self.assertRaises(ContractError):
            m.validate_artifact_refs(required=["does_not_exist"])

    def test_should_skip_step_respects_hash_and_required_refs(self) -> None:
        m = Manifest(input_sha256="a" * 64)
        step = m.ensure_step("normalize")
        step.status = "success"

        self.assertFalse(
            should_skip_step(
                m,
                "normalize",
                require_artifact_paths=["normalized_audio_path"],
                expected_inputs_hashes={"input_sha256": "a" * 64},
            )
        )

        m.artifacts.normalized_audio_path = "audio_openai.mp3"
        self.assertTrue(
            should_skip_step(
                m,
                "normalize",
                require_artifact_paths=["normalized_audio_path"],
                expected_inputs_hashes={"input_sha256": "a" * 64},
            )
        )
        self.assertFalse(
            should_skip_step(
                m,
                "normalize",
                require_artifact_paths=["normalized_audio_path"],
                expected_inputs_hashes={"input_sha256": "b" * 64},
            )
        )


if __name__ == "__main__":
    unittest.main()
