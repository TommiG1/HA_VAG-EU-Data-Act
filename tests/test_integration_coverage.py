"""Coverage for integration lifecycle, services, flows, and registry helpers."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import ServiceCall
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cupra_eu_data_act import (
    EudaRuntimeData,
    _async_migrate_raw_unique_ids,
    async_migrate_entry,
    async_setup,
    async_setup_entry,
    async_unload,
    async_unload_entry,
)
from custom_components.cupra_eu_data_act.api import ApiError, AuthError
from custom_components.cupra_eu_data_act.brands import get_brand
from custom_components.cupra_eu_data_act.config_flow import EudaConfigFlow
from custom_components.cupra_eu_data_act.const import (
    CONF_BRAND,
    CONF_COUNTRY,
    CONF_CREATE_UTILITY_METERS,
    CONF_EMAIL,
    CONF_IDENTIFIER,
    CONF_LANGUAGE,
    CONF_PASSWORD,
    CONF_UTILITY_METERS_PROVISIONED,
    CONF_VIN,
    DOMAIN,
)
from custom_components.cupra_eu_data_act.entity_migration import (
    async_migrate_entity_translations,
    async_sync_distance_registry_units,
    entity_registry_updates,
    translation_key_for_unique_id,
)
from custom_components.cupra_eu_data_act.services import (
    SERVICE_REFRESH_NOW,
    _async_handle_refresh_now,
    async_setup_services,
    async_unload_services,
)
from custom_components.cupra_eu_data_act.utility_meter import (
    async_ensure_utility_meters,
)

VIN = "WVWZZZTESTVIN0001"


def _entry(hass, *, loaded: bool = True, version: int = 1) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VIN: VIN,
            CONF_IDENTIFIER: "ident-1",
            CONF_BRAND: "cupra",
            CONF_EMAIL: "owner@example.com",
            CONF_PASSWORD: "secret",
            CONF_COUNTRY: "de",
            CONF_LANGUAGE: "de",
        },
        unique_id=VIN,
        version=version,
    )
    entry.add_to_hass(hass)
    if loaded:
        entry.runtime_data = EudaRuntimeData(MagicMock(), AsyncMock())
    else:
        entry.runtime_data = None
    return entry


def _flow(hass) -> EudaConfigFlow:
    flow = EudaConfigFlow()
    flow.hass = hass
    flow.context = {}
    return flow


def test_unknown_brand_and_translation_edges() -> None:
    with pytest.raises(ValueError, match="Unknown brand"):
        get_brand("not-a-brand")
    assert translation_key_for_unique_id("foreign", VIN) is None
    assert translation_key_for_unique_id(f"{VIN}_snapshot_stale", VIN) == "snapshot_stale"
    assert entity_registry_updates(
        SimpleNamespace(domain="button", unique_id="x"), VIN
    ) is None


async def test_services_empty_unloaded_duplicate_setup_and_unload(hass) -> None:
    call = ServiceCall(hass, DOMAIN, SERVICE_REFRESH_NOW, {})
    with pytest.raises(ServiceValidationError):
        await _async_handle_refresh_now(hass, call)

    entry = _entry(hass, loaded=False)
    with pytest.raises(ServiceValidationError):
        await _async_handle_refresh_now(hass, call)

    async_setup_services(hass)
    async_setup_services(hass)
    assert hass.services.has_service(DOMAIN, SERVICE_REFRESH_NOW)
    async_unload_services(hass)
    async_unload_services(hass)
    assert not hass.services.has_service(DOMAIN, SERVICE_REFRESH_NOW)
    await hass.config_entries.async_remove(entry.entry_id)


async def test_integration_setup_unload_migrate_and_raw_ids(hass) -> None:
    assert await async_setup(hass, {})
    assert hass.services.has_service(DOMAIN, SERVICE_REFRESH_NOW)
    assert await async_unload(hass)

    entry = _entry(hass, version=1)
    with patch(
        "custom_components.cupra_eu_data_act.async_migrate_entity_translations",
        AsyncMock(),
    ) as migrate:
        assert await async_migrate_entry(hass, entry)
        migrate.assert_awaited_once()
    assert entry.version == 2
    assert await async_migrate_entry(hass, entry)

    registry = __import__(
        "homeassistant.helpers.entity_registry", fromlist=["async_get"]
    ).async_get(hass)
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "raw-key",
        config_entry=entry,
    )
    registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "binary-key",
        config_entry=entry,
    )
    await _async_migrate_raw_unique_ids(hass, entry)
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{VIN}_raw-key")

    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    with patch(
        "custom_components.cupra_eu_data_act.async_clear_issues"
    ) as clear:
        assert await async_unload_entry(hass, entry)
        clear.assert_called_once()
        entry.runtime_data.session.close.assert_awaited_once()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    assert not await async_unload_entry(hass, entry)


async def test_setup_entry_success_and_failure_cleanup(hass) -> None:
    entry = _entry(hass)
    session = MagicMock()
    session.close = AsyncMock()
    coordinator = MagicMock()
    coordinator.async_restore_from_cache = AsyncMock(return_value={"k": MagicMock()})
    coordinator.async_add_listener.return_value = lambda: None
    coordinator.async_refresh = AsyncMock()
    coordinator.data = {}
    coordinator.async_set_updated_data = MagicMock()
    coordinator.async_update_listeners = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    with (
        patch("custom_components.cupra_eu_data_act.aiohttp.ClientSession", return_value=session),
        patch("custom_components.cupra_eu_data_act.EudaCoordinator", return_value=coordinator),
        patch(
            "custom_components.cupra_eu_data_act._async_migrate_raw_unique_ids",
            AsyncMock(),
        ),
        patch("custom_components.cupra_eu_data_act.async_update_issues"),
        patch("custom_components.cupra_eu_data_act.async_sync_distance_registry_units"),
    ):
        assert await async_setup_entry(hass, entry)
    coordinator.async_set_updated_data.assert_called_once()

    failed = _entry(hass)
    failed_session = MagicMock()
    failed_session.close = AsyncMock()
    with (
        patch(
            "custom_components.cupra_eu_data_act.aiohttp.ClientSession",
            return_value=failed_session,
        ),
        patch(
            "custom_components.cupra_eu_data_act.load_dictionary",
            side_effect=RuntimeError("bad dictionary"),
        ),
    ):
        with pytest.raises(RuntimeError, match="bad dictionary"):
            await async_setup_entry(hass, failed)
    failed_session.close.assert_awaited_once()


async def test_config_flow_login_errors_reauth_and_reconfigure(hass) -> None:
    flow = _flow(hass)
    for exc, expected in (
        (AuthError("bad"), "invalid_auth"),
        (ApiError("down"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ):
        client = MagicMock()
        client.async_login = AsyncMock(side_effect=exc)
        with patch.object(flow, "_client", return_value=client):
            assert await flow._async_try_login() == expected

    no_vehicle = _flow(hass)
    with patch.object(no_vehicle, "_async_try_login", AsyncMock(return_value=None)):
        result = await no_vehicle.async_step_user(
            {
                CONF_BRAND: "cupra",
                CONF_EMAIL: "a@b.c",
                CONF_PASSWORD: "x",
                CONF_COUNTRY: "DE",
            }
        )
    assert result["errors"]["base"] == "no_vehicles"

    entry = _entry(hass)
    reauth = _flow(hass)
    reauth.context = {"source": "reauth", "entry_id": entry.entry_id}
    await reauth.async_step_reauth(dict(entry.data))
    with patch.object(reauth, "_async_try_login", AsyncMock(return_value=None)):
        result = await reauth.async_step_reauth_confirm(
            {
                CONF_PASSWORD: "new",
                CONF_COUNTRY: "ES",
                CONF_LANGUAGE: "es",
            }
        )
    assert result["type"] == "abort"

    reconfigure = _flow(hass)
    reconfigure.context = {"source": "reconfigure", "entry_id": entry.entry_id}
    assert (await reconfigure.async_step_reconfigure())["type"] == "form"
    with patch.object(reconfigure, "_async_try_login", AsyncMock(return_value=None)):
        result = await reconfigure.async_step_reconfigure(
            {
                CONF_EMAIL: "new@example.com",
                CONF_PASSWORD: "new",
                CONF_COUNTRY: "CZ",
                CONF_LANGUAGE: "cs",
            }
        )
    assert result["reason"] == "reconfigure_successful"

    vehicle = _flow(hass)
    vehicle._vehicles = [{"vin": VIN}]
    with patch.object(
        vehicle, "_async_fetch_identifier", AsyncMock(side_effect=AuthError("bad"))
    ):
        assert (await vehicle.async_step_vehicle({CONF_VIN: VIN}))["reason"] == "auth"


async def test_utility_meter_creation_existing_and_unexpected(hass) -> None:
    entry = _entry(hass)
    entry.runtime_data = None
    hass.config_entries.async_update_entry(
        entry, options={CONF_CREATE_UTILITY_METERS: True}
    )
    registry_entry = SimpleNamespace(
        unique_id=f"{VIN}_mileage.value",
        entity_id="sensor.vehicle_mileage",
        domain="sensor",
    )
    results = [
        {"type": "create_entry"},
        {"type": "form"},
    ]
    with (
        patch(
            "custom_components.cupra_eu_data_act.utility_meter.er.async_entries_for_config_entry",
            return_value=[registry_entry],
        ),
        patch.object(
            hass.config_entries.flow,
            "async_init",
            AsyncMock(side_effect=results),
        ) as init,
    ):
        await async_ensure_utility_meters(hass, entry)
    init.assert_awaited_once()
    assert entry.options[CONF_UTILITY_METERS_PROVISIONED] == ["Monthly mileage"]

    hass.config_entries.async_update_entry(
        entry, options={CONF_CREATE_UTILITY_METERS: True}
    )
    with (
        patch(
            "custom_components.cupra_eu_data_act.utility_meter.er.async_entries_for_config_entry",
            return_value=[registry_entry],
        ),
        patch.object(
            hass.config_entries.flow,
            "async_init",
            AsyncMock(return_value={"type": "form"}),
        ),
    ):
        await async_ensure_utility_meters(hass, entry)
    assert CONF_UTILITY_METERS_PROVISIONED not in entry.options

    existing = MockConfigEntry(
        domain="utility_meter",
        title=f"{VIN} Monthly mileage",
        options={"source": "sensor.other", "cycle": "monthly"},
    )
    existing.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={CONF_CREATE_UTILITY_METERS: True}
    )
    with patch(
        "custom_components.cupra_eu_data_act.utility_meter.er.async_entries_for_config_entry",
        return_value=[registry_entry],
    ):
        await async_ensure_utility_meters(hass, entry)
    assert "Monthly mileage" in entry.options[CONF_UTILITY_METERS_PROVISIONED]


async def test_registry_migration_and_distance_sync(hass) -> None:
    entry = _entry(hass)
    registry = __import__(
        "homeassistant.helpers.entity_registry", fromlist=["async_get"]
    ).async_get(hass)
    reg = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{VIN}_remaining_climate_time",
        config_entry=entry,
        original_name="remaining_climate_time",
        entity_category=EntityCategory.DIAGNOSTIC,
        unit_of_measurement="s",
    )
    registry.async_update_entity_options(
        reg.entity_id,
        "sensor.private",
        {"suggested_unit_of_measurement": "s"},
    )
    await async_migrate_entity_translations(hass, entry)
    updated = registry.async_get(reg.entity_id)
    assert updated.unit_of_measurement == "min"

    mileage = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{VIN}_mileage.value",
        config_entry=entry,
        unit_of_measurement="km",
    )
    from custom_components.cupra_eu_data_act.data import Dataset

    points = Dataset.from_json(
        {
            "Data": [
                {"key": "v", "dataFieldName": "mileage.value", "value": "10"},
                {"key": "u", "dataFieldName": "mileage.unit", "value": "MILES"},
            ]
        }
    ).points
    async_sync_distance_registry_units(hass, entry, {})
    async_sync_distance_registry_units(hass, entry, points)
    assert registry.async_get(mileage.entity_id).unit_of_measurement == "mi"
