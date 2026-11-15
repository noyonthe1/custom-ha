"""Analyze camera snapshots using a remote vision server."""
import asyncio
import base64

import aiohttp
import voluptuous as vol
from homeassistant.components import camera
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("camera_entity_id"): cv.entity_id,
    vol.Required("prompt"): vol.All(str, vol.Length(min=1, max=4000)),
})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the analysis action."""
    async def analyze(call: ServiceCall) -> dict:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise HomeAssistantError("Camera Vision configuration is unavailable")
        entity_id = call.data["camera_entity_id"]
        if not entity_id.startswith("camera."):
            raise HomeAssistantError("Select a camera entity")
        try:
            image = await camera.async_get_image(hass, entity_id)
            payload = {"image": base64.b64encode(image.content).decode("ascii"), "prompt": call.data["prompt"]}
            session = async_get_clientsession(hass)
            async with session.post(
                f"{entry.data[CONF_URL]}/analyze", json=payload,
                headers={"Authorization": f"Bearer {entry.data[CONF_API_KEY]}"},
                timeout=aiohttp.ClientTimeout(total=600),
            ) as response:
                response.raise_for_status()
                result = await response.json()
            if not isinstance(result, dict):
                raise HomeAssistantError("Vision server returned an invalid response")
            return result
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise HomeAssistantError(f"Camera analysis failed: {err}") from err

    hass.services.async_register(DOMAIN, "analyze", analyze, schema=SCHEMA, supports_response=SupportsResponse.ONLY)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
