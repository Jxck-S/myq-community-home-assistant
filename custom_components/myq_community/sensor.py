"""Sensors for the latest myQ Community access event."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from myqcommunity import HistoryEvent

from .coordinator import MyQCommunityConfigEntry
from .entity import MyQCommunityEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyQCommunityConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the myQ Community sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for community in coordinator.communities:
        entities += [
            LastAccessSensor(coordinator, community),
            LastAccessTimeSensor(coordinator, community),
        ]
    async_add_entities(entities)


class _LastEventMixin(MyQCommunityEntity):
    @property
    def last_event(self) -> HistoryEvent | None:
        history = self.community_data.history
        return history[0] if history else None


class LastAccessSensor(_LastEventMixin, SensorEntity):
    """The latest access event, e.g. "Gate - unlocked"."""

    _attr_icon = "mdi:door-open"

    def __init__(self, coordinator, community) -> None:
        super().__init__(coordinator, community)
        self._attr_name = "Last Access"
        self._attr_unique_id = f"myq_community_last_access_{community.id}"

    @property
    def native_value(self) -> str | None:
        e = self.last_event
        return f"{e.device_name} - {e.event}"[:255] if e else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not (e := self.last_event):
            return None
        return {
            "event": e.event,
            "device": e.device_name,
            "serial_number": e.serial_number,
            "timestamp": dt_util.parse_datetime(e.timestamp) if e.timestamp else None,
        }


class LastAccessTimeSensor(_LastEventMixin, SensorEntity):
    """When the latest access event happened (from myQ, not when Home Assistant noticed it)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:door-closed-lock"

    def __init__(self, coordinator, community) -> None:
        super().__init__(coordinator, community)
        self._attr_name = "Last Access Time"
        self._attr_unique_id = f"myq_community_last_access_time_{community.id}"

    @property
    def native_value(self) -> datetime | None:
        e = self.last_event
        return dt_util.parse_datetime(e.timestamp) if e and e.timestamp else None
