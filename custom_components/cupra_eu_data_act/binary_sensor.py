"""Binary sensor platform: curated boolean data points."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
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
    async_add_entities([EudaSnapshotStaleBinarySensor(coordinator)])
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
            else:
                # Only create the entity once the field decodes to an actual
                # on/off state, not just an unsupported/invalid sentinel —
                # fields for hardware the vehicle doesn't have (sunroof,
                # spoiler, …) otherwise become entities that can never hold
                # a state.
                dp = find_by_field(points, curated.field_name)
                if dp is None or decode_binary_state(
                    dp.value, curated.encoding, curated.invert
                ) is None:
                    continue
            new_entities.append(EudaBinarySensor(coordinator, curated))
            added.add(curated.field_name)

        if new_entities:
            async_add_entities(new_entities)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))


class EudaSnapshotStaleBinarySensor(EudaEntity, BinarySensorEntity):
    """On when vehicle telemetry is older than the stale-snapshot threshold.

    Uses car-captured time, not portal ZIP ``createdOn``, so a replay of old
    snapshots in fresh ZIP files still reports as stale (#77).
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-alert"
    _attr_translation_key = "snapshot_stale"

    def __init__(self, coordinator: EudaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_snapshot_stale"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.is_snapshot_stale

    @property
    def extra_state_attributes(self) -> dict:
        threshold = self.coordinator.stale_threshold
        attrs: dict = {
            # 0 = stale check turned off in the integration options.
            "stale_threshold_hours": (
                int(threshold.total_seconds() // 3600) if threshold else 0
            ),
        }
        if (minutes := self.coordinator.minutes_since_last_snapshot) is not None:
            attrs["minutes_since_last_snapshot"] = minutes
        if snap := self.coordinator.last_snapshot_at:
            attrs["last_snapshot_at"] = snap.isoformat()
        return attrs


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
