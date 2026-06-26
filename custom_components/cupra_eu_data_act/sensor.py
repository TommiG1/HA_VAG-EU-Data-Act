"""Sensor platform: curated sensors + raw diagnostic data points."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EudaConfigEntry
from .const import raw_unique_id
from .coordinator import EudaCoordinator
from .data import (
    CURATED_BINARY_DOTTED,
    CURATED_BINARY_FLAT,
    CURATED_SENSORS_DOTTED,
    CURATED_SENSORS_FLAT,
    UNIT_RESOLVERS,
    CuratedSensor,
    DataPoint,
    curated_translation_key,
    datapoint_freshness_attributes,
    detect_dataset_format,
    field_coverage,
    find_by_field,
    friendly_name,
    is_raw_metadata_field,
    is_sentinel,
    is_superseded_instrument_cluster_field,
    is_usable_reading,
    last_connected_time,
    latest_captured_time,
    resolve_distance_unit,
    resolve_distance_unit_from_companion_fields,
    resolve_primary_range_unit,
    shorten_enum_label,
    total_charged_energy_kwh,
)
from .entity import EudaEntity

_LAST_CONNECTED_CURATED_FIELDS = frozenset(
    {"mileage.value.timestamp", "mileage.timestamp"}
)

_CHARGE_RATE_FIELDS = frozenset(
    {"battery_state_report.charge_rate", "actual_charge_rate"}
)

_REMAINING_CHARGE_TIME_FIELDS = frozenset(
    {
        "battery_state_report.remaining_charging_time_complete",
        "battery_state_report.remaining_charging_time_bulk",
        "remaining_charging_time",
    }
)


def _charging_time_is_applicable(points: dict[str, DataPoint]) -> bool:
    """Whether a remaining-charge-time value describes an active charge."""
    scenario = find_by_field(points, "charging_state_report.charging_scenario")
    if scenario and str(scenario.value).endswith("_OFF"):
        return False

    power = find_by_field(points, "battery_state_report.charge_power")
    if power is None:
        power = find_by_field(points, "charging_power")
    if power is not None:
        try:
            if float(power.value) <= 0:
                return False
        except (TypeError, ValueError):
            pass

    state = find_by_field(points, "charging_state_report.current_charge_state")
    if state and "CHARGING" in str(state.value):
        return True

    # Flat/PHEV payloads do not always expose the same companion fields. If no
    # inactive signal exists, keep the portal's remaining time value.
    return scenario is None and power is None and state is None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EudaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator

    # Status sensor is always present, even before the first dataset arrives,
    # so the user sees a device with a state explaining what's happening.
    async_add_entities(
        [
            EudaStatusSensor(coordinator),
            EudaDaysUntilSubscriptionExpiresSensor(coordinator),
            EudaMinutesSinceLastSnapshotSensor(coordinator),
            EudaLastVehicleUpdateSensor(coordinator),
            EudaLastConnectedSensor(coordinator),
            EudaDatasetGeneratedSensor(coordinator),
            EudaUncuratedFieldsCountSensor(coordinator),
        ]
    )

    added_curated: set[str] = set()
    added_raw_keys: set[str] = set()
    # Pin the detected format after the first non-empty refresh; later
    # datasets that mix formats won't flip the chosen registry.
    format_state: dict[str, str | None] = {"format": None}

    @callback
    def _discover() -> None:
        points: dict[str, DataPoint] = coordinator.data or {}
        if not points:
            return

        if format_state["format"] is None:
            format_state["format"] = detect_dataset_format(points)
        format_type = format_state["format"]

        curated_sensors = (
            CURATED_SENSORS_DOTTED if format_type == "dotted" else CURATED_SENSORS_FLAT
        )
        curated_binary = (
            CURATED_BINARY_DOTTED if format_type == "dotted" else CURATED_BINARY_FLAT
        )
        binary_fields = {b.field_name for b in curated_binary}
        curated_sensor_fields = {s.field_name for s in curated_sensors}
        present_fields = {dp.field_name for dp in points.values()}

        new_entities: list[SensorEntity] = []

        for curated in curated_sensors:
            if curated.field_name in added_curated:
                continue
            if curated.field_name in _LAST_CONNECTED_CURATED_FIELDS:
                continue
            if is_raw_metadata_field(curated.field_name):
                continue
            if is_superseded_instrument_cluster_field(
                curated.field_name, present_fields
            ):
                continue
            if curated.field_name == "last_charge_kwh":
                if total_charged_energy_kwh(points) is not None:
                    new_entities.append(EudaCuratedSensor(coordinator, curated))
                    added_curated.add(curated.field_name)
                continue
            # Timestamp sensors track ".timestamp" on a base field (e.g.
            # mileage.value.timestamp). Create once the base mileage field is
            # present — timestampUtc is often missing on Cupra/MEB payloads.
            if ".timestamp" in curated.field_name:
                base_field = curated.field_name.replace(".timestamp", "")
                if find_by_field(points, base_field) is not None:
                    new_entities.append(EudaCuratedSensor(coordinator, curated))
                    added_curated.add(curated.field_name)
            elif curated.field_name in present_fields:
                new_entities.append(EudaCuratedSensor(coordinator, curated))
                added_curated.add(curated.field_name)

        for key, dp in points.items():
            if key in added_raw_keys:
                continue
            if dp.field_name in curated_sensor_fields or dp.field_name in binary_fields:
                continue
            if is_raw_metadata_field(dp.field_name):
                continue
            new_entities.append(EudaRawSensor(coordinator, key))
            added_raw_keys.add(key)

        if new_entities:
            async_add_entities(new_entities)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))


class EudaCuratedSensor(EudaEntity, SensorEntity):
    """A curated, well-typed sensor (enabled by default)."""

    def __init__(self, coordinator: EudaCoordinator, curated: CuratedSensor) -> None:
        super().__init__(coordinator)
        self._curated = curated
        self._last_charge_total_kwh: float | None = None
        self._attr_unique_id = f"{coordinator.vin}_{curated.field_name}"
        self._attr_translation_key = curated_translation_key(
            curated.field_name, curated.translation_key
        )
        if curated.icon:
            self._attr_icon = curated.icon
        if curated.device_class:
            self._attr_device_class = SensorDeviceClass(curated.device_class)
        if curated.state_class:
            self._attr_state_class = SensorStateClass(curated.state_class)
        if curated.suggested_display_precision is not None:
            self._attr_suggested_display_precision = curated.suggested_display_precision

    def _apply_transform(self, value):
        """Apply configured transform to the raw value."""
        if value is None or not self._curated.transform:
            return value

        transform = self._curated.transform

        if transform == "duration_s":
            # Already handled by parse_duration_seconds in parse_value
            return value

        if transform == "duration_min":
            try:
                return round(float(value) / 60, 1)
            except (TypeError, ValueError):
                return None

        if transform == "decikelvin_to_celsius":
            from .data import decikelvin_to_celsius

            return decikelvin_to_celsius(str(value))

        if transform == "hectometers_to_km":
            from .data import hectometers_to_km

            return hectometers_to_km(value)

        return value

    def _sum_fallback_value(self) -> float | int | None:
        """Sum the curated sensor's ``sum_fallback_fields`` into a total.

        Used when the sensor's own field carries no usable reading. Only usable
        numeric components contribute; returns ``None`` when none are present so
        the sensor stays unknown rather than reporting a misleading zero.
        """
        points = self.coordinator.data or {}
        total = 0.0
        found = False
        for fname in self._curated.sum_fallback_fields:
            dp = find_by_field(points, fname)
            if dp is None or not is_usable_reading(dp.value, fname):
                continue
            try:
                total += float(dp.value)
            except (TypeError, ValueError):
                continue
            found = True
        if not found:
            return None
        return int(total) if total.is_integer() else total

    def _source_datapoint(self) -> DataPoint | None:
        """Return the portal data point backing ``native_value``."""
        points = self.coordinator.data or {}
        field_name = self._curated.field_name

        if ".timestamp" in field_name:
            return find_by_field(points, field_name.replace(".timestamp", ""))

        if field_name == "last_charge_kwh":
            for energy_field in (
                "battery_state_report.charge_energy",
                "charged_energy",
            ):
                dp = find_by_field(points, energy_field)
                if dp is not None and not is_sentinel(dp.value, dp.field_name):
                    return dp
            return None

        if field_name in _REMAINING_CHARGE_TIME_FIELDS and not _charging_time_is_applicable(
            points
        ):
            return None

        dp = find_by_field(
            points,
            field_name,
            prefer_max_value=self._curated.monotonic,
        )
        if dp is None or is_sentinel(dp.value, field_name):
            return None
        return dp

    @property
    def native_value(self):
        if ".timestamp" in self._curated.field_name:
            base_field = self._curated.field_name.replace(".timestamp", "")
            dp = find_by_field(self.coordinator.data or {}, base_field)
            if dp and dp.timestamp:
                return self._sticky(dp.timestamp)
            return self._sticky(None)

        field_name = self._curated.field_name
        if field_name == "last_charge_kwh":
            total = total_charged_energy_kwh(self.coordinator.data or {})
            if total is None:
                return self._sticky(None)
            if self._last_charge_total_kwh is None:
                self._last_charge_total_kwh = total
                return self._sticky(None)
            delta = total - self._last_charge_total_kwh
            self._last_charge_total_kwh = total
            if delta > 0:
                return self._sticky(round(delta, 3))
            # Ignore resets / plateaus and keep the previous "last charge" value.
            return self._sticky(None)

        if field_name in _REMAINING_CHARGE_TIME_FIELDS and not _charging_time_is_applicable(
            self.coordinator.data or {}
        ):
            return None

        dp = find_by_field(
            self.coordinator.data or {},
            field_name,
            prefer_max_value=self._curated.monotonic,
        )

        # When the portal sends this field empty (e.g. combined cruising range on
        # PHEVs) but still reports its components, reconstruct the total from the
        # declared fallback fields. A usable portal value always takes precedence.
        if self._curated.sum_fallback_fields and (
            dp is None or not is_usable_reading(dp.value, field_name)
        ):
            summed = self._sum_fallback_value()
            if summed is not None:
                return self._sticky(summed)

        if not dp:
            return self._sticky(None)

        # Sentinels are filtered against the raw portal value (before
        # transforms) so e.g. fuel-consumption /10 doesn't turn 4294967295
        # into a "plausible" 429496729.5.
        if is_sentinel(dp.value, field_name):
            return self._sticky(None)

        raw_value = dp.value

        # Apply transforms if specified
        if self._curated.transform:
            if self._curated.transform == "decikelvin_to_celsius":
                from .data import decikelvin_to_celsius

                transformed = decikelvin_to_celsius(dp.raw_value)
                return self._sticky(transformed)

            elif self._curated.transform == "abs":
                from .data import abs_value

                transformed = abs_value(raw_value)
                return self._sticky(transformed)

            elif self._curated.transform == "fuel_consumption":
                from .data import fuel_consumption_l_per_1000km_to_l_per_100km

                transformed = fuel_consumption_l_per_1000km_to_l_per_100km(raw_value)
                return self._sticky(transformed)

            elif self._curated.transform == "electr_consumption":
                from .data import electr_consumption_kwh_per_1000km_to_kwh_per_100km

                transformed = electr_consumption_kwh_per_1000km_to_kwh_per_100km(
                    raw_value
                )
                return self._sticky(transformed)

            elif self._curated.transform == "hectometers_to_km":
                from .data import hectometers_to_km

                transformed = hectometers_to_km(raw_value)
                return self._sticky(transformed)

            elif self._curated.transform == "deci_kwh":
                from .data import deci_kwh_to_kwh

                transformed = deci_kwh_to_kwh(raw_value)
                return self._sticky(transformed)

            elif self._curated.transform == "iso_timestamp":
                from .data import parse_timestamp

                transformed = parse_timestamp(raw_value)
                return self._sticky(transformed)

            elif self._curated.transform == "duration_min":
                try:
                    transformed = round(float(raw_value) / 60, 1)
                except (TypeError, ValueError):
                    transformed = None
                return self._sticky(transformed)

        if self._curated.translation_key:
            return self._sticky(raw_value)
        if isinstance(raw_value, str):
            return self._sticky(
                shorten_enum_label(self._curated.field_name, raw_value)
            )
        return self._sticky(raw_value)

    @property
    def extra_state_attributes(self) -> dict:
        return datapoint_freshness_attributes(
            self._source_datapoint(),
            now=dt_util.utcnow(),
        )

    @property
    def native_unit_of_measurement(self) -> str | None:
        # When a companion unit field is declared (e.g. mileage.unit), resolve
        # the unit at runtime so miles vs km is reported correctly per vehicle;
        # otherwise use the static curated unit.
        cur = self._curated
        points = self.coordinator.data or {}
        unit_candidates: list[str] = []
        if cur.unit_field:
            unit_candidates.append(cur.unit_field)
        unit_candidates.extend(cur.unit_fields)
        if unit_candidates:
            resolver = UNIT_RESOLVERS.get(cur.unit_resolver, resolve_distance_unit)
            if cur.unit_fields and cur.unit_resolver == "distance":
                resolved = resolve_distance_unit_from_companion_fields(
                    points, *unit_candidates
                )
                if resolved:
                    stable = self._sticky_unit(resolved)
                    if stable is not None:
                        return stable
            else:
                for field in unit_candidates:
                    dp = find_by_field(points, field)
                    if dp is None:
                        continue
                    resolved = resolver(dp.value)
                    if resolved:
                        consider = resolved
                        if cur.field_name in _CHARGE_RATE_FIELDS:
                            value_dp = find_by_field(points, cur.field_name)
                            if value_dp is None or not is_usable_reading(
                                value_dp.value, cur.field_name
                            ):
                                consider = None
                        stable = self._sticky_unit(consider)
                        if stable is not None:
                            return stable
        return cur.unit


class EudaRawSensor(EudaEntity, SensorEntity):
    """A raw data point exposed as a disabled-by-default diagnostic sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: EudaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        dp = coordinator.data[key]
        self._key = key
        # Namespace by VIN: dataset keys are shared across vehicles, so a bare
        # key collides between config entries (see raw_unique_id / migration).
        self._attr_unique_id = raw_unique_id(coordinator.vin, key)
        self._attr_name = friendly_name(dp.field_name, dp.description)
        self._is_primary_range = dp.field_name == "value_of_the_primary_range"
        # only attach a unit when the value is numeric
        if self._is_primary_range:
            self._attr_device_class = SensorDeviceClass.DISTANCE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif dp.unit and dp.type_hint in ("int", "float"):
            self._attr_native_unit_of_measurement = dp.unit

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self._is_primary_range:
            resolved = resolve_primary_range_unit(self.coordinator.data or {})
            return resolved or "km"
        return getattr(self, "_attr_native_unit_of_measurement", None)

    @property
    def native_value(self):
        dp = (self.coordinator.data or {}).get(self._key)
        if not dp:
            return self._sticky(None)
        value = self._filtered(dp.value, dp.field_name)
        if isinstance(value, str):
            return shorten_enum_label(dp.field_name, value)
        return value

    @property
    def extra_state_attributes(self) -> dict:
        dp = (self.coordinator.data or {}).get(self._key)
        if not dp:
            return {}
        attrs = {"key": dp.key, "field_name": dp.field_name}
        if dp.description:
            attrs["description"] = dp.description
        if dp.cluster:
            attrs["cluster"] = dp.cluster
        attrs.update(
            datapoint_freshness_attributes(dp, now=dt_util.utcnow())
        )
        return attrs


class EudaStatusSensor(EudaEntity, SensorEntity):
    """Always-present diagnostic sensor showing the integration's portal state.

    Created at setup so the device exists in HA even before the first dataset
    arrives, with a state that tells the user why their other entities haven't
    appeared yet.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-sync-outline"
    _attr_translation_key = "integration_status"

    def __init__(self, coordinator: EudaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_integration_status"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str | None:
        return self.coordinator.status_label

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {
            "empty_snapshot_count": self.coordinator.empty_snapshot_count,
            "consecutive_server_errors": self.coordinator.consecutive_server_errors,
            "next_retry_minutes": int(
                self.coordinator.update_interval.total_seconds() // 60
            ),
        }
        if self.coordinator.latest_dataset and self.coordinator.latest_dataset.captured_at:
            attrs["latest_dataset_captured_at"] = (
                self.coordinator.latest_dataset.captured_at.isoformat()
            )
        if self.coordinator.latest_dataset_name:
            attrs["latest_dataset_name"] = self.coordinator.latest_dataset_name
        if self.coordinator.last_download_attempts:
            attrs["last_download_attempts"] = self.coordinator.last_download_attempts
        cached = self.coordinator.cached_datasets()
        if cached:
            attrs["cached_datasets"] = cached
        if self.coordinator.subscription_created_on:
            attrs["subscription_created_on"] = (
                self.coordinator.subscription_created_on.isoformat()
            )
        if self.coordinator.listing_identifier:
            attrs["listing_identifier"] = self.coordinator.listing_identifier
        return attrs


class EudaDaysUntilSubscriptionExpiresSensor(EudaEntity, SensorEntity):
    """Diagnostic: estimated days until the portal subscription expires (~12 months)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:calendar-clock"
    _attr_translation_key = "days_until_subscription_expires"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EudaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_days_until_subscription_expires"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int | None:
        return self.coordinator.days_until_subscription_expires

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {}
        if self.coordinator.subscription_created_on:
            attrs["subscription_created_on"] = (
                self.coordinator.subscription_created_on.isoformat()
            )
        if self.coordinator.listing_identifier:
            attrs["listing_identifier"] = self.coordinator.listing_identifier
        return attrs


class EudaMinutesSinceLastSnapshotSensor(EudaEntity, SensorEntity):
    """Diagnostic: minutes since the last real vehicle snapshot."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-alert-outline"
    _attr_translation_key = "minutes_since_last_snapshot"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EudaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_minutes_since_last_snapshot"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int | None:
        return self.coordinator.minutes_since_last_snapshot

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {}
        if snap := self.coordinator.last_snapshot_at:
            attrs["last_snapshot_at"] = snap.isoformat()
        return attrs


class EudaLastVehicleUpdateSensor(EudaEntity, SensorEntity):
    """When the vehicle itself last reported data to the backend.

    Distinct from entity ``last_updated`` (portal poll time) and from
    ``dataset_generated`` (when the portal ZIP was created).
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:car-clock"
    _attr_translation_key = "last_vehicle_update"

    def __init__(self, coordinator: EudaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_last_vehicle_update"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self._sticky(latest_captured_time(self.coordinator.data or {}))


class EudaLastConnectedSensor(EudaEntity, SensorEntity):
    """When the vehicle last reported mileage / odometer to the backend.

    Registered at setup (not via discovery) so the entity stays linked in the
    registry. Many Cupra/MEB payloads omit ``timestampUtc`` on the mileage
    field; :func:`last_connected_time` falls back to car-captured timestamps.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock"

    def __init__(self, coordinator: EudaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_last_connected"
        self._attr_translation_key = "last_connected"

    @property
    def native_value(self):
        return self._sticky(last_connected_time(self.coordinator.data or {}))


class EudaDatasetGeneratedSensor(EudaEntity, SensorEntity):
    """When the portal generated the currently loaded dataset ZIP."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:database-clock"
    _attr_translation_key = "dataset_generated"

    def __init__(self, coordinator: EudaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_dataset_generated"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self._sticky(self.coordinator.dataset_created_at)


class EudaUncuratedFieldsCountSensor(EudaEntity, SensorEntity):
    """Diagnostic: count of dataset fields without a curated sensor mapping."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:format-list-numbered"
    _attr_translation_key = "uncurated_fields_count"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EudaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_uncurated_fields_count"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int | None:
        points = self.coordinator.data
        if not points:
            return None
        return field_coverage(points)["uncurated_count"]
