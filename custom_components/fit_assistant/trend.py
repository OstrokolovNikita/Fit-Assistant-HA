"""Optional, bounded numeric history for an authorized sensor."""
from datetime import datetime, timedelta, timezone
from functools import partial
from math import isfinite
from time import monotonic
from zoneinfo import ZoneInfo
import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

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
    rows = sorted((t, v) for t, v in rows if t <= end)
    # Use only the latest uninterrupted numeric segment. Never bridge gaps.
    for i in range(len(rows) - 1, -1, -1):
        if number(rows[i][1]) is None:
            rows = rows[i+1:]
            break
    if not rows:
        return None
    start = max(start, rows[0][0])
    if end <= start:
        return None
    # Keep at most the last state at/before the requested start.
    while len(rows) > 1 and rows[1][0] <= start:
        rows.pop(0)
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
    return {"hours": hours, "minutes": max(1, round((end-start)/60)),
            "start": int(start), "end": int(end),
            "min": round(lo, 2), "max": round(hi, 2), "points": points}


def load_history(hass, entity, hours):
    from homeassistant.components.recorder import history
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    data = history.get_significant_states(
        hass, start, end, entity_ids=[entity],
        include_start_time_state=True, no_attributes=True,
    )
    rows = [(s.last_updated.timestamp(), s.state) for s in data.get(entity, [])]
    result = summarize(rows, start.timestamp(), end.timestamp(), hours)
    if result:
        zone = ZoneInfo(hass.config.time_zone)
        first = datetime.fromtimestamp(result["start"], zone)
        last = datetime.fromtimestamp(result["end"], zone)
        result["interval"] = f"{first:%H:%M} – {last:%H:%M}"
        if result["minutes"] >= 1439:
            result["interval"] += " (24h)"
    return result


async def get_trend(hass, hub, entity, hours):
    """Cache only derived readings, one Recorder job at a time per hub."""
    if hours not in PERIODS or not hours:
        return ("disabled", None)
    cache = hub.setdefault("trend_cache", {})
    key = (entity, hours)
    now = monotonic()
    cached = cache.get(key)
    if cached and now - cached[0] < (300 if cached[1][0] == "ok" else 15):
        return cached[1]
    if hub.get("trend_busy"):
        return ("pending", None)
    hub["trend_busy"] = True
    # Negative cache prevents hammering missing history.
    if len(cache) >= 100:
        cache.clear()
    cache[key] = (now, ("pending", None))

    async def run():
        try:
            try:
                from homeassistant.helpers.recorder import get_instance
            except ImportError:
                from homeassistant.components.recorder import get_instance
            value = await get_instance(hass).async_add_executor_job(
                partial(load_history, hass, entity, hours))
            result = ("ok", value) if value else ("empty", None)
        except Exception:
            _LOGGER.exception("Failed to read Fit Assistant sensor history")
            result = ("error", None)
        finally:
            hub["trend_busy"] = False
        cache[key] = (monotonic(), result)
        return result

    task = hass.async_create_task(run())
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=2)
    except TimeoutError:
        return ("pending", None)
