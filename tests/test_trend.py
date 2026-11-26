"""Pure numeric history tests."""
import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location("trend", Path(__file__).resolve().parents[1] / "custom_components/fit_assistant/trend.py")
trend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trend)
class TestTrend(unittest.TestCase):
    def test_full(self):
        r = trend.summarize([(0, "-2"), (3600, "3")], 0, 7200, 12)
        self.assertEqual((r["min"],r["max"],len(r["points"])),(-2,3,36))
    def test_partial(self):
        r = trend.summarize([(0,"1"),(10,"unavailable"),(60,"2"),(120,"3")],0,180,12)
        self.assertEqual((r["min"],r["max"],r["minutes"]),(2,3,2))
    def test_constant(self):
        self.assertEqual(trend.summarize([(0,"25")],0,100,12)["points"],[50]*36)
    def test_missing(self):
        self.assertIsNone(trend.summarize([],0,100,12))
        self.assertIsNone(trend.summarize([(0,"1"),(2,"unknown")],0,100,12))
if __name__ == "__main__":
    unittest.main()
