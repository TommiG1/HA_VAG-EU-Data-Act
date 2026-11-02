"""Utility meter helper naming and opt-in provisioning tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.cupra_eu_data_act.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_NICKNAME,
    CONF_UTILITY_METERS_PROVISIONED,
    CONF_VIN,
)
from custom_components.cupra_eu_data_act.utility_meter import (
    async_ensure_utility_meters,
    utility_meter_helper_name,
    utility_meter_helper_object_id,
)


def _entry(vin: str, nickname: str | None = None, **options):
    data = {CONF_VIN: vin}
    if nickname is not None:
        data[CONF_NICKNAME] = nickname
    return SimpleNamespace(
        data=data,
        options=options,
        entry_id="test-entry",
    )


def test_helper_name_prefers_nickname() -> None:
    entry = _entry("WVWZZZTESTVIN0001", "Born")
    assert (
        utility_meter_helper_name(entry, "Monthly charged energy")
        == "Born Monthly charged energy"
    )


def test_helper_object_id_uses_vin_when_no_nickname() -> None:
    entry = _entry("WVWZZZTESTVIN0001")
    assert (
        utility_meter_helper_object_id(entry, "Monthly mileage")
        == "sensor.wvwzzztestvin0001_monthly_mileage"
    )


async def test_ensure_utility_meters_noop_when_opt_in_off(hass) -> None:
    entry = _entry("WVWZZZTESTVIN0001", "Born")
    with patch(
        "custom_components.cupra_eu_data_act.utility_meter.er.async_get"
    ) as mock_reg:
        await async_ensure_utility_meters(hass, entry)
        mock_reg.assert_not_called()


async def test_ensure_utility_meters_skips_already_provisioned(hass) -> None:
    entry = _entry(
        "WVWZZZTESTVIN0001",
        "Born",
        **{
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METERS_PROVISIONED: [
                "Monthly charged energy",
                "Monthly mileage",
            ],
        },
    )
    with (
        patch(
            "custom_components.cupra_eu_data_act.utility_meter.er.async_get",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.cupra_eu_data_act.utility_meter.er.async_entries_for_config_entry",
            return_value=[],
        ),
        patch.object(
            hass.config_entries.flow, "async_init", new_callable=AsyncMock
        ) as mock_init,
    ):
        await async_ensure_utility_meters(hass, entry)
        mock_init.assert_not_called()
