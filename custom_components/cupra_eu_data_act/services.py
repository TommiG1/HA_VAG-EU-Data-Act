"""Integration services."""

from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import CONF_VIN, DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH_NOW = "refresh_now"
ATTR_CONFIG_ENTRY = "config_entry"

REFRESH_NOW_SCHEMA = vol.Schema(
    {
        # cv.config_entry_id is not available on all HA versions; lookup validates.
        vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
    }
)


def _entries_for_call(hass: HomeAssistant, call: ServiceCall) -> list[ConfigEntry]:
    """Resolve which config entries the service should target."""
    # ``config_entry`` is a plain schema field (see services.yaml), not a HA
    # target selector, so it already arrives in ``call.data`` — ServiceCall
    # itself has no ``target`` attribute to fall back to.
    entry_id = call.data.get(ATTR_CONFIG_ENTRY)

    entries = hass.config_entries.async_entries(DOMAIN)
    if entry_id is not None:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="config_entry_not_found",
            )
        return [entry]

    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_config_entries",
        )
    return entries


async def _async_handle_refresh_now(hass: HomeAssistant, call: ServiceCall) -> None:
    """Fetch the latest portal dataset immediately."""
    entries = _entries_for_call(hass, call)
    tasks: list[asyncio.Task] = []

    for entry in entries:
        if not entry.runtime_data:
            _LOGGER.warning(
                "Skipping refresh for %s: config entry not loaded",
                entry.title,
            )
            continue
        coordinator = entry.runtime_data.coordinator
        tasks.append(
            hass.async_create_task(
                coordinator.async_refresh(),
                name=f"{DOMAIN} refresh_now {entry.data.get(CONF_VIN, entry.entry_id)}",
            )
        )

    if not tasks:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_loaded_entries",
        )

    await asyncio.gather(*tasks)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH_NOW):
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_NOW,
        lambda call: _async_handle_refresh_now(hass, call),
        schema=REFRESH_NOW_SCHEMA,
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove integration services."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH_NOW):
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH_NOW)
