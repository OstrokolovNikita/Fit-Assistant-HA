"""Optional, bounded numeric history for an authorized sensor."""
from datetime import datetime, timedelta, timezone
from functools import partial
from math import isfinite
from time import monotonic
import asyncio

PERIODS = (0, 3, 6, 12, 24)
POINTS = 36


def number(value):
    try:
        n = float(value)
        return n if isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def summarize(rows, start, end, hours):
    """Sample the last known recorded state at equal time intervals.
    Do not bridge explicit unavailable states or invent a missing initial state.
    """
    if not rows or rows[0][0] > start or any(number(v) is None for _, v in rows):
        return None
    vals = []
    at = 0
    for i in range(POINTS):
        t = start + (end - start) * i / (POINTS - 1)
        while at + 1 < len(rows) and rows[at + 1][0] <= t:
            at += 1
        vals.append(number(rows[at][1]))
    observed = [number(v) for _, v in rows]
    lo, hi = min(observed), max(observed)
    if not isfinite(hi - lo):
        return None
    points = [50 if hi == lo else round(8 + 84 * ((v - lo) / (hi - lo))) for v in vals]
    return {"hours": hours, "min": round(lo, 2), "max": round(hi, 2), "points": points}


def load_history(hass, entity, hours):
    from homeassistant.components.recorder import history
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    data = history.get_significant_states(
        hass, start, end, entity_ids=[entity],
        include_start_time_state=True, no_attributes=True,
    )
    rows = [(s.last_updated.timestamp(), s.state) for s in data.get(entity, [])]
    return summarize(rows, start.timestamp(), end.timestamp(), hours)


async def get_trend(hass, hub, entity, hours):
    """Cache only derived readings, one Recorder job at a time per hub."""
    if hours not in PERIODS or not hours:
        return None
    cache = hub.setdefault("trend_cache", {})
    key = (entity, hours)
    now = monotonic()
    cached = cache.get(key)
    if cached and now - cached[0] < 300:
        return cached[1]
    if hub.get("trend_busy"):
        return None
    hub["trend_busy"] = True
    # Negative cache prevents hammering missing history.
    if len(cache) >= 100:
        cache.clear()
    cache[key] = (now, None)

    async def run():
        try:
            from homeassistant.components.recorder import get_instance
            value = await get_instance(hass).async_add_executor_job(
                partial(load_history, hass, entity, hours))
            cache[key] = (monotonic(), value)
            return value
        except Exception:
            return None
        finally:
            hub["trend_busy"] = False

    task = hass.async_create_task(run())
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=2)
    except TimeoutError:
        return None
