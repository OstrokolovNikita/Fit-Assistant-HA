import importlib.util
from pathlib import Path
import unittest
path=Path(__file__).with_name('trend.py')
if not path.exists(): path=Path(__file__).resolve().parents[1]/'custom_components/fit_assistant/trend.py'
spec=importlib.util.spec_from_file_location('trend',path)
trend=importlib.util.module_from_spec(spec);spec.loader.exec_module(trend)
class TrendTests(unittest.TestCase):
    def test_tiny_temperature(self):
        r=trend.summarize([(0,'1.76'),(60,'1.77')],0,120,12,'°C')
        self.assertEqual((r['min'],r['max']),(0,3))
        self.assertLessEqual(max(r['points'])-min(r['points']),1)
    def test_weighted_smooth(self):
        r=trend.summarize([(0,'-2'),(3600,'3')],0,7200,12,'°C')
        self.assertEqual((r['min'],r['max'],len(r['points'])),(-3,4,36))
        self.assertTrue(any(15<p<85 for p in r['points']))
        self.assertGreater(min(r['points']),0);self.assertLess(max(r['points']),100)
    def test_humidity(self):
        r=trend.summarize([(0,'53.1'),(60,'53.2')],0,120,12,'%')
        self.assertEqual((r['min'],r['max']),(45,60))
    def test_gap(self):
        r=trend.summarize([(0,'2'),(60,'unknown'),(120,'3')],0,3600,12,'°C')
        self.assertEqual(r['start'],0)
        r=trend.summarize([(0,'2'),(60,'unknown'),(600,'3')],0,3600,12,'°C')
        self.assertEqual(r['start'],600)
        self.assertIsNone(trend.summarize([(0,'2'),(60,'unknown')],0,3600,12,'°C'))
    def test_missing(self):
        self.assertIsNone(trend.summarize([],0,100,12))
        r=trend.summarize([(50,'25')],0,100,12,'°C')
        self.assertEqual(r['start'],50)
        self.assertEqual(r['points'],[50]*36)
if __name__=='__main__': unittest.main()
