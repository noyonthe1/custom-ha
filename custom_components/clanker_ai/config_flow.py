"""Config flow for Clanker AI."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_URL

from .const import DEFAULT_URL, DOMAIN


class ClankerAIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the Clanker AI Gateway."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Allow changing the gateway URL from integration settings."""
        return ClankerAIOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Set the gateway URL."""
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            if not url.startswith(("http://", "https://")):
                return self.async_show_form(
                    step_id="user", data_schema=self._schema(url), errors={"base": "invalid_url"}
                )
            await self.async_set_unique_id(url)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=url, data={CONF_URL: url})
        return self.async_show_form(step_id="user", data_schema=self._schema())

    @staticmethod
    def _schema(url=DEFAULT_URL):
        return vol.Schema({vol.Required(CONF_URL, default=url): str})


class ClankerAIOptionsFlow(config_entries.OptionsFlow):
    """Options for an existing gateway connection."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Update the gateway URL."""
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            if not url.startswith(("http://", "https://")):
                return self.async_show_form(
                    step_id="init",
                    data_schema=ClankerAIConfigFlow._schema(url),
                    errors={"base": "invalid_url"},
                )
            return self.async_create_entry(title="", data={CONF_URL: url})

        url = self.config_entry.options.get(
            CONF_URL, self.config_entry.data.get(CONF_URL, DEFAULT_URL)
        )
        return self.async_show_form(
            step_id="init", data_schema=ClankerAIConfigFlow._schema(url)
        )
