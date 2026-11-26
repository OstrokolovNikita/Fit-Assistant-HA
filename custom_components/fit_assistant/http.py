"""Small HTTPS API with independent revocable tokens; never accepts arbitrary HA services."""
import asyncio
import json
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import Context
from homeassistant.helpers import area_registry, device_registry, entity_registry
from .const import DOMAIN, MAX_ENTITIES, READ_DOMAINS
from .protocol import matches, action_allowed
from .layout import decorate
from .trend import get_trend, number
from .dimming import dimmable, level, service_data


def reply(data, status=200):
    return web.json_response(data, status=status, headers={"Cache-Control": "no-store"})


class BaseView(HomeAssistantView):
    requires_auth = False  # Explicit device auth on every protected endpoint below.

    def __init__(self, hass, hub):
        self.hass, self.hub = hass, hub

    def entries(self):
        return [e for e in self.hass.config_entries.async_entries(DOMAIN)
                if e.entry_id in self.hub['loaded']]

    def profile(self, request):
        token = request.headers.get('X-Fit-Token', '')
        return next((e for e in self.entries() if matches(token, e.options.get('token_hash'))), None)

    def items(self, entry):
        controls = entry.options.get('controls', [])
        entities = list(dict.fromkeys(entry.options.get('entities', []) + controls))[:MAX_ENTITIES]
        result = []
        er = entity_registry.async_get(self.hass)
        dr = device_registry.async_get(self.hass)
        ar = area_registry.async_get(self.hass)
        for entity in entities:
            if entity.partition('.')[0] not in READ_DOMAINS:
                continue
            state = self.hass.states.get(entity)
            name = str(state.name if state else entity)[:60]
            value = str(state.state if state else 'unavailable')[:60]
            unit = str(state.attributes.get('unit_of_measurement') or '')[:15] if state else ''
            reg = er.async_get(entity)
            area_id = reg.area_id if reg else None
            if not area_id and reg and reg.device_id:
                device = dr.async_get(reg.device_id)
                area_id = device.area_id if device else None
            area = ar.async_get_area(area_id) if area_id else None
            item = {'id': entity, 'name': name, 'state': value, 'unit': unit,
                    '_area': area.name if area else '',
                    'control': action_allowed(entity, 'turn_on', controls) and value in ('on','off')}
            if item['control'] and state and dimmable(entity, state.attributes):
                item['dimmable'] = True
                item['brightness'] = level(state.attributes)
            result.append(item)
        return decorate(result, entry.options)


class PairView(BaseView):
    url = '/api/fit_assistant/v1/pair'
    name = 'api:fit_assistant:pair'

    async def post(self, request):
        # Only open while an administrator has created an unpaired watch profile.
        if not any(not e.options.get('token_hash') for e in self.entries()):
            return reply({'status': 'closed'}, 403)
        result = self.hub['pool'].start()
        if result is None:
            return reply({'status': 'rate_limited'}, 429)
        code, token = result
        return reply({'status': 'pending', 'code': code, 'token': token, 'expires_in': 600})


class DashboardView(BaseView):
    url = '/api/fit_assistant/v1/dashboard'
    name = 'api:fit_assistant:dashboard'

    async def get(self, request):
        entry = self.profile(request)
        if entry is None:
            if self.hub['pool'].waiting(request.headers.get('X-Fit-Token','')):
                return reply({'status': 'pending'})
            return reply({'status': 'denied'}, 403)
        items = self.items(entry)
        requested = request.query.get("history", "")
        item = next((i for i in items if i["id"] == requested), None)
        trend = None
        history_status = 'disabled'
        if item and requested.startswith("sensor.") and number(item["state"]) is not None:
            hours = entry.options.get("cards", {}).get(requested, {}).get("history_hours", 12)
            history_status, trend = await get_trend(self.hass, self.hub, requested, hours)
            # Reauthorize after the asynchronous Recorder query.
            entry = self.profile(request)
            if entry is None:
                return reply({"status": "denied"}, 403)
            items = self.items(entry)
            item = next((i for i in items if i["id"] == requested), None)
            current_hours = entry.options.get("cards", {}).get(requested, {}).get("history_hours", 12)
            if item and hours == current_hours and number(item["state"]) is not None:
                item["history_status"] = history_status
                if trend:
                    item["history"] = trend
        return reply({"status": "ok", "name": entry.title[:40], "items": items,
                      "language": entry.options.get("language", "en"),
                      "keep_seconds": entry.options.get("keep_seconds", 15)})


class ActionView(BaseView):
    url = '/api/fit_assistant/v1/action'
    name = 'api:fit_assistant:action'

    async def post(self, request):
        entry = self.profile(request)
        if entry is None:
            return reply({'status': 'denied'}, 403)
        if request.content_length is not None and request.content_length > 1024:
            return reply({'status': 'bad_request'}, 400)
        try:
            raw = bytearray()
            async with asyncio.timeout(5):
                async for chunk in request.content.iter_chunked(1024):
                    raw.extend(chunk)
                    if len(raw) > 1024:
                        return reply({'status': 'bad_request'}, 400)
            body = json.loads(raw)
        except (ValueError, UnicodeError, TimeoutError):
            return reply({'status': 'bad_request'}, 400)
        if not isinstance(body, dict):
            return reply({'status': 'bad_request'}, 400)
        # Recheck after awaiting input, in case the admin revoked or edited the profile.
        entry = self.profile(request)
        if entry is None:
            return reply({'status': 'denied'}, 403)
        entity, action = body.get('entity'), body.get('action')
        if not action_allowed(entity, action, entry.options.get('controls', [])):
            return reply({'status': 'denied'}, 403)
        state = self.hass.states.get(entity)
        if state is None or state.state not in ('on', 'off'):
            return reply({'status': 'unavailable'}, 409)
        data = service_data(entity, action, state.attributes, body)
        if data is None:
            return reply({'status': 'bad_request'}, 400)
        if entry.entry_id in self.hub['busy']:
            return reply({'status': 'busy'}, 409)
        self.hub['busy'].add(entry.entry_id)
        try:
            await self.hass.services.async_call(entity.split('.')[0], action,
                data, blocking=True, context=Context())
        except Exception:
            return reply({'status': 'service_failed'}, 502)
        finally:
            self.hub['busy'].discard(entry.entry_id)
        return reply({'status': 'ok', 'items': self.items(entry)})
