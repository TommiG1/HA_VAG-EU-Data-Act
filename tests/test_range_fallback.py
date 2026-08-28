"""Combined cruising range: summed fallback across portal snapshots (#30, #54)."""

from __future__ import annotations

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cupra_eu_data_act.const import CONF_IDENTIFIER, CONF_VIN, DOMAIN
from custom_components.cupra_eu_data_act.coordinator import EudaCoordinator
from custom_components.cupra_eu_data_act.data import (
    CURATED_SENSORS_FLAT,
    Dataset,
    merge_data_points,
    stamp_source_dataset,
)
from custom_components.cupra_eu_data_act.sensor import EudaCuratedSensor

_COMBINED = next(
    s for s in CURATED_SENSORS_FLAT if s.field_name == "cruising_range_combined"
)
_PRIMARY = next(
    s for s in CURATED_SENSORS_FLAT if s.field_name == "cruising_range_primary_engine"
)

# Stable per-field keys: the portal reuses the same UUID for a field across
# datasets, which is what lets merge_data_points retain a previous reading.
_KEYS = {
    "cruising_range_combined": "153e8c40-0000-0000-0000-000000000001",
    "cruising_range_primary_engine": "153e8c40-0000-0000-0000-000000000002",
    "cruising_range_secondary_engine": "153e8c40-0000-0000-0000-000000000003",
}


def _make_coordinator(hass) -> EudaCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VIN: "VSSZZZTESTVIN0607", CONF_IDENTIFIER: "ident-1"},
        unique_id="VSSZZZTESTVIN0607",
    )
    entry.add_to_hass(hass)
    return EudaCoordinator(hass, entry, MagicMock())


def _snapshot(zip_name: str, combined, primary, secondary) -> dict:
    """One portal dataset; a ``None`` value is a field present without a value."""
    items = []
    for field_name, value in (
        ("cruising_range_combined", combined),
        ("cruising_range_primary_engine", primary),
        ("cruising_range_secondary_engine", secondary),
    ):
        item = {"key": _KEYS[field_name], "dataFieldName": field_name}
        if value is not None:
            item["value"] = value
        items.append(item)
    points = Dataset.from_json({"vin": "V", "user_id": "u", "Data": items}).points
    return stamp_source_dataset(points, zip_name)


def _poll(coordinator: EudaCoordinator, snapshot: dict) -> None:
    """Feed a snapshot through the coordinator's merge, as _async_update_data does."""
    coordinator.data = (
        merge_data_points(coordinator.data, snapshot) if coordinator.data else snapshot
    )


def test_spurious_zero_does_not_latch_combined_range(hass) -> None:
    """A one-off portal 0 must not disable the sum fallback forever (#54)."""
    coordinator = _make_coordinator(hass)
    sensor = EudaCuratedSensor(coordinator, _COMBINED)

    _poll(coordinator, _snapshot("20260827120000.zip", "804", "760", "22"))
    assert sensor.native_value == 804

    # The portal reports a genuine 0 for the total while the engines are fine.
    _poll(coordinator, _snapshot("20260827154332.zip", "0", "790", "22"))
    assert sensor.native_value == 812

    # Ten later datasets carry the field without a value; the retained 0 used to
    # win because it counted as a usable reading.
    for minute in range(10):
        _poll(
            coordinator,
            _snapshot(f"202608280{minute}0000.zip", None, "770", "22"),
        )

    assert sensor.native_value == 792
    # The attributes must date the sum by the components that produced it, not
    # by the retained total's day-old ZIP.
    assert sensor.extra_state_attributes["source_dataset"] == "20260828090000.zip"


def test_portal_total_wins_while_it_keeps_reporting(hass) -> None:
    """A usable total from the current dataset is never second-guessed."""
    coordinator = _make_coordinator(hass)
    sensor = EudaCuratedSensor(coordinator, _COMBINED)

    _poll(coordinator, _snapshot("20260828060000.zip", "801", "770", "22"))

    assert sensor.native_value == 801
    assert sensor.extra_state_attributes["source_dataset"] == "20260828060000.zip"


def test_empty_tank_and_battery_stay_zero(hass) -> None:
    """A total of 0 backed by 0 components is a real reading, not a placeholder."""
    coordinator = _make_coordinator(hass)
    sensor = EudaCuratedSensor(coordinator, _COMBINED)

    _poll(coordinator, _snapshot("20260828060000.zip", "0", "0", "0"))

    assert sensor.native_value == 0


def test_zero_without_components_is_reported(hass) -> None:
    """Vehicles that report no per-engine ranges keep the portal's own value."""
    coordinator = _make_coordinator(hass)
    sensor = EudaCuratedSensor(coordinator, _COMBINED)

    points = Dataset.from_json(
        {
            "vin": "V",
            "user_id": "u",
            "Data": [
                {
                    "key": _KEYS["cruising_range_combined"],
                    "dataFieldName": "cruising_range_combined",
                    "value": "0",
                }
            ],
        }
    ).points
    _poll(coordinator, stamp_source_dataset(points, "20260828060000.zip"))

    assert sensor.native_value == 0


def test_sensors_without_components_are_untouched(hass) -> None:
    """The fallback only applies to sensors that declare sum_fallback_fields."""
    coordinator = _make_coordinator(hass)
    sensor = EudaCuratedSensor(coordinator, _PRIMARY)

    _poll(coordinator, _snapshot("20260828060000.zip", "804", "0", "22"))

    assert _PRIMARY.sum_fallback_fields == ()
    assert sensor.native_value == 0
