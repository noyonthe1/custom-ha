"""Home Assistant actions for the Clanker AI Gateway."""

import asyncio
import base64
import json

import aiohttp
import voluptuous as vol
from homeassistant.components import camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_TIMEOUT, DOMAIN, POLL_INTERVAL

CHAT_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): str,
        vol.Required("prompt"): vol.All(str, vol.Length(min=1, max=32000)),
        vol.Required("model"): vol.All(str, vol.Length(min=1)),
        vol.Optional("camera_entity_id"): cv.entity_id,
        vol.Optional("system_prompt"): str,
        vol.Optional("priority"): vol.All(vol.Coerce(int), vol.Range(min=0, max=9)),
        vol.Optional("tags"): [str],
        vol.Optional("timeout", default=DEFAULT_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=3600)
        ),
    }
)
DETECT_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): str,
        vol.Required("camera_entity_id"): cv.entity_id,
        vol.Required("model"): vol.All(str, vol.Length(min=1)),
        vol.Optional("conf", default=0.25): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
        vol.Optional("priority"): vol.All(vol.Coerce(int), vol.Range(min=0, max=9)),
        vol.Optional("tags"): [str],
        vol.Optional("timeout", default=DEFAULT_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=3600)
        ),
    }
)
IMAGE_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): str,
        vol.Required("prompt"): vol.All(str, vol.Length(min=1, max=32000)),
        vol.Optional("model", default="flux-schnell-q4ks-img"): str,
        vol.Optional("width", default=512): vol.All(vol.Coerce(int), vol.Range(min=64, max=2048)),
        vol.Optional("height", default=512): vol.All(vol.Coerce(int), vol.Range(min=64, max=2048)),
        vol.Optional("priority"): vol.All(vol.Coerce(int), vol.Range(min=0, max=9)),
        vol.Optional("tags"): [str],
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register automation actions."""

    async def chat(call: ServiceCall) -> dict:
        entry = _get_entry(hass, call.data.get("config_entry_id"))
        content = call.data["prompt"]
        camera_entity = call.data.get("camera_entity_id")
        if camera_entity:
            try:
                image = await camera.async_get_image(hass, camera_entity)
            except Exception as err:
                raise HomeAssistantError(f"Could not get camera image: {err}") from err
            content = [
                {"type": "text", "text": content},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image.content_type};base64,{base64.b64encode(image.content).decode('ascii')}"
                    },
                },
            ]
        messages = []
        if call.data.get("system_prompt"):
            messages.append({"role": "system", "content": call.data["system_prompt"]})
        messages.append({"role": "user", "content": content})
        payload = {"model": call.data["model"], "messages": messages, "timeout": call.data["timeout"]}
        _add_clanker_options(payload, call.data)
        return await _submit_and_wait(hass, entry, "/v1/chat/completions", payload, call.data["timeout"])

    async def generate_image(call: ServiceCall) -> dict:
        entry = _get_entry(hass, call.data.get("config_entry_id"))
        payload = {
            "model": call.data["model"],
            "prompt": call.data["prompt"],
            "width": call.data["width"],
            "height": call.data["height"],
        }
        _add_clanker_options(payload, call.data)
        return await _submit_and_wait(hass, entry, "/v1/images/generations", payload, DEFAULT_TIMEOUT)

    hass.services.async_register(
        DOMAIN, "chat", chat, schema=vol.All(CHAT_SCHEMA, _with_entry), supports_response=SupportsResponse.ONLY
    )
    async def detect_objects(call: ServiceCall) -> dict:
        entry = _get_entry(hass, call.data.get("config_entry_id"))
        try:
            image = await camera.async_get_image(hass, call.data["camera_entity_id"])
        except Exception as err:
            raise HomeAssistantError(f"Could not get camera image: {err}") from err

        form = aiohttp.FormData()
        form.add_field(
            "file", image.content, filename="camera_image", content_type=image.content_type
        )
        form.add_field("model", call.data["model"])
        form.add_field("conf", str(call.data["conf"]))
        options = {key: call.data[key] for key in ("priority", "tags") if key in call.data}
        if options:
            form.add_field("clanker", json.dumps(options))
        return await _submit_and_wait(
            hass, entry, "/v1/images/detect", form, call.data["timeout"]
        )

    hass.services.async_register(
        DOMAIN, "generate_image", generate_image,
        schema=vol.All(IMAGE_SCHEMA, _with_entry), supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, "detect_objects", detect_objects,
        schema=vol.All(DETECT_SCHEMA, _with_entry), supports_response=SupportsResponse.ONLY
    )
    return True


def _with_entry(data):
    """Require a selected integration entry."""
    if not data.get("config_entry_id"):
        raise vol.Invalid("config_entry_id is required")
    return data


def _get_entry(hass: HomeAssistant, entry_id: str | None) -> ConfigEntry:
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if entry is None or entry.domain != DOMAIN:
        raise HomeAssistantError("Select a valid Clanker AI configuration entry")
    return entry


def _add_clanker_options(payload: dict, data: dict) -> None:
    options = {key: data[key] for key in ("priority", "tags") if key in data}
    if options:
        payload["clanker"] = options


async def _submit_and_wait(hass, entry, path: str, payload: dict, timeout: int) -> dict:
    """Submit a queued job and return its terminal job response."""
    session = async_get_clientsession(hass)
    base_url = entry.options.get(CONF_URL, entry.data[CONF_URL])
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        request_payload = {"data": payload} if isinstance(payload, aiohttp.FormData) else {"json": payload}
        async with session.post(
            f"{base_url}{path}", **request_payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            response.raise_for_status()
            accepted = await response.json()
        job_id = accepted.get("id") if isinstance(accepted, dict) else None
        if not job_id:
            raise HomeAssistantError("Clanker AI returned no job ID")
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(POLL_INTERVAL)
            async with session.get(
                f"{base_url}/v1/jobs/{job_id}", timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                job = await response.json()
            if job.get("state") == "completed":
                return job
            if job.get("state") in ("failed", "cancelled", "discarded"):
                raise HomeAssistantError(job.get("error") or f"Clanker AI job {job.get('state')}")
        raise HomeAssistantError(f"Clanker AI job {job_id} timed out")
    except HomeAssistantError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        raise HomeAssistantError(f"Clanker AI request failed: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load the configured gateway."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the configured gateway."""
    return True
