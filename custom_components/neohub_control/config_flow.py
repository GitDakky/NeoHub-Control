"""Config flow for the NeoHub Control HACS companion integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from .const import ADDON_REPOSITORY_URL, ADDON_STORE_REDIRECT_URL, DOMAIN


class NeoHubControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create a helper entry that points users to the add-on install path."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Handle the initial user step."""
        await self.async_set_unique_id("neohub_control_hacs_companion")
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="NeoHub Control", data={})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "repository_url": ADDON_REPOSITORY_URL,
                "addon_store_url": ADDON_STORE_REDIRECT_URL,
            },
        )
