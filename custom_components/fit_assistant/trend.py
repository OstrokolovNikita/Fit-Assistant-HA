"""Bounded history, time-weighted bucket averages and readable axis bounds."""
from datetime import datetime, timedelta, timezone
from math import ceil, floor, isfinite, log10
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


def bounds(lo, hi, unit):
    if unit in ('°C', '°F', 'K'):
        step, pad = 1, 1
    elif unit == '%':
        step, pad = 5, 5
    else:
        scale = max(hi-lo, abs(hi)*0.02, abs(lo)*0.02, 1e-6)
        power = 10 ** floor(log10(scale/4))
        step = next((power*k for k in (1, 2, 5, 10) if power*k >= scale/4), power*10)
        pad = step
    low, high = floor((lo-pad)/step)*step, ceil((hi+pad)/step)*step
    if unit == '%' and 0 <= lo <= hi <= 100:
        low, high = max(0, low), min(100, high)
    return round(low, 9), round(high, 9)


def summarize(rows, start, end, hours, unit=''):
    """Use real state durations, bridge only short bounded gaps, never invent hours."""
    rows = sorted(((t, number(v)) for t, v in rows if t <= end), key=lambda row: row[0])
    # Keep the initial state and the whole requested window where available.
    while len(rows) > 1 and rows[1][0] <= start:
        rows.pop(0)
    # A short unavailable episode is a missing sample, not a new temperature.
    # Only interpolate gaps bracketed by real numeric observations (<= 5 min).
    segments = []
    part = []
    for i, (t, val) in enumerate(rows):
        if val is None:
            if part:
                segments.append((part, t))
                part = []
            continue
        if not part and segments and t-segments[-1][1] <= 300:
            prev, gap = segments.pop()
            part = prev + [(gap, (prev[-1][1]+val)/2)]
        part.append((t, val))
    if not part:
        return None
    # Do not pretend a long outage was measured. Use the latest actual segment.
    start = max(start, part[0][0])
    if end <= start:
        return None
    width = (end-start)/POINTS
    vals = []
    idx = 0
    for i in range(POINTS):
        a = start+i*width
        b = min(end, a+width)
        while idx+1 < len(part) and part[idx+1][0] <= a:
            idx += 1
        total, t = 0.0, a
        while idx+1 < len(part) and part[idx+1][0] < b:
            nxt = part[idx+1][0]
            total += (nxt-t)*part[idx][1]
            t = nxt
            idx += 1
        total += (b-t)*part[idx][1]
        vals.append(total/(b-a))
    # Three-point weighted moving average. Preserve actual extrema for scale.
    smooth = [(vals[max(0,i-1)] + 2*vals[i] + vals[min(POINTS-1,i+1)])/4 for i in range(POINTS)]
    lo, hi = min(v for _,v in part), max(v for _,v in part)
    if not isfinite(hi-lo) or not all(isfinite(v) for v in smooth):
        return None
    low, high = bounds(lo, hi, unit)
    if high <= low:
        return None
    points = [max(0,min(100,round((v-low)*100/(high-low)))) for v in smooth]
    return {'hours':hours,'minutes':max(1,round((end-start)/60)), 'start':int(start),'end':int(end),
            'min':low,'max':high,'points':points}


def load_batch(hass, keys):
    from homeassistant.components.recorder import history
    end = datetime.now(timezone.utc)
    zone = ZoneInfo(hass.config.time_zone)
    results = {}
    for hours in sorted({k[1] for k in keys}):
        subset = [k for k in keys if k[1] == hours]
        start = end-timedelta(hours=hours)
        try:
            data = history.get_significant_states(hass,start,end,entity_ids=[k[0] for k in subset],
                include_start_time_state=True, significant_changes_only=False, no_attributes=True)
            for key in subset:
                entity, _, unit = key
                rows = [(s.last_updated.timestamp(),s.state) for s in data.get(entity,[])]
                result = summarize(rows,start.timestamp(),end.timestamp(),hours,unit)
                if result:
                    first = datetime.fromtimestamp(result['start'],zone)
                    last = datetime.fromtimestamp(result['end'],zone)
                    result['interval'] = f'{first:%H:%M} – {last:%H:%M}'
                    if result['minutes'] >= 1439:
                        result['interval'] += ' (24h)'
                results[key] = ('ok',result) if result else ('empty',None)
        except Exception:
            _LOGGER.exception('Failed to read Fit Assistant history batch')
            results.update({key:('error',None) for key in subset})
    return results


async def get_trends(hass, hub, keys):
    """One recorder task per hub; group sensors by period, cache each result."""
    keys = list(dict.fromkeys(k for k in keys if k[1] in PERIODS and k[1]))[:20]
    cache = hub.setdefault('trend_cache',{})
    now = monotonic()
    missing = [k for k in keys if k not in cache or now-cache[k][0] >= (300 if cache[k][1][0]=='ok' else 15)]
    if missing and not hub.get('trend_busy'):
        hub['trend_busy'] = True
        async def run():
            try:
                try:
                    from homeassistant.helpers.recorder import get_instance
                except ImportError:
                    from homeassistant.components.recorder import get_instance
                results = await get_instance(hass).async_add_executor_job(load_batch,hass,missing)
                if len(cache)>100:
                    cache.clear()
                cache.update({k:(monotonic(),v) for k,v in results.items()})
            except Exception:
                _LOGGER.exception('Fit Assistant recorder unavailable')
                cache.update({k:(monotonic(),('error',None)) for k in missing})
            finally:
                hub['trend_busy']=False
        task = hass.async_create_task(run())
        try:
            await asyncio.wait_for(asyncio.shield(task),timeout=2)
        except TimeoutError:
            pass
    return {k:cache.get(k,(0,('pending',None)))[1] for k in keys}
