"""Configure the camera vision server."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_URL

from .const import DOMAIN


class CameraVisionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a server connection."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            if not user_input[CONF_URL].startswith(("http://", "https://")):
                return self.async_show_form(step_id="user", data_schema=self._schema(user_input), errors={"base": "invalid_url"})
            await self.async_set_unique_id(user_input[CONF_URL].rstrip("/"))
            self._abort_if_unique_id_configured()
            user_input[CONF_URL] = user_input[CONF_URL].rstrip("/")
            return self.async_create_entry(title=user_input[CONF_URL], data=user_input)
        return self.async_show_form(step_id="user", data_schema=self._schema())

    @staticmethod
    def _schema(values=None):
        values = values or {}
        return vol.Schema({
            vol.Required(CONF_URL, default=values.get(CONF_URL, "http://")): str,
            vol.Required(CONF_API_KEY): str,
        })
