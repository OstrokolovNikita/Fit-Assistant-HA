"""Unit tests for restricted light brightness data."""
import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location("dimming", Path(__file__).resolve().parents[1]/"custom_components/fit_assistant/dimming.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
class TestDimming(unittest.TestCase):
    def test_modes_and_levels(self):
        self.assertFalse(mod.dimmable("light.relay", {"supported_color_modes":["onoff"]}))
        self.assertFalse(mod.dimmable("switch.relay", {"supported_color_modes":["brightness"]}))
        self.assertTrue(mod.dimmable("light.lamp", {"supported_color_modes":["color_temp"]}))
        self.assertEqual(mod.level({"brightness":128}),50)
        self.assertIsNone(mod.level({}))
    def test_service_bounds(self):
        attrs={"supported_color_modes":["brightness"]}
        for bad in (0, 101, True, "40", 50.5):
            self.assertIsNone(mod.service_data("light.lamp","turn_on",attrs,{"brightness_pct":bad}))
        self.assertIsNone(mod.service_data("light.lamp","turn_off",attrs,{"brightness_pct":50}))
        self.assertIsNone(mod.service_data("switch.x","turn_on",attrs,{"brightness_pct":50}))
        self.assertEqual(mod.service_data("light.lamp","turn_on",attrs,{"brightness_pct":1}),{"entity_id":"light.lamp","brightness_pct":1})
        self.assertEqual(mod.service_data("switch.x","turn_off",{},{}),{"entity_id":"switch.x"})
if __name__ == "__main__":
    unittest.main()
