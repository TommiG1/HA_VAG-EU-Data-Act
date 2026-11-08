"""Broad platform/entity coverage using realistic portal datasets."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cupra_eu_data_act import EudaRuntimeData
from custom_components.cupra_eu_data_act import binary_sensor, button, sensor
from custom_components.cupra_eu_data_act.const import (
    CONF_BRAND,
    CONF_IDENTIFIER,
    CONF_NICKNAME,
    CONF_VIN,
    DOMAIN,
)
from custom_components.cupra_eu_data_act.coordinator import EudaCoordinator
from custom_components.cupra_eu_data_act.data import CuratedSensor, Dataset
from custom_components.cupra_eu_data_act.entity import EudaEntity

FIXTURES = Path(__file__).parent / "fixtures"
VIN = "WVWZZZTESTVIN0001"


def _entry_and_coordinator(hass, payload: dict):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VIN: VIN,
            CONF_IDENTIFIER: "ident-1",
            CONF_BRAND: "cupra",
            CONF_NICKNAME: "Born",
        },
        unique_id=VIN,
    )
    entry.add_to_hass(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    coordinator.data = Dataset.from_json(payload).points
    coordinator.async_refresh = AsyncMock()
    entry.runtime_data = EudaRuntimeData(coordinator, MagicMock())
    return entry, coordinator


def _payload(*items: tuple[str, object], dotted: bool = True) -> dict:
    data = []
    for index, (field, value) in enumerate(items):
        item = {"key": f"k{index}", "dataFieldName": field}
        if value is not None:
            item["value"] = str(value)
        data.append(item)
    if dotted and not any("." in item["dataFieldName"] for item in data):
        data.append({"key": "format", "dataFieldName": "format.marker", "value": "1"})
    return {"vin": VIN, "user_id": "u", "Data": data}


async def test_realistic_platforms_and_entities(hass) -> None:
    payload = json.loads((FIXTURES / "sample_dataset.json").read_text())
    payload["Data"].extend(
        json.loads((FIXTURES / "cupra_dotted_uncurated_sample.json").read_text())[
            "Data"
        ]
    )
    entry, coordinator = _entry_and_coordinator(hass, payload)
    coordinator.status_label = "ok"
    coordinator.empty_snapshot_count = 2
    coordinator._consecutive_server_errors = 1
    coordinator.latest_dataset = Dataset.from_json(payload)
    coordinator.latest_dataset_name = "20260101120000_test.zip"
    coordinator.dataset_created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    coordinator.subscription_created_on = datetime(2026, 1, 1, tzinfo=timezone.utc)
    coordinator.listing_identifier = "ident-1"
    coordinator.last_download_attempts = [{"success": True}]
    coordinator._cached_dataset_meta = [{"name": "cached.zip"}]

    sensors: list = []
    binaries: list = []
    buttons: list = []
    await sensor.async_setup_entry(hass, entry, sensors.extend)
    await binary_sensor.async_setup_entry(hass, entry, binaries.extend)
    await button.async_setup_entry(hass, entry, buttons.extend)

    assert sensors and binaries and len(buttons) == 1
    for entity in sensors:
        _ = entity.available
        _ = entity.native_value
        _ = entity.native_unit_of_measurement
        _ = entity.extra_state_attributes
    for entity in binaries:
        _ = entity.available
        _ = entity.is_on
        _ = entity.extra_state_attributes
    assert buttons[0].available
    await buttons[0].async_press()
    coordinator.async_refresh.assert_awaited_once()

    # Re-run discovery with values that unlock derived/timestamp/due-date entities.
    coordinator.data.update(
        Dataset.from_json(
            _payload(
                ("maintenance_interval__time_until_inspection", -5),
                ("battery_state_report.charge_energy", 100),
                ("battery_state_report.remaining_charging_time_complete", 600),
                ("charging_state_report.current_charge_state", "CHARGING_HV_BATTERY"),
            )
        ).points
    )
    coordinator.async_update_listeners()
    for entity in sensors:
        _ = entity.native_value
        _ = entity.extra_state_attributes


def test_base_entity_sticky_filter_and_units(hass) -> None:
    entry, coordinator = _entry_and_coordinator(hass, _payload(("mileage.value", 10)))
    entity = EudaEntity(coordinator)
    assert entity.available
    coordinator.data = None
    assert not entity.available
    assert entity._sticky(4) == 4
    assert entity._sticky(None) == 4
    entity._last_value = None
    now = datetime.now(timezone.utc)
    assert entity._sticky_monotonic(now) == now
    assert entity._sticky_monotonic(now - timedelta(days=1)) == now
    assert entity._sticky_unit(None) is None
    assert entity._sticky_unit("km") is None
    assert entity._sticky_unit("km") == "km"
    assert entity._sticky_unit("km") == "km"
    assert entity._sticky_unit("mi") == "km"
    assert entity._filtered(12, "mileage") == 12
    assert entity._filtered(4294967295, "mileage") == 12


def test_curated_sensor_transforms_and_special_values(hass) -> None:
    entry, coordinator = _entry_and_coordinator(hass, _payload(("value", 1)))

    cases = [
        ("duration_s", 60, 60),
        ("duration_min", 120, 2.0),
        ("duration_min", "bad", None),
        ("decikelvin_to_celsius", 2931, 20.0),
        ("hectometers_to_km", 160, 16.0),
        (None, 7, 7),
    ]
    for transform, value, expected in cases:
        curated = CuratedSensor("value", "Value", transform=transform)
        entity = sensor.EudaCuratedSensor(coordinator, curated)
        assert entity._apply_transform(value) == expected

    native_cases = [
        ("decikelvin_to_celsius", 2931, 20.0),
        ("abs", -5, 5),
        ("fuel_consumption", 168, 16.8),
        ("electr_consumption", 180, 18.0),
        ("hectometers_to_km", 160, 16.0),
        ("deci_kwh", 124, 12.4),
        ("deci_kw", 99, 9.9),
        ("iso_timestamp", "2026-01-01T00:00:00Z", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ("duration_min", 120, 2.0),
        ("duration_min", "bad", None),
    ]
    for transform, value, expected in native_cases:
        coordinator.data = Dataset.from_json(_payload(("value", value))).points
        entity = sensor.EudaCuratedSensor(
            coordinator, CuratedSensor("value", "Value", transform=transform)
        )
        assert entity.native_value == expected

    # Translation enums, enum shortening, missing/sentinel, and dynamic units.
    coordinator.data = Dataset.from_json(
        _payload(("value", "ENUM_VALUE"), ("value.unit", "MILES"))
    ).points
    translated = sensor.EudaCuratedSensor(
        coordinator,
        CuratedSensor(
            "value", "Value", translation_key="value", unit_field="value.unit"
        ),
    )
    assert translated.native_value == "enum_value"
    assert translated.native_unit_of_measurement == "mi"
    assert isinstance(translated.extra_state_attributes, dict)
    plain = sensor.EudaCuratedSensor(coordinator, CuratedSensor("value", "Value"))
    assert plain.native_value == "ENUM_VALUE"
    coordinator.data = {}
    assert plain.native_value == "ENUM_VALUE"


def test_raw_and_special_sensor_empty_paths(hass) -> None:
    entry, coordinator = _entry_and_coordinator(
        hass, _payload(("value_of_the_primary_range", 42), ("range.unit", "MILES"))
    )
    raw = sensor.EudaRawSensor(coordinator, "k0")
    assert raw.native_value == 42
    assert raw.native_unit_of_measurement == "mi"
    assert raw.extra_state_attributes["key"] == "k0"
    coordinator.data = {}
    assert raw.native_value == 42
    assert raw.extra_state_attributes == {}

    status = sensor.EudaStatusSensor(coordinator)
    assert status.available and status.native_value == "starting"
    assert status.extra_state_attributes["next_retry_minutes"] >= 0
    days = sensor.EudaDaysUntilSubscriptionExpiresSensor(coordinator)
    assert days.available and days.native_value is None
    assert days.extra_state_attributes == {"listing_identifier": "ident-1"}
    minutes = sensor.EudaMinutesSinceLastSnapshotSensor(coordinator)
    assert minutes.available and minutes.native_value is None
    assert minutes.extra_state_attributes == {}
    assert sensor.EudaLastVehicleUpdateSensor(coordinator).available
    assert sensor.EudaDatasetGeneratedSensor(coordinator).available
    assert sensor.EudaUncuratedFieldsCountSensor(coordinator).native_value is None


def test_curated_special_sources_values_and_units(hass) -> None:
    entry, coordinator = _entry_and_coordinator(
        hass,
        _payload(
            ("maintenance_interval__time_until_inspection", -5),
            ("mileage.value", 10),
            ("battery_state_report.charge_energy", 100),
            ("battery_state_report.charge_rate", 2),
            ("battery_state_report.charge_rate_unit", "CHARGE_RATE_UNIT_KM_PER_MIN"),
            ("battery_state_report.remaining_charging_time_complete", 600),
            ("charging_state_report.current_charge_state", "CHARGE_STATE_CHARGING_HV_BATTERY"),
        ),
    )
    due = sensor.EudaCuratedSensor(
        coordinator,
        CuratedSensor(
            "maintenance_interval__time_until_inspection.due_date",
            "Due",
        ),
    )
    assert due.native_value is not None
    assert due._source_datapoint() is None
    timestamp = sensor.EudaCuratedSensor(
        coordinator, CuratedSensor("mileage.value.timestamp", "Timestamp")
    )
    assert timestamp.native_value is None
    assert timestamp._source_datapoint() is not None

    charge = sensor.EudaCuratedSensor(
        coordinator, CuratedSensor("last_charge_kwh", "Last charge")
    )
    assert charge.native_value is None
    energy = next(
        dp
        for dp in coordinator.data.values()
        if dp.field_name == "battery_state_report.charge_energy"
    )
    energy.raw_value = "125"
    assert charge.native_value == 25
    energy.raw_value = "120"
    assert charge.native_value == 25
    assert charge._source_datapoint() is energy

    rate = sensor.EudaCuratedSensor(
        coordinator,
        CuratedSensor(
            "battery_state_report.charge_rate",
            "Rate",
            unit_field="battery_state_report.charge_rate_unit",
            unit_resolver="charge_rate",
        ),
    )
    assert rate.native_value == 120
    assert rate.native_unit_of_measurement is None
    assert rate.native_unit_of_measurement == "km/h"

    remaining = sensor.EudaCuratedSensor(
        coordinator,
        CuratedSensor(
            "battery_state_report.remaining_charging_time_complete", "Remaining"
        ),
    )
    assert remaining.native_value == 600
    coordinator.data = Dataset.from_json(
        _payload(
            ("battery_state_report.remaining_charging_time_complete", 600),
            ("charging_state_report.current_charge_state", "CHARGE_STATE_READY_FOR_CHARGING"),
            ("charging_state_report.charging_scenario", "CHARGING_SCENARIO_OFF"),
        )
    ).points
    assert remaining.native_value is None


def test_curated_remaining_sensor_branches(hass) -> None:
    entry, coordinator = _entry_and_coordinator(
        hass,
        _payload(
            ("value", 99),
            ("unit", "KM"),
            ("fallback.unit", "MILES"),
            ("timed", 1),
        ),
    )
    # Constructor option and charge-rate helper fallbacks.
    disabled = sensor.EudaCuratedSensor(
        coordinator, CuratedSensor("value", "Value", enabled_by_default=False)
    )
    assert disabled.entity_registry_enabled_default is False
    assert disabled._charge_rate_native_value(
        next(dp for dp in coordinator.data.values() if dp.field_name == "value")
    ) == 99
    missing_unit = sensor.EudaCuratedSensor(
        coordinator,
        CuratedSensor("value", "Value", unit_field="missing", transform="deci_kw"),
    )
    assert missing_unit._charge_rate_native_value(
        next(dp for dp in coordinator.data.values() if dp.field_name == "value")
    ) == 9.9

    # Timestamp value and fallback companion-unit chain.
    timed_dp = next(dp for dp in coordinator.data.values() if dp.field_name == "timed")
    timed_dp.timestamp_utc = "2026-01-01T00:00:00Z"
    timestamp = sensor.EudaCuratedSensor(
        coordinator, CuratedSensor("timed.timestamp", "Timestamp")
    )
    assert timestamp.native_value == datetime(2026, 1, 1, tzinfo=timezone.utc)
    dynamic = sensor.EudaCuratedSensor(
        coordinator,
        CuratedSensor(
            "value",
            "Value",
            unit_fields=("missing", "fallback.unit"),
            unit_resolver="distance",
        ),
    )
    assert dynamic.native_unit_of_measurement == "mi"

    # Sentinel filtering and absent last-charge source.
    sentinel = sensor.EudaCuratedSensor(
        coordinator, CuratedSensor("value", "Value")
    )
    next(dp for dp in coordinator.data.values() if dp.field_name == "value").raw_value = (
        "4294967295"
    )
    assert sentinel.native_value is None
    coordinator.data = {}
    last_charge = sensor.EudaCuratedSensor(
        coordinator, CuratedSensor("last_charge_kwh", "Last charge")
    )
    assert last_charge._source_datapoint() is None


async def test_binary_sensor_missing_and_derived_attribute_paths(hass) -> None:
    entry, coordinator = _entry_and_coordinator(
        hass,
        _payload(
            ("charging_power", 1),
            ("locked", "true"),
            dotted=False,
        ),
    )
    entities: list = []
    await binary_sensor.async_setup_entry(hass, entry, entities.extend)
    curated = next(
        e
        for e in entities
        if getattr(getattr(e, "_curated", None), "field_name", None) == "locked"
    )
    first = curated.is_on
    assert isinstance(first, bool)
    coordinator.data = {}
    assert curated.is_on is first
    derived = next(
        e
        for e in entities
        if getattr(getattr(e, "_curated", None), "field_name", None) == "charging"
    )
    assert derived.extra_state_attributes == {}
