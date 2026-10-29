"""Repairs-center issues for portal delivery states."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import (
    BASE_URL,
    CONF_NICKNAME,
    DOMAIN,
    SUBSCRIPTION_WARNING_BEFORE,
)
from .coordinator import EudaCoordinator

# Status labels that should surface a repairs issue (see coordinator.status_label).
_ISSUE_STATUSES: frozenset[str] = frozenset(
    {
        "delivery_not_ready",
        "waiting_for_portal_data",
        "empty_snapshots",
        "listing_failed",
    }
)

_HEALTH_ISSUE_KEYS: frozenset[str] = frozenset(
    {
        "subscription_expiring_soon",
        "stale_snapshot",
    }
)

_ALL_ISSUE_KEYS: frozenset[str] = _ISSUE_STATUSES | _HEALTH_ISSUE_KEYS

def _retry_minutes(coordinator: EudaCoordinator) -> str:
    return str(int(coordinator.update_interval.total_seconds() // 60))


def _issue_id(entry_id: str, status: str) -> str:
    return f"{entry_id}_{status}"


@callback
def async_update_issues(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: EudaCoordinator
) -> None:
    """Create or clear repairs issues based on the integration status sensor."""
    status = coordinator.status_label
    vehicle = entry.data.get(CONF_NICKNAME) or coordinator.vin

    for issue_status in _ISSUE_STATUSES:
        issue_id = _issue_id(entry.entry_id, issue_status)
        # After reboot the cache can leave coordinator.data set while the
        # portal listing briefly has no content files. status_label then
        # becomes waiting_for_portal_data even though sensors already show
        # values — the "Waiting for first dataset" repair would be wrong
        # and would stack with stale_snapshot (#77). Suppress that repair
        # when we already have data; the status sensor still reports the label.
        if status != issue_status or (
            issue_status == "waiting_for_portal_data" and coordinator.data
        ):
            ir.async_delete_issue(hass, DOMAIN, issue_id)
            continue

        placeholders: dict[str, str] = {
            "portal_url": BASE_URL,
            "retry_minutes": _retry_minutes(coordinator),
            "vehicle": vehicle,
        }
        if issue_status == "empty_snapshots":
            placeholders["empty_count"] = str(coordinator.empty_snapshot_count)

        severity = (
            ir.IssueSeverity.ERROR
            if issue_status == "delivery_not_ready"
            else ir.IssueSeverity.WARNING
        )

        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            data={"entry_id": entry.entry_id},
            is_fixable=False,
            issue_domain=DOMAIN,
            learn_more_url=BASE_URL,
            severity=severity,
            translation_key=issue_status,
            translation_placeholders=placeholders,
        )

    _async_update_health_issues(hass, entry, coordinator, vehicle)


@callback
def _async_update_health_issues(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: EudaCoordinator,
    vehicle: str,
) -> None:
    """Create or clear subscription-expiry and stale-snapshot health issues."""
    days_until = coordinator.days_until_subscription_expires
    sub_issue_id = _issue_id(entry.entry_id, "subscription_expiring_soon")
    if (
        days_until is not None
        and days_until <= SUBSCRIPTION_WARNING_BEFORE.days
    ):
        ir.async_create_issue(
            hass,
            DOMAIN,
            sub_issue_id,
            data={"entry_id": entry.entry_id},
            is_fixable=False,
            issue_domain=DOMAIN,
            learn_more_url=BASE_URL,
            severity=ir.IssueSeverity.WARNING,
            translation_key="subscription_expiring_soon",
            translation_placeholders={
                "portal_url": BASE_URL,
                "vehicle": vehicle,
                "days_until": str(days_until),
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, sub_issue_id)

    minutes_since = coordinator.minutes_since_last_snapshot
    stale_issue_id = _issue_id(entry.entry_id, "stale_snapshot")
    if coordinator.is_snapshot_stale and minutes_since is not None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            stale_issue_id,
            data={"entry_id": entry.entry_id},
            is_fixable=False,
            issue_domain=DOMAIN,
            learn_more_url=BASE_URL,
            severity=ir.IssueSeverity.WARNING,
            translation_key="stale_snapshot",
            translation_placeholders={
                "portal_url": BASE_URL,
                "vehicle": vehicle,
                "hours_since": str(minutes_since // 60),
                "minutes_since": str(minutes_since),
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, stale_issue_id)


@callback
def async_clear_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove all portal-state issues when the config entry is unloaded."""
    for status in _ALL_ISSUE_KEYS:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(entry.entry_id, status))
