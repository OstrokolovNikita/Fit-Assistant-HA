"""Fit Assistant integration: each config entry is an independently scoped watch."""
from .const import DOMAIN
from .protocol import PairingPool
from .http import PairView, DashboardView, ActionView


async def async_setup(hass, config):
    if DOMAIN not in hass.data:
        hub = {"pool": PairingPool(), "loaded": set(), "busy": set()}
        hass.data[DOMAIN] = hub
        for view in (PairView, DashboardView, ActionView):
            hass.http.register_view(view(hass, hub))
    return True


async def async_setup_entry(hass, entry):
    hass.data[DOMAIN]["loaded"].add(entry.entry_id)
    return True


async def async_unload_entry(hass, entry):
    hass.data[DOMAIN]["loaded"].discard(entry.entry_id)
    return True
