import unittest

from src.contracts.manifest import StepRecord


class StepRecordTests(unittest.TestCase):
    def test_duration_calculation(self) -> None:
        step = StepRecord(name="normalize")
        step.start(at_s=10.0)
        step.finish(status="success", at_s=10.125)

        self.assertEqual(step.duration_ms, 125)
        self.assertEqual(step.attempts, 1)
        self.assertEqual(step.status, "success")

    def test_duration_non_negative(self) -> None:
        step = StepRecord(name="normalize", started_at_s=5.0, ended_at_s=4.0)
        self.assertEqual(step.compute_duration_ms(), 0)


if __name__ == "__main__":
    unittest.main()
