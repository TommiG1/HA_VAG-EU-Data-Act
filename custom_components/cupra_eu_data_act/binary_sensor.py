"""Binary sensor platform: curated boolean data points."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EudaConfigEntry
from .coordinator import EudaCoordinator
from .data import (
    CURATED_BINARY_DOTTED,
    CURATED_BINARY_FLAT,
    CuratedBinary,
    DataPoint,
    charging_signal_present,
    curated_translation_key,
    datapoint_freshness_attributes,
    decode_binary_state,
    detect_dataset_format,
    find_by_field,
    is_actively_charging,
)
from .entity import EudaEntity

# Synthetic curated field — not present in portal payloads.
_DERIVED_CHARGING_FIELD = "charging"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EudaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    added: set[str] = set()
    format_state: dict[str, str | None] = {"format": None}

    @callback
    def _discover() -> None:
        points: dict[str, DataPoint] = coordinator.data or {}
        if not points:
            return

        if format_state["format"] is None:
            format_state["format"] = detect_dataset_format(points)
        format_type = format_state["format"]

        curated_binary = (
            CURATED_BINARY_DOTTED if format_type == "dotted" else CURATED_BINARY_FLAT
        )
        present_fields = {dp.field_name for dp in points.values()}

        new_entities: list[EudaBinarySensor] = []
        for curated in curated_binary:
            if curated.field_name in added:
                continue
            if curated.field_name == _DERIVED_CHARGING_FIELD:
                if not charging_signal_present(points):
                    continue
            elif curated.field_name not in present_fields:
                continue
            new_entities.append(EudaBinarySensor(coordinator, curated))
            added.add(curated.field_name)

        if new_entities:
            async_add_entities(new_entities)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))


class EudaBinarySensor(EudaEntity, BinarySensorEntity):
    """A curated boolean sensor."""

    def __init__(self, coordinator: EudaCoordinator, curated: CuratedBinary) -> None:
        super().__init__(coordinator)
        self._curated = curated
        self._attr_unique_id = f"{coordinator.vin}_{curated.field_name}"
        self._attr_translation_key = curated_translation_key(curated.field_name)
        if curated.icon:
            self._attr_icon = curated.icon
        if curated.device_class:
            self._attr_device_class = BinarySensorDeviceClass(curated.device_class)

    @property
    def is_on(self) -> bool | None:
        if self._curated.field_name == _DERIVED_CHARGING_FIELD:
            return self._sticky(is_actively_charging(self.coordinator.data or {}))
        dp = find_by_field(self.coordinator.data or {}, self._curated.field_name)
        result = (
            decode_binary_state(
                dp.value, self._curated.encoding, self._curated.invert
            )
            if dp is not None
            else None
        )
        return self._sticky(result)

    @property
    def extra_state_attributes(self) -> dict:
        if self._curated.field_name == _DERIVED_CHARGING_FIELD:
            # Prefer charge-state freshness; fall back to power fields.
            for field_name in (
                "charging_state_report.current_charge_state",
                "charging_state",
                "battery_state_report.charge_power",
                "charging_power",
            ):
                dp = find_by_field(self.coordinator.data or {}, field_name)
                if dp is not None:
                    return datapoint_freshness_attributes(dp, now=dt_util.utcnow())
            return {}
        dp = find_by_field(self.coordinator.data or {}, self._curated.field_name)
        return datapoint_freshness_attributes(dp, now=dt_util.utcnow())
