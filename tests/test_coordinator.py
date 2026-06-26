"""Coordinator tests: authentication failures surface as ConfigEntryAuthFailed.

An expired/invalid login must trigger Home Assistant's reauth flow, not be
swallowed as a transient polling error. AuthError is a subclass of ApiError, so
the coordinator has to catch it *before* the generic ApiError handling in both
the dataset-listing and dataset-download paths.
"""
from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cupra_eu_data_act.api import ApiError, AuthError, EudaApiClient
from custom_components.cupra_eu_data_act.const import (
    CONF_IDENTIFIER,
    CONF_VIN,
    DOMAIN,
    SERVER_ERROR_BACKOFF_INTERVALS,
)
from custom_components.cupra_eu_data_act.coordinator import EudaCoordinator
from custom_components.cupra_eu_data_act.data import DataPoint


def _zip_bytes(payload: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps(payload))
    return buf.getvalue()


def _mock_client_with_zip(client: MagicMock, payload: dict) -> None:
    client.async_download_dataset_raw = AsyncMock(return_value=_zip_bytes(payload))
    client.parse_dataset_zip = EudaApiClient.parse_dataset_zip


def _make_coordinator(hass, client) -> EudaCoordinator:
    """Build a coordinator the way async_setup_entry does."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VIN: "WVWZZZTESTVIN0001", CONF_IDENTIFIER: "ident-1"},
        unique_id="WVWZZZTESTVIN0001",
    )
    entry.add_to_hass(hass)
    return EudaCoordinator(hass, entry, client)


async def test_auth_error_while_listing_raises_reauth(hass) -> None:
    client = MagicMock()
    client.async_list_datasets = AsyncMock(side_effect=AuthError("invalid token"))
    coordinator = _make_coordinator(hass, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_auth_error_while_downloading_raises_reauth(hass) -> None:
    # Listing succeeds, but the download leg hits an expired session. Because
    # AuthError subclasses ApiError, this previously fell into the retry/skip
    # branch instead of triggering reauth.
    client = MagicMock()
    client.async_list_datasets = AsyncMock(
        return_value=[
            {
                "name": "WVWZZZTESTVIN0001_20260101000000.zip",
                "createdOn": "2026-01-01T00:00:00Z",
            }
        ]
    )
    client.async_download_dataset_raw = AsyncMock(
        side_effect=AuthError("session expired")
    )
    coordinator = _make_coordinator(hass, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_http_400_with_existing_data_keeps_previous(hass) -> None:
    client = MagicMock()
    client.async_list_datasets = AsyncMock(
        side_effect=ApiError("HTTP 400", status=400)
    )
    client.async_get_metadata = AsyncMock(
        side_effect=ApiError("no metadata", status=400)
    )
    coordinator = _make_coordinator(hass, client)
    previous = {
        "key-1": DataPoint(
            key="key-1",
            field_name="mileage",
            raw_value="1000",
        )
    }
    coordinator.data = previous

    result = await coordinator._async_update_data()

    assert result is previous
    assert coordinator.status_label == "delivery_not_ready"


async def test_merge_keeps_good_value_when_new_snapshot_has_sentinel(hass) -> None:
    client = MagicMock()
    client.async_list_datasets = AsyncMock(
        return_value=[
            {
                "name": "WVWZZZTESTVIN0001_20260102000000.zip",
                "createdOn": "2026-01-02T00:00:00Z",
            }
        ]
    )
    _mock_client_with_zip(
        client,
        {
            "user_id": "u1",
            "Data": [
                {
                    "key": "key-1",
                    "dataFieldName": "battery",
                    "value": "4294967295",
                }
            ],
        },
    )
    coordinator = _make_coordinator(hass, client)
    coordinator.data = {
        "key-1": DataPoint(
            key="key-1",
            field_name="battery",
            raw_value="72",
        )
    }

    result = await coordinator._async_update_data()

    assert result["key-1"].value == 72


async def test_plain_api_error_does_not_raise_reauth(hass) -> None:
    # A generic (non-auth) failure on first load must surface as a normal
    # UpdateFailed / EudaUpdateNotReady, never as a reauth trigger. A 400
    # ("data delivery not ready") is not retried, so this stays deterministic.
    client = MagicMock()
    client.async_list_datasets = AsyncMock(
        side_effect=ApiError("HTTP 400", status=400)
    )
    client.async_get_metadata = AsyncMock(
        side_effect=ApiError("no metadata", status=400)
    )
    coordinator = _make_coordinator(hass, client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_successful_download_sets_latest_dataset_name(hass) -> None:
    dataset_name = "WVWZZZTESTVIN0001_20260102000000.zip"
    client = MagicMock()
    client.async_list_datasets = AsyncMock(
        return_value=[
            {
                "name": dataset_name,
                "createdOn": "2026-01-02T00:00:00Z",
            }
        ]
    )
    _mock_client_with_zip(
        client,
        {
            "user_id": "u1",
            "Data": [
                {
                    "key": "key-1",
                    "dataFieldName": "mileage",
                    "value": "12345",
                }
            ],
        },
    )
    coordinator = _make_coordinator(hass, client)

    await coordinator._async_update_data()

    assert coordinator.latest_dataset_name == dataset_name
    assert len(coordinator.cached_datasets()) == 1
    assert coordinator.cached_datasets()[0]["name"] == dataset_name
    assert len(coordinator.last_download_attempts) == 1
    assert coordinator.last_download_attempts[0]["name"] == dataset_name
    assert coordinator.last_download_attempts[0]["success"] is True
    assert coordinator.last_download_attempts[0]["error"] is None
    assert coordinator.last_download_attempts[0]["at"]


async def test_http_503_listing_restores_from_cache_when_no_memory_data(hass) -> None:
    client = MagicMock()
    client.async_list_datasets = AsyncMock(
        side_effect=ApiError("HTTP 503", status=503)
    )
    client.async_get_metadata = AsyncMock(
        side_effect=ApiError("no metadata", status=400)
    )
    _mock_client_with_zip(
        client,
        {
            "user_id": "u1",
            "Data": [
                {
                    "key": "key-1",
                    "dataFieldName": "battery_state_report.soc",
                    "value": "72",
                }
            ],
        },
    )
    coordinator = _make_coordinator(hass, client)
    dataset_name = "WVWZZZTESTVIN0001_20260101000000.zip"
    coordinator._store_in_cache(dataset_name, _zip_bytes({"user_id": "u1", "Data": []}))
    coordinator._store_in_cache(
        dataset_name,
        _zip_bytes(
            {
                "user_id": "u1",
                "Data": [
                    {
                        "key": "key-1",
                        "dataFieldName": "battery_state_report.soc",
                        "value": "72",
                    }
                ],
            }
        ),
    )

    result = await coordinator._async_update_data()

    assert result["key-1"].value == 72
    assert coordinator.status_label == "listing_failed"
    assert coordinator.latest_dataset_name == dataset_name


async def test_corrupt_cache_is_skipped_and_deleted_on_restore(hass) -> None:
    # A truncated download or portal error body saved as a ZIP must not block
    # restore: the unreadable file is dropped and the next-newest readable
    # dataset is used instead (regression for setup crash on BadZipFile).
    client = MagicMock()
    client.parse_dataset_zip = EudaApiClient.parse_dataset_zip
    coordinator = _make_coordinator(hass, client)
    good_name = "WVWZZZTESTVIN0001_20260101000000.zip"
    bad_name = "WVWZZZTESTVIN0001_20260102000000.zip"
    coordinator._cache.store(
        coordinator.vin,
        good_name,
        _zip_bytes(
            {
                "user_id": "u1",
                "Data": [
                    {
                        "key": "key-1",
                        "dataFieldName": "battery_state_report.soc",
                        "value": "72",
                    }
                ],
            }
        ),
    )
    coordinator._cache.store(coordinator.vin, bad_name, b"not a zip file")

    points = await coordinator.async_restore_from_cache()

    assert points is not None
    assert points["key-1"].value == 72
    assert coordinator.latest_dataset_name == good_name
    assert coordinator._cache.read(coordinator.vin, bad_name) is None


async def test_http_503_listing_sets_listing_failed_and_backoff(hass) -> None:
    client = MagicMock()
    client.async_list_datasets = AsyncMock(
        side_effect=ApiError("HTTP 503", status=503)
    )
    client.async_get_metadata = AsyncMock(
        side_effect=ApiError("no metadata", status=400)
    )
    coordinator = _make_coordinator(hass, client)
    coordinator.data = {
        "key-1": DataPoint(key="key-1", field_name="mileage", raw_value="1000")
    }

    result = await coordinator._async_update_data()

    assert result is coordinator.data
    assert coordinator.status_label == "listing_failed"
    assert coordinator.consecutive_server_errors == 1
    assert coordinator.update_interval == SERVER_ERROR_BACKOFF_INTERVALS[0]


async def test_consecutive_503_increases_backoff(hass) -> None:
    client = MagicMock()
    client.async_list_datasets = AsyncMock(
        side_effect=ApiError("HTTP 503", status=503)
    )
    client.async_get_metadata = AsyncMock(
        side_effect=ApiError("no metadata", status=400)
    )
    coordinator = _make_coordinator(hass, client)
    coordinator.data = {
        "key-1": DataPoint(key="key-1", field_name="mileage", raw_value="1000")
    }
    coordinator._consecutive_server_errors = 1
    coordinator.update_interval = SERVER_ERROR_BACKOFF_INTERVALS[0]

    await coordinator._async_update_data()

    assert coordinator.consecutive_server_errors == 2
    assert coordinator.update_interval == SERVER_ERROR_BACKOFF_INTERVALS[1]


async def test_successful_load_resets_server_error_backoff(hass) -> None:
    dataset_name = "WVWZZZTESTVIN0001_20260102000000.zip"
    client = MagicMock()
    client.async_list_datasets = AsyncMock(
        return_value=[
            {
                "name": dataset_name,
                "createdOn": "2026-01-02T00:00:00Z",
            }
        ]
    )
    _mock_client_with_zip(
        client,
        {
            "user_id": "u1",
            "Data": [
                {
                    "key": "key-1",
                    "dataFieldName": "mileage",
                    "value": "12345",
                }
            ],
        },
    )
    coordinator = _make_coordinator(hass, client)
    coordinator._consecutive_server_errors = 2
    coordinator.update_interval = SERVER_ERROR_BACKOFF_INTERVALS[1]

    await coordinator._async_update_data()

    assert coordinator.consecutive_server_errors == 0
    assert coordinator.status_label == "ok"
