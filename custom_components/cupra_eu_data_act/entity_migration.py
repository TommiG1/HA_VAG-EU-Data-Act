"""Entity registry migrations for translation_key / naming fixes."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_VIN, DOMAIN
from .data import (
    CURATED_BINARY_DOTTED,
    CURATED_BINARY_FLAT,
    CURATED_SENSORS_DOTTED,
    CURATED_SENSORS_FLAT,
    CuratedSensor,
    DataPoint,
    curated_translation_key,
    is_raw_metadata_field,
    resolve_curated_distance_unit,
)

_FIELD_TO_TRANSLATION_KEY: dict[str, str] = {
    s.field_name: curated_translation_key(s.field_name, s.translation_key)
    for s in (*CURATED_SENSORS_DOTTED, *CURATED_SENSORS_FLAT)
}
_BINARY_FIELD_TO_TRANSLATION_KEY: dict[str, str] = {
    b.field_name: curated_translation_key(b.field_name)
    for b in (*CURATED_BINARY_DOTTED, *CURATED_BINARY_FLAT)
}

_DYNAMIC_DISTANCE_CURATED: dict[str, CuratedSensor] = {
    s.field_name: s
    for s in (*CURATED_SENSORS_DOTTED, *CURATED_SENSORS_FLAT)
    if s.unit_resolver == "distance" and (s.unit_field or s.unit_fields)
}


def translation_key_for_unique_id(unique_id: str, vin: str) -> str | None:
    """Map a curated sensor unique_id to its HA translation_key."""
    if unique_id == f"{vin}_integration_status":
        return "integration_status"
    for suffix, key in (
        ("days_until_subscription_expires", "days_until_subscription_expires"),
        ("minutes_since_last_snapshot", "minutes_since_last_snapshot"),
        ("last_vehicle_update", "last_vehicle_update"),
        ("last_connected", "last_connected"),
        ("dataset_generated", "dataset_generated"),
        ("uncurated_fields_count", "uncurated_fields_count"),
    ):
        if unique_id == f"{vin}_{suffix}":
            return key
    prefix = f"{vin}_"
    if not unique_id.startswith(prefix):
        return None
    field = unique_id[len(prefix) :]
    return _FIELD_TO_TRANSLATION_KEY.get(field) or _BINARY_FIELD_TO_TRANSLATION_KEY.get(
        field
    )


_INSTRUMENT_CLUSTER_RAW_NAMES = frozenset(
    {"instrument_cluster_time", "profile_state_report.instrument_cluster_time"}
)

_MINUTE_DURATION_FIELDS = frozenset(
    {
        "battery_state_report.remaining_charging_time_complete",
        "battery_state_report.remaining_charging_time_bulk",
        "remaining_climate_time",
    }
)


def distance_registry_unit_fix(
    resolved: str | None,
    registry_unit: str | None,
    private_unit: str | None,
) -> tuple[bool, str | None]:
    """Return whether to clear sensor.private and the registry unit to set.

    ``resolved`` is the portal-mapped unit (``mi`` / ``km``). When the dataset
    carries no companion ``*.unit`` field, ``resolved`` is ``None`` and the
    registry is left alone so the static curated default can apply.
    """
    if resolved is None:
        return False, None
    if registry_unit == resolved and private_unit in (None, resolved):
        return False, None
    clear_private = bool(private_unit and private_unit != resolved)
    if registry_unit == resolved:
        return clear_private, None
    return clear_private, resolved


def entity_registry_updates(
    reg_entry: er.RegistryEntry,
    vin: str,
    *,
    has_dotted_instrument_cluster: bool = False,
) -> dict | None:
    """Return registry updates for one entity, or None if unchanged."""
    if reg_entry.domain not in ("sensor", "binary_sensor"):
        return None

    if reg_entry.unique_id in (
        f"{vin}_mileage.value.timestamp",
        f"{vin}_mileage.timestamp",
    ):
        return {"new_unique_id": f"{vin}_last_connected"}

    if reg_entry.unique_id == f"{vin}_car_captured_time":
        if reg_entry.disabled_by is None:
            return {"disabled_by": er.RegistryEntryDisabler.INTEGRATION}
        return None

    if (
        reg_entry.unique_id == f"{vin}_instrument_cluster_time"
        and has_dotted_instrument_cluster
        and reg_entry.disabled_by is None
    ):
        return {"disabled_by": er.RegistryEntryDisabler.INTEGRATION}

    if (
        reg_entry.domain == "sensor"
        and reg_entry.translation_key is None
        and reg_entry.original_name in _INSTRUMENT_CLUSTER_RAW_NAMES
        and reg_entry.disabled_by is None
    ):
        return {"disabled_by": er.RegistryEntryDisabler.INTEGRATION}

    if (
        reg_entry.domain == "sensor"
        and reg_entry.translation_key is None
        and reg_entry.entity_category == EntityCategory.DIAGNOSTIC
    ):
        name = reg_entry.original_name or ""
        if is_raw_metadata_field(name) and reg_entry.disabled_by is None:
            return {"disabled_by": er.RegistryEntryDisabler.INTEGRATION}

    updates: dict = {}
    prefix = f"{vin}_"
    field = (
        reg_entry.unique_id[len(prefix) :]
        if reg_entry.unique_id.startswith(prefix)
        else None
    )
    if (
        field in _MINUTE_DURATION_FIELDS
        and (
            getattr(reg_entry, "unit_of_measurement", None) == "s"
            or reg_entry.options.get("sensor.private", {}).get(
                "suggested_unit_of_measurement"
            )
            == "s"
        )
    ):
        updates["unit_of_measurement"] = "min"
    key = translation_key_for_unique_id(reg_entry.unique_id, vin)
    if not key:
        return updates or None
    if reg_entry.translation_key == key and reg_entry.name is None:
        return updates or None
    updates["translation_key"] = key
    updates["name"] = None
    return updates


async def async_migrate_entity_translations(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Ensure curated entities use translation_key instead of stale registry names.

    Also disables legacy duplicate timestamp/meta entities (upstream #23).
    """
    vin = entry.data[CONF_VIN]
    registry = er.async_get(hass)
    has_dotted_instrument_cluster = any(
        reg.unique_id == f"{vin}_profile_state_report.instrument_cluster_time"
        for reg in er.async_entries_for_config_entry(registry, entry.entry_id)
    )

    @callback
    def _migrate(reg_entry: er.RegistryEntry) -> dict | None:
        return entity_registry_updates(
            reg_entry,
            vin,
            has_dotted_instrument_cluster=has_dotted_instrument_cluster,
        )

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)

    prefix = f"{vin}_"
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        field = (
            reg_entry.unique_id[len(prefix) :]
            if reg_entry.unique_id.startswith(prefix)
            else None
        )
        if (
            field in _MINUTE_DURATION_FIELDS
            and (
                getattr(reg_entry, "unit_of_measurement", None) == "s"
                or reg_entry.options.get("sensor.private", {}).get(
                    "suggested_unit_of_measurement"
                )
                == "s"
            )
        ):
            registry.async_update_entity_options(
                reg_entry.entity_id,
                "sensor.private",
                None,
            )
            registry.async_update_entity(
                reg_entry.entity_id,
                unit_of_measurement="min",
            )


@callback
def async_sync_distance_registry_units(
    hass: HomeAssistant,
    entry: ConfigEntry,
    points: dict[str, DataPoint],
) -> None:
    """Align entity-registry distance units with the portal once data is available.

    Setup-time migrations run before the first dataset arrives, so Home
    Assistant can lock the static curated default (``km``) into the registry and
    keep overriding the resolved native unit afterwards (issue #11). This runs
    after coordinator data is present and only updates entities whose portal
    companion ``*.unit`` field maps to a concrete unit.
    """
    if not points:
        return

    vin = entry.data[CONF_VIN]
    prefix = f"{vin}_"
    registry = er.async_get(hass)

    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.domain != "sensor" or reg_entry.platform != DOMAIN:
            continue
        if not reg_entry.unique_id.startswith(prefix):
            continue
        field = reg_entry.unique_id[len(prefix) :]
        curated = _DYNAMIC_DISTANCE_CURATED.get(field)
        if curated is None:
            continue

        resolved = resolve_curated_distance_unit(curated, points)
        private_unit = reg_entry.options.get("sensor.private", {}).get(
            "suggested_unit_of_measurement"
        )
        clear_private, new_unit = distance_registry_unit_fix(
            resolved,
            getattr(reg_entry, "unit_of_measurement", None),
            private_unit,
        )
        if clear_private:
            registry.async_update_entity_options(
                reg_entry.entity_id,
                "sensor.private",
                None,
            )
        if new_unit is not None:
            registry.async_update_entity(
                reg_entry.entity_id,
                unit_of_measurement=new_unit,
            )
