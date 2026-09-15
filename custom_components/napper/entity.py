"""Base entity for the Napper integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NapperDataUpdateCoordinator
from .models import NapperBabyState


class NapperEntity(CoordinatorEntity[NapperDataUpdateCoordinator]):
    """Common behavior for a Napper baby entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NapperDataUpdateCoordinator,
        baby_id: str,
        key: str,
    ) -> None:
        super().__init__(coordinator, context=baby_id)
        self._baby_id = baby_id
        self._attr_unique_id = f"{baby_id}_{key}"
        baby = coordinator.data[baby_id].baby
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, baby.id)},
            manufacturer="Napper",
            name=baby.name,
        )

    @property
    def baby_state(self) -> NapperBabyState:
        """Return the latest state for this entity's baby."""
        return self.coordinator.data[self._baby_id]
