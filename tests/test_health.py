"""Subscription health, snapshot age, and uncurated-field diagnostic tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cupra_eu_data_act.binary_sensor import (
    EudaSnapshotStaleBinarySensor,
)
from custom_components.cupra_eu_data_act.const import (
    CONF_IDENTIFIER,
    CONF_STALE_SNAPSHOT_HOURS,
    CONF_VIN,
    DOMAIN,
    NO_CONTENT_SUFFIX,
    SNAPSHOT_STALE_THRESHOLD,
    SUBSCRIPTION_VALIDITY,
)
from custom_components.cupra_eu_data_act.coordinator import EudaCoordinator
from custom_components.cupra_eu_data_act.data import Dataset
from custom_components.cupra_eu_data_act.issues import async_update_issues
from custom_components.cupra_eu_data_act.sensor import (
    EudaDaysUntilSubscriptionExpiresSensor,
    EudaMinutesSinceLastSnapshotSensor,
    EudaUncuratedFieldsCountSensor,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "sample_dataset.json"


def _make_entry(hass, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VIN: "WVWZZZTESTVIN0001", CONF_IDENTIFIER: "ident-1"},
        options=options or {},
        unique_id="WVWZZZTESTVIN0001",
    )
    entry.add_to_hass(hass)
    return entry


def _make_coordinator(hass, client=None) -> EudaCoordinator:
    entry = _make_entry(hass)
    return EudaCoordinator(hass, entry, client or MagicMock())


def test_listing_metadata_tracks_subscription_and_content(hass) -> None:
    coordinator = _make_coordinator(hass)
    listing = [
        {
            "name": f"WVWZZZTESTVIN0001_20250101000000{NO_CONTENT_SUFFIX}",
            "createdOn": "2025-01-01T00:00:00Z",
        },
        {
            "name": "WVWZZZTESTVIN0001_20250601000000.zip",
            "createdOn": "2025-06-01T00:00:00Z",
        },
    ]
    coordinator._update_listing_metadata(listing)

    assert coordinator.listing_identifier == "ident-1"
    assert coordinator.subscription_created_on == datetime(
        2025, 1, 1, tzinfo=timezone.utc
    )
    assert coordinator.last_listing_content_at == datetime(
        2025, 6, 1, tzinfo=timezone.utc
    )


def test_days_until_subscription_expires(hass, monkeypatch) -> None:
    coordinator = _make_coordinator(hass)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    coordinator.subscription_created_on = now - SUBSCRIPTION_VALIDITY + timedelta(days=10)

    assert coordinator.days_until_subscription_expires == 10


def test_minutes_since_last_snapshot_prefers_car_captured_time(hass, monkeypatch) -> None:
    coordinator = _make_coordinator(hass)
    payload = json.loads(_FIXTURE.read_text())
    coordinator.latest_dataset = Dataset.from_json(payload)
    coordinator.data = coordinator.latest_dataset.points
    now = datetime(2026, 5, 29, 23, 59, 27, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)

    assert coordinator.minutes_since_last_snapshot == 60
    assert coordinator.is_snapshot_stale is False


def test_minutes_since_ignores_fresh_zip_listing(hass, monkeypatch) -> None:
    """Portal ZIP createdOn must not mask old vehicle telemetry (#77)."""
    coordinator = _make_coordinator(hass)
    payload = json.loads(_FIXTURE.read_text())
    coordinator.latest_dataset = Dataset.from_json(payload)
    coordinator.data = coordinator.latest_dataset.points
    now = datetime(2026, 5, 29, 23, 59, 27, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    # Fresh ZIP delivery while car_captured_time is still an hour old.
    coordinator.last_listing_content_at = now

    assert coordinator.minutes_since_last_snapshot == 60
    assert coordinator.is_snapshot_stale is False


def test_minutes_since_falls_back_to_field_timestamp_utc(hass, monkeypatch) -> None:
    """Flat/PHEV payloads without car_captured_* still expose age (#77)."""
    coordinator = _make_coordinator(hass)
    captured = datetime(2026, 10, 26, 16, 18, 45, tzinfo=timezone.utc)
    dataset = Dataset.from_json(
        {
            "vin": "VSSZZZTESTVIN0001",
            "user_id": "u",
            "Data": [
                {
                    "key": "k1",
                    "dataFieldName": "state_of_charge",
                    "value": "55",
                    "timestampUtc": captured.isoformat().replace("+00:00", "Z"),
                }
            ],
        }
    )
    coordinator.latest_dataset = dataset
    coordinator.data = dataset.points
    now = captured + timedelta(hours=40)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    coordinator.last_listing_content_at = now

    assert dataset.captured_at == captured
    assert coordinator.minutes_since_last_snapshot == 40 * 60
    assert coordinator.is_snapshot_stale is True


def test_minutes_since_prefers_fresher_timestamp_utc_over_frozen_capture(
    hass, monkeypatch
) -> None:
    """A frozen car_captured_* must not mask fresher per-field stamps (#77)."""
    coordinator = _make_coordinator(hass)
    frozen = datetime(2026, 9, 28, 9, 49, 6, tzinfo=timezone.utc)
    fresh = datetime(2026, 10, 3, 17, 0, 10, tzinfo=timezone.utc)
    dataset = Dataset.from_json(
        {
            "vin": "VSSZZZTESTVIN0001",
            "user_id": "u",
            "Data": [
                {
                    "key": "k0",
                    "dataFieldName": "car_captured_time",
                    "value": frozen.isoformat().replace("+00:00", "Z"),
                },
                {
                    "key": "k1",
                    "dataFieldName": "state_of_charge",
                    "value": "82",
                    "timestampUtc": fresh.isoformat().replace("+00:00", "Z"),
                },
            ],
        }
    )
    coordinator.latest_dataset = dataset
    coordinator.data = dataset.points
    now = fresh + timedelta(hours=1)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)

    assert dataset.captured_at == fresh
    assert coordinator.minutes_since_last_snapshot == 60
    assert coordinator.is_snapshot_stale is False


async def test_subscription_expiring_issue(hass, monkeypatch) -> None:
    entry = _make_entry(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    coordinator.subscription_created_on = now - SUBSCRIPTION_VALIDITY + timedelta(days=20)

    async_update_issues(hass, entry, coordinator)

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"{entry.entry_id}_subscription_expiring_soon"
    )
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING


async def test_stale_snapshot_issue_and_clear(hass, monkeypatch) -> None:
    entry = _make_entry(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    stale_at = now - SNAPSHOT_STALE_THRESHOLD - timedelta(hours=1)
    coordinator.latest_dataset = MagicMock(captured_at=stale_at)
    coordinator.data = {}
    coordinator.status_label = "ok"

    async_update_issues(hass, entry, coordinator)
    issue_id = f"{entry.entry_id}_stale_snapshot"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    assert coordinator.is_snapshot_stale is True

    coordinator.latest_dataset = MagicMock(captured_at=now)
    async_update_issues(hass, entry, coordinator)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert coordinator.is_snapshot_stale is False


async def test_stale_snapshot_issue_despite_fresh_zip(hass, monkeypatch) -> None:
    """Replayed old snapshots in new ZIPs must still raise the repairs issue."""
    entry = _make_entry(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    coordinator.last_listing_content_at = now
    coordinator.latest_dataset = MagicMock(
        captured_at=now - SNAPSHOT_STALE_THRESHOLD - timedelta(hours=1)
    )
    coordinator.data = {}
    coordinator.status_label = "ok"

    async_update_issues(hass, entry, coordinator)
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f"{entry.entry_id}_stale_snapshot"
        )
        is not None
    )


def test_snapshot_stale_binary_sensor(hass, monkeypatch) -> None:
    coordinator = _make_coordinator(hass)
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    sensor = EudaSnapshotStaleBinarySensor(coordinator)

    assert sensor.is_on is None

    coordinator.latest_dataset = MagicMock(captured_at=now - timedelta(hours=1))
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["stale_threshold_hours"] == 12

    coordinator.latest_dataset = MagicMock(
        captured_at=now - SNAPSHOT_STALE_THRESHOLD - timedelta(minutes=1)
    )
    assert sensor.is_on is True


async def test_stale_threshold_from_options(hass, monkeypatch) -> None:
    """A longer window keeps a sleeping car's last snapshot from raising the issue."""
    entry = _make_entry(hass, {CONF_STALE_SNAPSHOT_HOURS: 48})
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    coordinator.latest_dataset = MagicMock(captured_at=now - timedelta(hours=20))
    coordinator.data = {}
    coordinator.status_label = "ok"
    issue_id = f"{entry.entry_id}_stale_snapshot"

    async_update_issues(hass, entry, coordinator)
    assert coordinator.is_snapshot_stale is False
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert (
        EudaSnapshotStaleBinarySensor(coordinator).extra_state_attributes[
            "stale_threshold_hours"
        ]
        == 48
    )

    coordinator.latest_dataset = MagicMock(captured_at=now - timedelta(hours=49))
    async_update_issues(hass, entry, coordinator)
    assert coordinator.is_snapshot_stale is True
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None


async def test_stale_check_off_clears_issue(hass, monkeypatch) -> None:
    """0 hours turns the check off: no issue, binary sensor unknown."""
    entry = _make_entry(hass)
    coordinator = EudaCoordinator(hass, entry, MagicMock())
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    coordinator.latest_dataset = MagicMock(captured_at=now - timedelta(days=3))
    coordinator.data = {}
    coordinator.status_label = "ok"
    issue_id = f"{entry.entry_id}_stale_snapshot"
    async_update_issues(hass, entry, coordinator)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    hass.config_entries.async_update_entry(
        entry, options={CONF_STALE_SNAPSHOT_HOURS: 0}
    )
    async_update_issues(hass, entry, coordinator)
    assert coordinator.is_snapshot_stale is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    sensor = EudaSnapshotStaleBinarySensor(coordinator)
    assert sensor.is_on is None
    assert sensor.extra_state_attributes["stale_threshold_hours"] == 0


def test_health_sensor_values(hass, monkeypatch) -> None:
    coordinator = _make_coordinator(hass)
    payload = json.loads(_FIXTURE.read_text())
    coordinator.latest_dataset = Dataset.from_json(payload)
    coordinator.data = coordinator.latest_dataset.points
    coordinator.subscription_created_on = datetime(2025, 6, 1, tzinfo=timezone.utc)
    now = datetime(2026, 5, 29, 23, 59, 27, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)

    days_sensor = EudaDaysUntilSubscriptionExpiresSensor(coordinator)
    minutes_sensor = EudaMinutesSinceLastSnapshotSensor(coordinator)
    uncurated_sensor = EudaUncuratedFieldsCountSensor(coordinator)

    assert days_sensor.native_value is not None
    assert minutes_sensor.native_value == 60
    assert uncurated_sensor.native_value == 1  # range.unit (report_type omitted)
