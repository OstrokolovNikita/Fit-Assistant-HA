"""Pure history sampler tests (no HA runtime required)."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("trend", Path(__file__).resolve().parents[1] / "custom_components/fit_assistant/trend.py")
trend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trend)

class TestTrend(unittest.TestCase):
    def test_negative_and_positive(self):
        result = trend.summarize([(0, "-2"), (50, "3")], 0, 100, 12)
        self.assertEqual((result["min"], result["max"]), (-2, 3))
        self.assertEqual(len(result["points"]), 36)
        self.assertEqual((result["points"][0], result["points"][-1]), (8, 92))

    def test_constant(self):
        self.assertEqual(trend.summarize([(0, "25")], 0, 100, 12)["points"], [50]*36)

    def test_missing(self):
        self.assertIsNone(trend.summarize([], 0, 100, 12))
        self.assertIsNone(trend.summarize([(1, "2")], 0, 100, 12))
        self.assertIsNone(trend.summarize([(0, "2"), (2, "unavailable")], 0, 100, 12))

if __name__ == "__main__":
    unittest.main()
