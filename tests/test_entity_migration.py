"""Entity registry translation_key migration tests."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from custom_components.cupra_eu_data_act.entity_migration import (
    distance_registry_unit_fix,
    entity_registry_updates,
    translation_key_for_unique_id,
)


def _entry(**kwargs) -> SimpleNamespace:
    defaults = {
        "domain": "sensor",
        "unique_id": "WVWZZZTESTVIN0001_report_type",
        "translation_key": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "original_name": "report_type",
        "disabled_by": None,
        "name": None,
        "unit_of_measurement": None,
        "options": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_translation_key_for_curated_sensor() -> None:
    assert (
        translation_key_for_unique_id(
            "WVWZZZTESTVIN0001_battery_state_report.soc", "WVWZZZTESTVIN0001"
        )
        == "battery_state_report_soc"
    )


def test_translation_key_for_enum_sensor() -> None:
    assert (
        translation_key_for_unique_id(
            "WVWZZZTESTVIN0001_charging_state_report.current_charge_state",
            "WVWZZZTESTVIN0001",
        )
        == "charge_state"
    )


def test_translation_key_for_status_sensor() -> None:
    assert (
        translation_key_for_unique_id(
            "WVWZZZTESTVIN0001_integration_status", "WVWZZZTESTVIN0001"
        )
        == "integration_status"
    )


def test_translation_key_unknown_raw_sensor() -> None:
    assert (
        translation_key_for_unique_id(
            "WVWZZZTESTVIN0001_1763a4fe-d8a6-3b8c-b095-70081f3e61c7",
            "WVWZZZTESTVIN0001",
        )
        is None
    )


def test_translation_key_for_curated_binary_sensor() -> None:
    assert (
        translation_key_for_unique_id(
            "WVWZZZTESTVIN0001_locked", "WVWZZZTESTVIN0001"
        )
        == "locked"
    )


def test_translation_key_for_dotted_binary_sensor() -> None:
    assert (
        translation_key_for_unique_id(
            "WVWZZZTESTVIN0001_charge_mode_selection_options.immediate_charging",
            "WVWZZZTESTVIN0001",
        )
        == "charge_mode_selection_options_immediate_charging"
    )


def test_translation_key_for_flat_binary_sensor() -> None:
    assert (
        translation_key_for_unique_id(
            "WVWZZZTESTVIN0001_open_state_front_left_door",
            "WVWZZZTESTVIN0001",
        )
        == "open_state_front_left_door"
    )


def test_migration_disables_car_captured_time_curated() -> None:
    vin = "WVWZZZTESTVIN0001"
    updates = entity_registry_updates(
        _entry(
            unique_id=f"{vin}_car_captured_time",
            translation_key="car_captured_time",
            entity_category=None,
            original_name="Last telemetry",
        ),
        vin,
    )
    assert updates == {"disabled_by": er.RegistryEntryDisabler.INTEGRATION}


def test_migration_disables_bare_instrument_cluster_when_dotted_exists() -> None:
    vin = "WVWZZZTESTVIN0001"
    updates = entity_registry_updates(
        _entry(
            unique_id=f"{vin}_instrument_cluster_time",
            translation_key="instrument_cluster_time",
            entity_category=None,
            original_name="Vehicle clock",
        ),
        vin,
        has_dotted_instrument_cluster=True,
    )
    assert updates == {"disabled_by": er.RegistryEntryDisabler.INTEGRATION}


def test_migration_keeps_bare_instrument_cluster_for_flat_cars() -> None:
    vin = "WVWZZZTESTVIN0001"
    assert (
        entity_registry_updates(
            _entry(
                unique_id=f"{vin}_instrument_cluster_time",
                translation_key="instrument_cluster_time",
                entity_category=None,
                original_name="Vehicle clock",
            ),
            vin,
            has_dotted_instrument_cluster=False,
        )
        is None
    )


def test_migration_disables_raw_instrument_cluster_duplicate() -> None:
    vin = "WVWZZZTESTVIN0001"
    updates = entity_registry_updates(
        _entry(
            unique_id=f"{vin}_f295ae23-0485-3ccb-830b-58c644a04f2e",
            original_name="profile_state_report.instrument_cluster_time",
        ),
        vin,
    )
    assert updates == {"disabled_by": er.RegistryEntryDisabler.INTEGRATION}


def test_migration_disables_raw_report_type() -> None:
    vin = "WVWZZZTESTVIN0001"
    updates = entity_registry_updates(
        _entry(
            unique_id=f"{vin}_3dc12462-4854-3c9e-8428-a61d7c1c3297",
            original_name="report_type",
        ),
        vin,
    )
    assert updates == {"disabled_by": er.RegistryEntryDisabler.INTEGRATION}


def test_migration_disables_raw_timestamp() -> None:
    vin = "WVWZZZTESTVIN0001"
    updates = entity_registry_updates(
        _entry(
            unique_id=f"{vin}_75184561-67be-36ed-a951-d2b398cc256f",
            original_name="timestamp",
        ),
        vin,
    )
    assert updates == {"disabled_by": er.RegistryEntryDisabler.INTEGRATION}


def test_migration_keeps_non_metadata_raw() -> None:
    vin = "WVWZZZTESTVIN0001"
    assert (
        entity_registry_updates(
            _entry(
                unique_id=f"{vin}_b24b8c24-662b-3540-9bf3-6ea953e5303e",
                original_name="error_code",
            ),
            vin,
        )
        is None
    )


def test_distance_registry_unit_fix_miles_vehicle() -> None:
    clear_private, new_unit = distance_registry_unit_fix("mi", "km", None)
    assert clear_private is False
    assert new_unit == "mi"


def test_distance_registry_unit_fix_silent_portal() -> None:
    assert distance_registry_unit_fix(None, "km", None) == (False, None)


def test_distance_registry_unit_fix_already_correct() -> None:
    assert distance_registry_unit_fix("km", "km", None) == (False, None)


def test_distance_registry_unit_fix_clears_private_override() -> None:
    clear_private, new_unit = distance_registry_unit_fix("mi", "mi", "km")
    assert clear_private is True
    assert new_unit is None


def test_migration_does_not_blind_clear_km_at_setup() -> None:
    vin = "WVWZZZTESTVIN0001"
    updates = entity_registry_updates(
        _entry(
            unique_id=f"{vin}_mileage.value",
            translation_key="mileage_value",
            entity_category=None,
            unit_of_measurement="km",
        ),
        vin,
    )
    assert updates is None
