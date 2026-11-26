import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "fit_assistant"
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
p = load("protocol")
c = load("cover_control")

class CoverTests(unittest.TestCase):
    def test_scope(self):
        self.assertFalse(p.action_allowed("cover.a", "open_cover", []))
        self.assertFalse(p.action_allowed("cover.a", "turn_on", ["cover.a"]))
        self.assertFalse(p.action_allowed("light.a", "open_cover", ["light.a"]))
        self.assertTrue(p.action_allowed("cover.a", "open_cover", ["cover.a"]))
        self.assertTrue(p.action_allowed("light.a", "turn_on", ["light.a"]))
    def test_capabilities(self):
        self.assertEqual(c.fields({"supported_features": 15, "current_position": 0}), {"cover_control": True, "cover_open": True, "cover_close": True, "cover_stop": True, "cover_position": True, "position": 0})
        self.assertFalse(c.fields({"supported_features": 1})["cover_position"])
        self.assertIsNone(c.fields({"current_position": True})["position"])
    def test_position(self):
        for pos in (0, 65, 100):
            body={"entity":"cover.a","action":"set_cover_position","position":pos}
            self.assertEqual(c.service_data("cover.a","set_cover_position",{"supported_features":4},body), {"entity_id":"cover.a","position":pos})
            self.assertIsNone(c.service_data("cover.a","set_cover_position",{"supported_features":1},body))
        for pos in (-1, 101, True, "65", 50.5, None):
            self.assertIsNone(c.service_data("cover.a","set_cover_position",{"supported_features":4},{"entity":"cover.a","action":"set_cover_position","position":pos}))
    def test_commands(self):
        for action, bit in c.FEATURES.items():
            if action == "set_cover_position": continue
            body={"entity":"cover.a","action":action}
            self.assertEqual(c.service_data("cover.a",action,{"supported_features":bit},body),{"entity_id":"cover.a"})
            self.assertIsNone(c.service_data("cover.a",action,{"supported_features":0},body))
            self.assertIsNone(c.service_data("cover.a",action,{"supported_features":bit},{**body,"position":50}))
    def test_pair_unchanged(self):
        pool=p.PairingPool()
        code,t=pool.start()
        opts={"token_hash":p.digest("a"*64),"cards":{"cover.a":{"label":"Curtains"}}}
        self.assertIsNone(p.apply_pairing(opts,pool,code,False))
        self.assertTrue(p.matches(t,opts["token_hash"]))
        self.assertEqual(opts["cards"],{"cover.a":{"label":"Curtains"}})
if __name__ == "__main__": unittest.main()
