"""NeoHub Control HACS companion integration.

NeoHub Control runs as a Home Assistant add-on. This small custom
integration exists so the repository has a valid HACS integration layout and
can explain the correct add-on installation path from inside Home Assistant.
"""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ADDON_REPOSITORY_URL, ADDON_STORE_REDIRECT_URL, ISSUE_TRACKER_URL

_NOTIFICATION_ID = "neohub_control_addon_install"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the HACS companion entry."""
    persistent_notification.async_create(
        hass,
        (
            "NeoHub Control is a Home Assistant add-on repository, not a "
            "runtime HACS integration. HACS can install this helper, but it "
            "cannot run or update the add-on container.\n\n"
            "To install the working bridge, add this repository in "
            "Settings > Add-ons > Add-on Store > Repositories, then install "
            "the NeoHub Control add-on.\n\n"
            f"Repository: {ADDON_REPOSITORY_URL}\n\n"
            f"My Home Assistant add-on repository link: {ADDON_STORE_REDIRECT_URL}\n\n"
            f"Issues: {ISSUE_TRACKER_URL}"
        ),
        title="NeoHub Control add-on install required",
        notification_id=_NOTIFICATION_ID,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the HACS companion entry."""
    persistent_notification.async_dismiss(hass, _NOTIFICATION_ID)
    return True
