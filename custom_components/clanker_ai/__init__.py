"""Home Assistant actions for the Clanker AI Gateway."""

import asyncio
import base64
import json
import logging
from datetime import timedelta

import aiohttp
import voluptuous as vol
from homeassistant.components import camera, persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_FALLBACK_URL, DEFAULT_TIMEOUT, DOMAIN, POLL_INTERVAL

_LOGGER = logging.getLogger(__name__)

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


def _gateway_urls(entry):
    primary = entry.options.get(CONF_URL, entry.data[CONF_URL])
    fallback = entry.options.get(CONF_FALLBACK_URL, entry.data.get(CONF_FALLBACK_URL, ""))
    return [url for url in dict.fromkeys((primary, fallback)) if url]


async def _available_gateway(hass, entry):
    session = async_get_clientsession(hass)
    for url in _gateway_urls(entry):
        try:
            async with session.get(f"{url}/status", timeout=aiohttp.ClientTimeout(total=5)) as response:
                response.raise_for_status()
                status = await response.json()
                if isinstance(status, dict) and "gateway" in status:
                    return url
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            continue
    return None


def _notify_gateway(hass, entry, available):
    notification_id = f"{DOMAIN}_gateway_{entry.entry_id}"
    if available:
        persistent_notification.async_dismiss(hass, notification_id)
    else:
        persistent_notification.async_create(
            hass, "The configured gateways are unreachable. Check the gateway and its URLs.",
            title="Clanker AI gateway unavailable", notification_id=notification_id,
        )


async def _cancel_job(session, base_url, job_id):
    try:
        async with session.delete(
            f"{base_url}/v1/jobs/{job_id}", timeout=aiohttp.ClientTimeout(total=3)
        ) as response:
            response.raise_for_status()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        _LOGGER.warning("Could not cancel Clanker AI job %s at %s", job_id, base_url)


async def _submit_and_wait(hass, entry, path: str, payload, timeout: int) -> dict:
    """Submit once, then poll and cancel on the same gateway."""
    session = async_get_clientsession(hass)
    base_url = None
    job_id = None
    terminal = False
    try:
        async with asyncio.timeout(timeout):
            base_url = await _available_gateway(hass, entry)
            _notify_gateway(hass, entry, bool(base_url))
            if not base_url:
                raise HomeAssistantError("Clanker AI gateways are unavailable")
            request_payload = {"data": payload} if isinstance(payload, aiohttp.FormData) else {"json": payload}
            async with session.post(
                f"{base_url}{path}", **request_payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                accepted = await response.json()
            accepted_id = accepted.get("id") if isinstance(accepted, dict) else None
            if not isinstance(accepted_id, str) or not accepted_id:
                raise HomeAssistantError("Clanker AI returned no job ID")
            job_id = accepted_id
            while True:
                await asyncio.sleep(POLL_INTERVAL)
                try:
                    async with session.get(
                        f"{base_url}/v1/jobs/{job_id}", timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        response.raise_for_status()
                        job = await response.json()
                except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
                    continue
                if not isinstance(job, dict):
                    raise HomeAssistantError(f"Invalid response for Clanker AI job {job_id}")
                if job.get("state") == "completed":
                    terminal = True
                    return job
                if job.get("state") in ("failed", "cancelled", "discarded"):
                    terminal = True
                    raise HomeAssistantError(job.get("error") or f"Clanker AI job {job.get('state')}")
    except asyncio.TimeoutError as err:
        raise HomeAssistantError(f"Clanker AI request timed out{f' (job {job_id})' if job_id else ''}") from err
    except (aiohttp.ClientError, ValueError) as err:
        raise HomeAssistantError(f"Clanker AI request failed: {err}") from err
    finally:
        if job_id and not terminal:
            await _cancel_job(session, base_url, job_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Monitor the configured gateways."""
    async def check_gateway(_now=None):
        _notify_gateway(hass, entry, bool(await _available_gateway(hass, entry)))

    entry.async_on_unload(async_track_time_interval(hass, check_gateway, timedelta(minutes=1)))
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    hass.async_create_task(check_gateway())
    return True


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    _notify_gateway(hass, entry, bool(await _available_gateway(hass, entry)))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the configured gateway."""
    persistent_notification.async_dismiss(hass, f"{DOMAIN}_gateway_{entry.entry_id}")
    return True
