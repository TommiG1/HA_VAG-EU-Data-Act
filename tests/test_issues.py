"""Repairs issue lifecycle tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cupra_eu_data_act.const import CONF_IDENTIFIER, CONF_VIN, DOMAIN
from custom_components.cupra_eu_data_act.coordinator import EudaCoordinator
from custom_components.cupra_eu_data_act.issues import async_clear_issues, async_update_issues


def _make_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VIN: "WVWZZZTESTVIN0001", CONF_IDENTIFIER: "ident-1"},
        unique_id="WVWZZZTESTVIN0001",
    )
    entry.add_to_hass(hass)
    return entry


async def test_delivery_not_ready_creates_issue(hass) -> None:
    entry = _make_entry(hass)
    client = MagicMock()
    coordinator = EudaCoordinator(hass, entry, client)
    coordinator.status_label = "delivery_not_ready"

    async_update_issues(hass, entry, coordinator)

    registry = ir.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, f"{entry.entry_id}_delivery_not_ready")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.ERROR
    assert issue.learn_more_url is not None


async def test_ok_clears_portal_issues(hass) -> None:
    entry = _make_entry(hass)
    client = MagicMock()
    coordinator = EudaCoordinator(hass, entry, client)
    coordinator.status_label = "delivery_not_ready"
    async_update_issues(hass, entry, coordinator)

    coordinator.status_label = "ok"
    async_update_issues(hass, entry, coordinator)

    registry = ir.async_get(hass)
    assert (
        registry.async_get_issue(DOMAIN, f"{entry.entry_id}_delivery_not_ready") is None
    )


async def test_listing_failed_creates_issue(hass) -> None:
    entry = _make_entry(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    coordinator.status_label = "listing_failed"
    coordinator.update_interval = __import__(
        "datetime"
    ).timedelta(minutes=15)

    async_update_issues(hass, entry, coordinator)

    registry = ir.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, f"{entry.entry_id}_listing_failed")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_placeholders["retry_minutes"] == "15"


async def test_waiting_for_portal_data_creates_issue_without_data(hass) -> None:
    entry = _make_entry(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    coordinator.status_label = "waiting_for_portal_data"
    coordinator.data = None

    async_update_issues(hass, entry, coordinator)

    registry = ir.async_get(hass)
    assert (
        registry.async_get_issue(DOMAIN, f"{entry.entry_id}_waiting_for_portal_data")
        is not None
    )


async def test_waiting_for_portal_data_skipped_when_data_present(hass) -> None:
    """Cached/previous data must not raise the 'first dataset' repair (#77)."""
    entry = _make_entry(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    coordinator.status_label = "waiting_for_portal_data"
    coordinator.data = {"battery_state_report.soc": MagicMock()}

    async_update_issues(hass, entry, coordinator)

    registry = ir.async_get(hass)
    assert (
        registry.async_get_issue(DOMAIN, f"{entry.entry_id}_waiting_for_portal_data")
        is None
    )


async def test_waiting_for_portal_data_clears_when_data_arrives(hass) -> None:
    entry = _make_entry(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    coordinator.status_label = "waiting_for_portal_data"
    coordinator.data = None
    async_update_issues(hass, entry, coordinator)

    coordinator.data = {"battery_state_report.soc": MagicMock()}
    async_update_issues(hass, entry, coordinator)

    registry = ir.async_get(hass)
    assert (
        registry.async_get_issue(DOMAIN, f"{entry.entry_id}_waiting_for_portal_data")
        is None
    )


async def test_unload_clears_all_issues(hass) -> None:
    entry = _make_entry(hass)
    client = MagicMock()
    coordinator = EudaCoordinator(hass, entry, client)
    coordinator.status_label = "empty_snapshots"
    coordinator.empty_snapshot_count = 3
    async_update_issues(hass, entry, coordinator)

    async_clear_issues(hass, entry)

    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, f"{entry.entry_id}_empty_snapshots") is None


async def test_unload_clears_health_issues(hass, monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from homeassistant.util import dt as dt_util

    from custom_components.cupra_eu_data_act.const import SUBSCRIPTION_VALIDITY

    entry = _make_entry(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    coordinator.subscription_created_on = now - SUBSCRIPTION_VALIDITY + timedelta(days=5)
    async_update_issues(hass, entry, coordinator)

    async_clear_issues(hass, entry)

    registry = ir.async_get(hass)
    assert (
        registry.async_get_issue(
            DOMAIN, f"{entry.entry_id}_subscription_expiring_soon"
        )
        is None
    )
