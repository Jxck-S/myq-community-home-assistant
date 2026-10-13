"""Lock entities for myQ Community gates, doors and smart locks."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later
from myqcommunity import Device, MyQAuthError, MyQError

from .coordinator import MyQCommunityConfigEntry
from .entity import MyQCommunityEntity

# Gates and access-panel doors re-lock themselves; show "unlocked" this long after opening
UNLOCKED_DISPLAY_SECONDS = 10
# Ignore repeat unlocks within this window
UNLOCK_COOLDOWN_SECONDS = 20


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyQCommunityConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a lock entity for each unlockable device."""
    coordinator = entry.runtime_data
    async_add_entities(
        (SmartLock if device.family == "remote_lock" else AccessPoint)(coordinator, community, device)
        for community in coordinator.communities
        for device in coordinator.data[community.id].devices
        if device.is_lock
    )


class MyQCommunityLock(MyQCommunityEntity, LockEntity):
    """A myQ Community device that can be unlocked."""

    def __init__(self, coordinator, community, device: Device) -> None:
        super().__init__(coordinator, community)
        self._device = device
        self._attr_name = device.name
        self._attr_unique_id = f"myq_community_lock_{device.serial_number}"
        self._attr_is_locked = True
        self._last_unlock = 0.0

    @property
    def available(self) -> bool:
        """Available when the coordinator is healthy and myQ doesn't report the device offline."""
        if not super().available:
            return False
        device = next(
            (d for d in self.community_data.devices if d.serial_number == self._device.serial_number), None
        )
        return device is not None and device.online is not False

    async def _call(self, verb: str, method, *args) -> None:
        try:
            ok = await method(self._community.id, *args)
        except MyQAuthError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"Failed to {verb} {self.name}: {err}") from err
        except MyQError as err:
            raise HomeAssistantError(f"Failed to {verb} {self.name}: {err}") from err
        if not ok:
            raise HomeAssistantError(f"Failed to {verb} {self.name}")

    async def async_unlock(self, **kwargs: Any) -> None:
        remaining = UNLOCK_COOLDOWN_SECONDS - (time.monotonic() - self._last_unlock)
        if remaining > 0:
            raise HomeAssistantError(f"{self.name} was just opened; try again in {int(remaining) + 1}s")
        await self._call("open", self.coordinator.client.unlock, self._device)
        self._last_unlock = time.monotonic()
        self._attr_is_locked = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()  # pick up the new history event


class AccessPoint(MyQCommunityLock):
    """A gate or access-panel door. Unlocking opens it; it re-locks on its own."""

    _cancel_relock = None

    async def async_lock(self, **kwargs: Any) -> None:
        """Gates and doors lock automatically; nothing to do."""

    async def async_unlock(self, **kwargs: Any) -> None:
        await super().async_unlock(**kwargs)
        if self._cancel_relock:
            self._cancel_relock()
        self._cancel_relock = async_call_later(self.hass, UNLOCKED_DISPLAY_SECONDS, self._relock)

    @callback
    def _relock(self, _now) -> None:
        self._cancel_relock = None
        self._attr_is_locked = True
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._cancel_relock:
            self._cancel_relock()
        await super().async_will_remove_from_hass()


class SmartLock(MyQCommunityLock):
    """A remote_lock smart lock. myQ doesn't report its state, so it shows the last command."""

    _attr_assumed_state = True

    async def async_lock(self, **kwargs: Any) -> None:
        await self._call("lock", self.coordinator.client.lock, self._device.serial_number)
        self._last_unlock = 0.0
        self._attr_is_locked = True
        self.async_write_ha_state()
