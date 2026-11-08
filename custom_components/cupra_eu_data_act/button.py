"""Button platform: device actions such as manual portal refresh."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EudaConfigEntry
from .entity import EudaEntity

# Coordinator owns all portal I/O; entities never call the API directly.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EudaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([EudaRefreshButton(coordinator)])


class EudaRefreshButton(EudaEntity, ButtonEntity):
    """Fetch the latest portal dataset on demand from the device page."""

    _attr_translation_key = "refresh"
    _attr_icon = "mdi:cloud-sync"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_refresh"

    @property
    def available(self) -> bool:
        """Stay pressable even before the first dataset arrives."""
        return True

    async def async_press(self) -> None:
        """Query the EU Data Act portal immediately."""
        await self.coordinator.async_refresh()
