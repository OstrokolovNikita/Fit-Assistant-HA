"""Explicit feature-gated cover controls. No arbitrary service calls."""
FEATURES = {"open_cover": 1, "close_cover": 2, "set_cover_position": 4, "stop_cover": 8}
STATES = frozenset(("open", "closed", "opening", "closing"))


def capabilities(attributes):
    flags = attributes.get("supported_features", 0)
    if type(flags) is not int or flags < 0:
        flags = 0
    return {name: bool(flags & bit) for name, bit in FEATURES.items()}


def fields(attributes):
    caps = capabilities(attributes)
    pos = attributes.get("current_position")
    return {
        "cover_control": any(caps.values()),
        "cover_open": caps["open_cover"],
        "cover_close": caps["close_cover"],
        "cover_stop": caps["stop_cover"],
        "cover_position": caps["set_cover_position"],
        "position": pos if type(pos) is int and 0 <= pos <= 100 else None,
    }


def service_data(entity, action, attributes, body):
    if not isinstance(entity, str) or not entity.startswith("cover.") or not capabilities(attributes).get(action):
        return None
    if action == "set_cover_position":
        pos = body.get("position")
        if set(body) != {"entity", "action", "position"} or type(pos) is not int or not 0 <= pos <= 100:
            return None
        return {"entity_id": entity, "position": pos}
    if set(body) != {"entity", "action"}:
        return None
    return {"entity_id": entity}
