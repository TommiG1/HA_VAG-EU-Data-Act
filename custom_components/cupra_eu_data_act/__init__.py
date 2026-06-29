"""The VW Group EU Data Act integration."""
from __future__ import annotations

from dataclasses import dataclass

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EudaApiClient
from .brands import DEFAULT_BRAND, get_brand
from .const import (
    CONF_BRAND,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_VIN,
    DOMAIN,
    raw_unique_id,
)
from .coordinator import EudaCoordinator
from .data import load_dictionary
from .entity_migration import (
    async_migrate_entity_translations,
    async_sync_distance_registry_units,
)
from .issues import async_clear_issues, async_update_issues
from .services import async_setup_services, async_unload_services
from .utility_meter import async_ensure_utility_meters

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (services)."""
    async_setup_services(hass)
    return True


async def async_unload(hass: HomeAssistant) -> bool:
    """Unload the integration."""
    async_unload_services(hass)
    return True


@dataclass
class EudaRuntimeData:
    coordinator: EudaCoordinator
    session: object


type EudaConfigEntry = ConfigEntry[EudaRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: EudaConfigEntry) -> bool:
    """Set up VW Group EU Data Act from a config entry.

    Setup is intentionally non-blocking: the first portal dataset can take
    15–60 minutes to appear after subscription, so blocking setup on it would
    leave the user staring at "Setting up..." for a long time. Instead the
    entry loads immediately with a single status sensor explaining what the
    integration is waiting for; the dataset-derived entities appear via the
    discovery listener as soon as real data arrives.
    """
    # Own session (own cookie jar — auth is cookie-based) but reuse Home
    # Assistant's shared connector so we benefit from its warm DNS cache and are
    # resilient to transient DNS hiccups. connector_owner=False so closing our
    # session never closes the shared connector.
    session = aiohttp.ClientSession(
        connector=async_get_clientsession(hass).connector,
        connector_owner=False,
        cookie_jar=aiohttp.CookieJar(),
    )
    try:
        # Warm the data-dictionary cache off the event loop (it reads a bundled
        # JSON file) so it doesn't block the loop during dataset parsing.
        await hass.async_add_executor_job(load_dictionary)

        brand = get_brand(entry.data.get(CONF_BRAND, DEFAULT_BRAND))
        client = EudaApiClient(
            session,
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD],
            brand,
        )
        coordinator = EudaCoordinator(hass, entry, client)
        entry.runtime_data = EudaRuntimeData(coordinator=coordinator, session=session)

        # Migrate pre-0.1.3 raw sensor unique_ids (bare dataset key -> VIN_key)
        # so they survive the namespacing fix that lets multiple vehicles work.
        await _async_migrate_raw_unique_ids(hass, entry)

        # Before platforms register entities: rename legacy unique_ids (e.g.
        # mileage.value.timestamp -> last_connected) so restored orphans are
        # adopted instead of duplicated.
        await async_migrate_entity_translations(hass, entry)

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        if cached_points := await coordinator.async_restore_from_cache():
            coordinator.status_label = "ok"
            coordinator.async_set_updated_data(cached_points)

        @callback
        def _on_coordinator_update() -> None:
            async_update_issues(hass, entry, coordinator)
            async_sync_distance_registry_units(hass, entry, coordinator.data or {})
            hass.async_create_task(async_ensure_utility_meters(hass, entry))

        entry.async_on_unload(coordinator.async_add_listener(_on_coordinator_update))
        _on_coordinator_update()

        # Kick off the first refresh after platform setup so the discovery
        # listeners are already wired up when data arrives. Failures are not
        # propagated to async_setup_entry — they are surfaced via the status
        # sensor and HA's regular coordinator retry logic.
        entry.async_create_background_task(
            hass,
            coordinator.async_refresh(),
            name=f"{DOMAIN} initial refresh {entry.data[CONF_VIN]}",
        )
    except Exception:
        # Setup failed: HA will not call async_unload_entry, so close the
        # session here to avoid leaking it (and its connector).
        await session.close()
        raise

    return True


async def _async_migrate_raw_unique_ids(hass: HomeAssistant, entry: EudaConfigEntry) -> None:
    """Prefix legacy raw-sensor unique_ids (bare dataset key) with the VIN.

    Curated sensors were always namespaced; only raw diagnostic sensors used the
    bare key, which collides across vehicles. Renaming them in the registry
    preserves the user's entity_ids/customisations across the fix.
    """
    vin = entry.data[CONF_VIN]
    prefix = f"{vin}_"

    @callback
    def _migrate(reg_entry: er.RegistryEntry) -> dict | None:
        if reg_entry.domain != "sensor":
            return None
        if reg_entry.unique_id.startswith(prefix):
            return None  # already namespaced (curated, or already migrated)
        return {"new_unique_id": raw_unique_id(vin, reg_entry.unique_id)}

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)


async def async_unload_entry(hass: HomeAssistant, entry: EudaConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        async_clear_issues(hass, entry)
        if entry.runtime_data:
            await entry.runtime_data.session.close()
    return unload_ok
