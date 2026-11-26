"""Bounded light-only brightness controls; authorization remains in ActionView."""
MODES = frozenset(("brightness", "color_temp", "hs", "xy", "rgb", "rgbw", "rgbww", "white"))

def dimmable(entity, attributes):
    modes = attributes.get("supported_color_modes") or ()
    return entity.startswith("light.") and any(mode in MODES for mode in modes)

def level(attributes):
    value = attributes.get("brightness")
    if type(value) not in (int, float) or not 1 <= value <= 255:
        return None
    return max(1, min(100, round(value * 100 / 255)))

def service_data(entity, action, attributes, body):
    result = {"entity_id": entity}
    if "brightness_pct" not in body:
        return result
    value = body["brightness_pct"]
    if action != "turn_on" or not dimmable(entity, attributes) or type(value) is not int or not 1 <= value <= 100:
        return None
    result["brightness_pct"] = value
    return result
