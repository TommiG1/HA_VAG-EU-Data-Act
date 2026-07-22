"""Diagnostics download tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cupra_eu_data_act import EudaRuntimeData
from custom_components.cupra_eu_data_act.const import (
    CONF_EMAIL,
    CONF_IDENTIFIER,
    CONF_PASSWORD,
    CONF_VIN,
    DOMAIN,
)
from custom_components.cupra_eu_data_act.coordinator import EudaCoordinator
from custom_components.cupra_eu_data_act.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redacts_secrets(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VIN: "WVWZZZSECRETVIN01",
            CONF_IDENTIFIER: "secret-id",
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "hunter2",
        },
        unique_id="WVWZZZSECRETVIN01",
    )
    entry.add_to_hass(hass)
    client = MagicMock()
    coordinator = EudaCoordinator(hass, entry, client)
    coordinator.status_label = "ok"
    entry.runtime_data = EudaRuntimeData(coordinator=coordinator, session=MagicMock())

    result = await async_get_config_entry_diagnostics(hass, entry)

    dumped = str(result)
    assert "hunter2" not in dumped
    assert "user@example.com" not in dumped
    assert "WVWZZZSECRETVIN01" not in dumped
    assert "secret-id" not in dumped
    assert result["status"]["label"] == "ok"
    assert result["integration"]["version"]


async def test_diagnostics_includes_uncurated_sample(hass) -> None:
    import json
    from pathlib import Path

    from custom_components.cupra_eu_data_act.data import Dataset

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VIN: "WVWZZZSECRETVIN01",
            CONF_IDENTIFIER: "secret-id",
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "hunter2",
        },
        unique_id="WVWZZZSECRETVIN01",
    )
    entry.add_to_hass(hass)
    client = MagicMock()
    coordinator = EudaCoordinator(hass, entry, client)
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "sample_dataset.json").read_text()
    )
    coordinator.latest_dataset = Dataset.from_json(payload)
    coordinator.data = coordinator.latest_dataset.points
    coordinator.status_label = "ok"
    entry.runtime_data = EudaRuntimeData(coordinator=coordinator, session=MagicMock())

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["uncurated_fields_sample"] is not None
    assert "report_type" not in result["uncurated_fields_sample"]
    assert "range.unit" in result["uncurated_fields_sample"]
    assert len(result["uncurated_fields_sample"]) <= 20

    timestamps = result["timestamps"]
    assert timestamps is not None
    assert timestamps["last_connected"]["timestamp_source"] == "car_captured_time"
    assert timestamps["last_connected"]["raw_timestamp"] == "2026-05-29T22:59:27Z"
    assert timestamps["mileage"][0]["field_name"] == "mileage.value"
    assert timestamps["car_captured"][0]["value"] == "2026-05-29T22:59:27Z"
    assert (
        timestamps["instrument_cluster_time"][0]["value"]
        == "2026-05-29T22:59:27+02:00"
    )


async def test_diagnostics_redacts_vin_in_dataset_filenames(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VIN: "WVWZZZSECRETVIN01",
            CONF_IDENTIFIER: "secret-id",
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "hunter2",
        },
        unique_id="WVWZZZSECRETVIN01",
    )
    entry.add_to_hass(hass)
    client = MagicMock()
    coordinator = EudaCoordinator(hass, entry, client)
    coordinator.status_label = "ok"
    coordinator.latest_dataset_name = "20260721195554_WVWZZZSECRETVIN01.zip"
    coordinator._cached_dataset_meta = [
        {
            "name": "20260721195554_WVWZZZSECRETVIN01.zip",
            "size": 12,
            "mtime": "2026-07-21T19:55:54+00:00",
        }
    ]
    entry.runtime_data = EudaRuntimeData(coordinator=coordinator, session=MagicMock())

    result = await async_get_config_entry_diagnostics(hass, entry)

    dumped = str(result)
    assert "WVWZZZSECRETVIN01" not in dumped
    assert result["latest_dataset"]["name"] == "20260721195554_REDACTED.zip"
    assert result["cached_datasets"][0]["name"] == "20260721195554_REDACTED.zip"
