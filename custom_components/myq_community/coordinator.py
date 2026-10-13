"""Data coordinator for myQ Community: devices + recent history per community."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from myqcommunity import Community, Device, HistoryEvent, MyQAuthError, MyQCommunity, MyQRequestError

from .const import DOMAIN, HISTORY_LIMIT, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type MyQCommunityConfigEntry = ConfigEntry[MyQCommunityCoordinator]


@dataclass
class CommunityData:
    devices: list[Device] = field(default_factory=list)
    history: list[HistoryEvent] = field(default_factory=list)  # newest first


class MyQCommunityCoordinator(DataUpdateCoordinator[dict[str, CommunityData]]):
    """Fetches devices and access history for every community on the account."""

    config_entry: MyQCommunityConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MyQCommunityConfigEntry,
        client: MyQCommunity,
        communities: list[Community],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.communities = communities

    async def _async_update_data(self) -> dict[str, CommunityData]:
        try:
            return {
                c.id: CommunityData(
                    devices=await self.client.devices(c.id),
                    history=await self.client.history(c.id, limit=HISTORY_LIMIT),
                )
                for c in self.communities
            }
        except MyQAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MyQRequestError as err:
            raise UpdateFailed(str(err)) from err
