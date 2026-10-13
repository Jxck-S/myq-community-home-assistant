"""Base entity for myQ Community."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from myqcommunity import Community

from .const import DOMAIN
from .coordinator import CommunityData, MyQCommunityCoordinator


class MyQCommunityEntity(CoordinatorEntity[MyQCommunityCoordinator]):
    """An entity belonging to one community. Named "<community> <entity name>"."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MyQCommunityCoordinator, community: Community) -> None:
        super().__init__(coordinator)
        self._community = community
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, community.id)},
            name=community.name,
            manufacturer="myQ Community",
        )

    @property
    def community_data(self) -> CommunityData:
        return self.coordinator.data.get(self._community.id) or CommunityData()
