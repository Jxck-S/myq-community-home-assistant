"""The myQ Community integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.httpx_client import get_async_client
from myqcommunity import MyQAuthError, MyQCommunity, MyQRequestError, Token

from .const import CONF_TOKEN
from .coordinator import MyQCommunityConfigEntry, MyQCommunityCoordinator

PLATFORMS = [Platform.LOCK, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: MyQCommunityConfigEntry) -> bool:
    """Set up myQ Community from a config entry."""

    @callback
    def save_token(token: Token) -> None:
        # myQ issues a new refresh token on every refresh; keep the newest one
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_TOKEN: token.to_dict()})

    client = MyQCommunity(
        Token.from_dict(entry.data[CONF_TOKEN]),
        http=get_async_client(hass),
        on_token_refresh=save_token,
    )

    try:
        communities = await client.communities()
    except MyQAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except MyQRequestError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = MyQCommunityCoordinator(hass, entry, client, communities)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MyQCommunityConfigEntry) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.aclose()
    return unloaded
