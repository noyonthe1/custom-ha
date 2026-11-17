"""Config flow for Clanker AI."""

from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_URL

from .const import CONF_FALLBACK_URL, DEFAULT_URL, DOMAIN


def _normalize(data):
    result = {}
    for key in (CONF_URL, CONF_FALLBACK_URL):
        url = data.get(key, "").strip().rstrip("/")
        if url:
            try:
                parts = urlsplit(url)
                if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
                    raise ValueError
                parts.port
            except ValueError as err:
                raise vol.Invalid("Invalid URL") from err
        elif key == CONF_URL:
            raise vol.Invalid("Gateway URL is required")
        result[key] = url
    return result


class ClankerAIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the Clanker AI Gateway."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Allow changing the gateway URL from integration settings."""
        return ClankerAIOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Set the gateway URL."""
        if user_input is not None:
            try:
                data = _normalize(user_input)
            except vol.Invalid:
                return self.async_show_form(
                    step_id="user", data_schema=self._schema(**user_input), errors={"base": "invalid_url"}
                )
            await self.async_set_unique_id(data[CONF_URL])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=data[CONF_URL], data=data)
        return self.async_show_form(step_id="user", data_schema=self._schema())

    @staticmethod
    def _schema(url=DEFAULT_URL, fallback_url=""):
        return vol.Schema({vol.Required(CONF_URL, default=url): str, vol.Optional(CONF_FALLBACK_URL, default=fallback_url): str})


class ClankerAIOptionsFlow(config_entries.OptionsFlow):
    """Options for an existing gateway connection."""

    async def async_step_init(self, user_input=None):
        """Update the gateway URL."""
        if user_input is not None:
            try:
                data = _normalize(user_input)
            except vol.Invalid:
                return self.async_show_form(
                    step_id="init",
                    data_schema=ClankerAIConfigFlow._schema(**user_input),
                    errors={"base": "invalid_url"},
                )
            return self.async_create_entry(title="", data=data)

        url = self.config_entry.options.get(
            CONF_URL, self.config_entry.data.get(CONF_URL, DEFAULT_URL)
        )
        fallback = self.config_entry.options.get(CONF_FALLBACK_URL, self.config_entry.data.get(CONF_FALLBACK_URL, ""))
        return self.async_show_form(step_id="init", data_schema=ClankerAIConfigFlow._schema(url, fallback))
