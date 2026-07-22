"""Config-entry diagnostics download (redacted)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BRAND,
    CONF_EMAIL,
    CONF_IDENTIFIER,
    CONF_NICKNAME,
    CONF_PASSWORD,
    CONF_VIN,
    DOMAIN,
)
from .data import (
    CURATED_FIELDS,
    detect_dataset_format,
    field_coverage,
    redact_dataset_filename,
    timestamp_support_snapshot,
)

_MANIFEST = json.loads((Path(__file__).parent / "manifest.json").read_text())

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_VIN,
    CONF_IDENTIFIER,
    "listing_identifier",
    "user_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for support and field-coverage checks."""
    coordinator = entry.runtime_data.coordinator
    points = coordinator.data or {}
    dataset = coordinator.latest_dataset
    vin = entry.data.get(CONF_VIN)

    payload: dict[str, Any] = {
        "integration": {
            "domain": DOMAIN,
            "version": _MANIFEST.get("version"),
            "brand": entry.data.get(CONF_BRAND),
            "nickname": entry.data.get(CONF_NICKNAME),
        },
        "status": {
            "label": coordinator.status_label,
            "empty_snapshot_count": coordinator.empty_snapshot_count,
            "consecutive_server_errors": coordinator.consecutive_server_errors,
            "next_retry_minutes": int(
                coordinator.update_interval.total_seconds() // 60
            ),
            "has_data": bool(points),
            "dataset_format": detect_dataset_format(points) if points else None,
            "subscription_created_on": (
                coordinator.subscription_created_on.isoformat()
                if coordinator.subscription_created_on
                else None
            ),
            "listing_identifier": coordinator.listing_identifier,
            "days_until_subscription_expires": coordinator.days_until_subscription_expires,
            "minutes_since_last_snapshot": coordinator.minutes_since_last_snapshot,
        },
        "latest_dataset": None,
        "timestamps": timestamp_support_snapshot(points) if points else None,
        "field_coverage": field_coverage(points) if points else None,
        "uncurated_fields_sample": (
            field_coverage(points)["uncurated_fields"][:20] if points else None
        ),
        "config_entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            CONF_VIN: entry.data.get(CONF_VIN),
            CONF_IDENTIFIER: entry.data.get(CONF_IDENTIFIER),
            CONF_EMAIL: entry.data.get(CONF_EMAIL),
        },
    }

    if dataset or coordinator.latest_dataset_name or coordinator.last_download_attempts:
        latest_dataset: dict[str, Any] = {
            "name": redact_dataset_filename(coordinator.latest_dataset_name, vin),
            "last_download_attempts": coordinator.last_download_attempts,
        }
        if dataset:
            latest_dataset.update(
                {
                    "captured_at": dataset.captured_at.isoformat()
                    if dataset.captured_at
                    else None,
                    "point_count": len(dataset.points),
                    "sample_fields": sorted(
                        {dp.field_name for dp in dataset.points.values()}
                        & CURATED_FIELDS
                    )[:20],
                }
            )
        payload["latest_dataset"] = latest_dataset

    cached = coordinator.cached_datasets()
    if cached:
        payload["cached_datasets"] = [
            {**item, "name": redact_dataset_filename(item.get("name"), vin)}
            for item in cached[:3]
        ]

    return async_redact_data(payload, TO_REDACT)
