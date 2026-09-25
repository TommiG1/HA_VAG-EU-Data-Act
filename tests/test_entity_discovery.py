"""Curated entities are only created once a field holds a usable reading.

Fields for hardware the vehicle doesn't have (TPMS, sunroof, hood, …) arrive
every cycle with a sentinel or empty value. Creating an entity for them
immediately means an entity that can never hold a state. Discovery must wait
until a real reading shows up.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cupra_eu_data_act import EudaRuntimeData, binary_sensor, sensor
from custom_components.cupra_eu_data_act.const import CONF_IDENTIFIER, CONF_VIN, DOMAIN
from custom_components.cupra_eu_data_act.coordinator import EudaCoordinator
from custom_components.cupra_eu_data_act.data import Dataset

_TYRE_KEY = "e0f1c2a0-0000-0000-0000-000000000001"
_HOOD_KEY = "e0f1c2a0-0000-0000-0000-000000000002"


def _make_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VIN: "VSSZZZTESTVIN0901", CONF_IDENTIFIER: "ident-1"},
        unique_id="VSSZZZTESTVIN0901",
    )
    entry.add_to_hass(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    entry.runtime_data = EudaRuntimeData(coordinator=coordinator, session=MagicMock())
    return entry


def _snapshot(field_name: str, key: str, value) -> dict:
    item = {"key": key, "dataFieldName": field_name}
    if value is not None:
        item["value"] = value
    return Dataset.from_json({"vin": "V", "user_id": "u", "Data": [item]}).points


async def test_sensor_not_created_for_sentinel_only_field(hass) -> None:
    """A tyre-pressure field stuck on the 1 ("invalid") sentinel stays hidden."""
    entry = _make_entry(hass)
    coordinator = entry.runtime_data.coordinator
    added: list = []

    coordinator.data = _snapshot("tyre_pressure_actual_front_left", _TYRE_KEY, "1")
    await sensor.async_setup_entry(hass, entry, added.extend)
    assert not any(
        getattr(e, "_curated", None)
        and e._curated.field_name == "tyre_pressure_actual_front_left"
        for e in added
    )

    # A real reading arrives on the next poll -> the listener re-runs discovery.
    coordinator.data = _snapshot("tyre_pressure_actual_front_left", _TYRE_KEY, "2.3")
    coordinator.async_update_listeners()
    assert any(
        getattr(e, "_curated", None)
        and e._curated.field_name == "tyre_pressure_actual_front_left"
        for e in added
    )


async def test_binary_not_created_for_sentinel_only_field(hass) -> None:
    """A hood-state field stuck on 0 ("unsupported") stays hidden."""
    entry = _make_entry(hass)
    coordinator = entry.runtime_data.coordinator
    added: list = []

    coordinator.data = _snapshot("state_of_hood", _HOOD_KEY, "0")
    await binary_sensor.async_setup_entry(hass, entry, added.extend)
    assert not any(
        getattr(e, "_curated", None) and e._curated.field_name == "state_of_hood"
        for e in added
    )

    # The vehicle reports a real closed/open state on the next poll.
    coordinator.data = _snapshot("state_of_hood", _HOOD_KEY, "3")
    coordinator.async_update_listeners()
    assert any(
        getattr(e, "_curated", None) and e._curated.field_name == "state_of_hood"
        for e in added
    )
