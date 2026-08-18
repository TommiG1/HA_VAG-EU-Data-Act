"""Coordinator: dynamic-interval refresh of the latest dataset."""

from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ApiError, AuthError, EudaApiClient
from .cache import DatasetCache
from .const import (
    BASE_URL,
    CACHE_DIR_NAME,
    CONF_IDENTIFIER,
    CONF_VIN,
    DATASET_INTERVAL,
    DOMAIN,
    MAX_CACHE_BYTES_PER_VIN,
    MAX_CACHED_DATASETS,
    MIN_INTERVAL,
    NO_CONTENT_SUFFIX,
    POST_DATASET_BUFFER,
    RETRY_INTERVAL,
    SERVER_ERROR_BACKOFF_INTERVALS,
    SUBSCRIPTION_VALIDITY,
    TRANSIENT_HTTP_STATUSES,
)
from .data import Dataset, DataPoint, latest_captured_time, merge_data_points, stamp_source_dataset

_LOGGER = logging.getLogger(__name__)

def _is_server_error(err: Exception) -> bool:
    """True for transient HTTP ApiErrors we should retry instead of giving up."""
    return isinstance(err, ApiError) and err.status in TRANSIENT_HTTP_STATUSES


class EudaUpdateNotReady(UpdateFailed):
    """UpdateFailed that maps to a translated ConfigEntryNotReady message."""

    def __init__(
        self,
        translation_key: str,
        *,
        translation_placeholders: dict[str, str] | None = None,
    ) -> None:
        super().__init__(translation_key)
        self.translation_key = translation_key
        self.translation_placeholders = translation_placeholders or {}


def _filename_timestamp(name: str) -> datetime | None:
    """Parse a YYYYMMDDhhmmss segment from a dataset filename.

    Handles both layouts seen in the wild ("TIMESTAMP_VIN.zip" and
    "VIN_TIMESTAMP.zip") by scanning the underscore-separated parts
    right-to-left for the first one that parses as a timestamp.
    """
    stem = name.rsplit(".", 1)[0]
    for part in reversed(stem.split("_")):
        try:
            return datetime.strptime(part, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _created_on(entry: dict) -> datetime | None:
    raw = entry.get("createdOn")
    if not raw:
        return _filename_timestamp(entry.get("name", ""))
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return _filename_timestamp(entry.get("name", ""))


class EudaCoordinator(DataUpdateCoordinator[dict[str, DataPoint]]):
    """Fetches the latest dataset and reschedules adaptively."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: EudaApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            # Pass the entry explicitly; relying on the ContextVar is
            # deprecated and breaks in HA 2026.8.
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_VIN]}",
            update_interval=RETRY_INTERVAL,
        )
        self.entry = entry
        self.client = client
        self.vin: str = entry.data[CONF_VIN]
        self.identifier: str = entry.data[CONF_IDENTIFIER]
        self.latest_dataset: Dataset | None = None
        self._is_initial_setup: bool = True
        # Human-readable status the diagnostic sensor surfaces; updated by
        # _async_update_data on each refresh.
        self.status_label: str = "starting"
        self.empty_snapshot_count: int = 0
        # Earliest createdOn seen in the dataset listing (proxy for subscription
        # start); refreshed on every list call.
        self.subscription_created_on: datetime | None = None
        self.listing_identifier: str | None = entry.data.get(CONF_IDENTIFIER)
        # Newest createdOn among content (non-empty) listing entries.
        self.last_listing_content_at: datetime | None = None
        # When the portal generated the currently loaded dataset ZIP.
        self.dataset_created_at: datetime | None = None
        self.latest_dataset_name: str | None = None
        self.last_download_attempts: list[dict] = []
        self._cache = DatasetCache(
            Path(hass.config.path(CACHE_DIR_NAME)),
            max_files=MAX_CACHED_DATASETS,
            max_bytes_per_vin=MAX_CACHE_BYTES_PER_VIN,
        )
        # In-memory snapshot of the cache listing. Disk I/O only happens in the
        # executor (after each store); sensor attributes read this without
        # blocking the event loop.
        self._cached_dataset_meta: list[dict] | None = None
        # True when the last listing call failed but previous data was kept, so
        # the no-content branch must not overwrite e.g. "delivery_not_ready".
        self._listing_failed: bool = False
        # Consecutive refresh cycles that ended in a portal 5xx without new data.
        self._consecutive_server_errors: int = 0

    def cached_datasets(self) -> list[dict]:
        """Return cached ZIP metadata (in-memory; safe in the event loop)."""
        return self._cached_dataset_meta or []

    @property
    def consecutive_server_errors(self) -> int:
        """Portal 5xx streak without a successful dataset load."""
        return self._consecutive_server_errors

    def _server_error_backoff_interval(self) -> timedelta:
        """Map consecutive 5xx count to 5 → 15 → 30 minute retry spacing."""
        if self._consecutive_server_errors <= 0:
            return RETRY_INTERVAL
        index = min(
            self._consecutive_server_errors - 1,
            len(SERVER_ERROR_BACKOFF_INTERVALS) - 1,
        )
        return SERVER_ERROR_BACKOFF_INTERVALS[index]

    def _note_server_error(self) -> None:
        """Slow down polling after a transient portal outage."""
        self._consecutive_server_errors += 1
        self.update_interval = self._server_error_backoff_interval()
        _LOGGER.debug(
            "Portal server error streak %d; next retry in %s",
            self._consecutive_server_errors,
            self.update_interval,
        )

    def _reset_server_error_backoff(self) -> None:
        """Restore normal scheduling after a successful dataset load."""
        self._consecutive_server_errors = 0

    def _store_in_cache(self, name: str, data: bytes) -> list[dict]:
        """Write a ZIP and return fresh listing metadata (executor only)."""
        self._cache.store(self.vin, name, data)
        return [
            {
                "name": item.name,
                "size": item.size,
                "mtime": item.mtime.isoformat(),
            }
            for item in self._cache.list_entries(self.vin)
        ]

    def _parse_cached_zip(self, name: str, raw: bytes) -> dict[str, DataPoint] | None:
        """Parse a cached ZIP and update coordinator metadata (executor only)."""
        payload = self.client.parse_dataset_zip(raw, name)
        dataset = Dataset.from_json(payload)
        points = dataset.points
        if not points:
            return None
        self.latest_dataset = dataset
        self.latest_dataset_name = name
        self.dataset_created_at = _filename_timestamp(name)
        self._cached_dataset_meta = [
            {
                "name": item.name,
                "size": item.size,
                "mtime": item.mtime.isoformat(),
            }
            for item in self._cache.list_entries(self.vin)
        ]
        self._is_initial_setup = False
        return stamp_source_dataset(points, name)

    async def async_restore_from_cache(self) -> dict[str, DataPoint] | None:
        """Load the newest readable local ZIP when memory was cleared (e.g. after HA restart).

        Unreadable cache files (truncated downloads, portal error bodies saved as
        ZIPs) are dropped and older datasets are tried, so a corrupt cache never
        blocks setup.
        """

        def _restore() -> tuple[str, dict[str, DataPoint]] | None:
            for entry in self._cache.list_entries(self.vin):
                raw = self._cache.read(self.vin, entry.name)
                if raw is None:
                    continue
                try:
                    points = self._parse_cached_zip(entry.name, raw)
                except ApiError as err:
                    _LOGGER.warning(
                        "Discarding unreadable cached dataset %s: %s",
                        entry.name,
                        err,
                    )
                    self._cache.delete(self.vin, entry.name)
                    continue
                if points:
                    return entry.name, points
            return None

        result = await self.hass.async_add_executor_job(_restore)
        if not result:
            return None
        name, points = result
        _LOGGER.info(
            "Restored vehicle data from local cache (%s, %d fields)",
            name,
            len(points),
        )
        return points

    def _record_download_attempt(
        self,
        name: str,
        *,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Append a download outcome; keep the last five for diagnostics."""
        self.last_download_attempts.append(
            {
                "name": name,
                "success": success,
                "error": error,
                "at": dt_util.utcnow().isoformat(),
            }
        )
        if len(self.last_download_attempts) > 5:
            self.last_download_attempts = self.last_download_attempts[-5:]

    @property
    def last_snapshot_at(self) -> datetime | None:
        """Best-known timestamp of the last real (non-empty) vehicle snapshot."""
        candidates: list[datetime] = []
        if self.last_listing_content_at is not None:
            candidates.append(self.last_listing_content_at)
        if self.latest_dataset and self.latest_dataset.captured_at is not None:
            candidates.append(self.latest_dataset.captured_at)
        if ts := latest_captured_time(self.data or {}):
            candidates.append(ts)
        return max(candidates) if candidates else None

    @property
    def days_until_subscription_expires(self) -> int | None:
        """Estimated days until the ~12-month portal subscription lapses."""
        if self.subscription_created_on is None:
            return None
        expiry = self.subscription_created_on + SUBSCRIPTION_VALIDITY
        return (expiry - dt_util.utcnow()).days

    @property
    def minutes_since_last_snapshot(self) -> int | None:
        """Minutes since the last real snapshot, or None if unknown."""
        if (snap := self.last_snapshot_at) is None:
            return None
        return int((dt_util.utcnow() - snap).total_seconds() // 60)

    def _update_listing_metadata(self, listing: list[dict]) -> None:
        """Track subscription and snapshot timing from the dataset listing."""
        self.listing_identifier = self.identifier
        timestamps = [
            ts
            for entry in listing
            if entry.get("name") and (ts := _created_on(entry))
        ]
        if timestamps:
            self.subscription_created_on = min(timestamps)
        content_timestamps = [
            ts
            for entry in listing
            if entry.get("name")
            and not entry["name"].endswith(NO_CONTENT_SUFFIX)
            and (ts := _created_on(entry))
        ]
        if content_timestamps:
            self.last_listing_content_at = max(content_timestamps)

    async def _async_update_data(self) -> dict[str, DataPoint]:
        self._listing_failed = False
        cached_points: dict[str, DataPoint] | None = None
        if not self.data:
            cached_points = await self.async_restore_from_cache()

        try:
            listing = await self._async_list_with_refresh()
        except UpdateFailed as err:
            if cached_points:
                self.status_label = "listing_failed"
                _LOGGER.warning(
                    "Portal listing failed (%s); using last cached dataset %s",
                    err,
                    self.latest_dataset_name,
                )
                return cached_points
            raise
        self._update_listing_metadata(listing)

        # content datasets, oldest -> newest by createdOn
        content = sorted(
            (
                e
                for e in listing
                if e.get("name") and not e["name"].endswith(NO_CONTENT_SUFFIX)
            ),
            key=lambda e: _created_on(e) or datetime.min.replace(tzinfo=timezone.utc),
        )
        empty_only = [
            e
            for e in listing
            if e.get("name", "").endswith(NO_CONTENT_SUFFIX)
        ]
        _LOGGER.debug(
            "refresh: %d listed, %d with content, %d empty snapshots",
            len(listing),
            len(content),
            len(empty_only),
        )

        if not content:
            # Listing API failures already set a server-error backoff interval;
            # do not overwrite it with the normal empty-listing schedule.
            if not self._listing_failed:
                self._reschedule(listing)
            self.empty_snapshot_count = len(empty_only)
            if not self._listing_failed:
                # An empty listing caused by a failed list call must not mask
                # the more specific status (e.g. "delivery_not_ready") set by
                # _async_list_with_refresh.
                self.status_label = (
                    "empty_snapshots" if empty_only else "waiting_for_portal_data"
                )
            if self.data:
                # Subsequent refresh: keep previous data
                _LOGGER.debug("No new datasets available, keeping previous data")
                return self.data
            # First load with no data: surface as UpdateFailed so HA logs and
            # retries, but do not raise ConfigEntryNotReady — the entry stays
            # loaded so the user sees a device with the status sensor explaining
            # what is happening.
            if empty_only:
                _LOGGER.info(
                    "Portal delivered %d empty snapshot(s) (_no_content_found); "
                    "vehicle had no telemetry in that 15-minute window. "
                    "Retrying in %s",
                    len(empty_only),
                    RETRY_INTERVAL,
                )
            else:
                _LOGGER.warning(
                    "No datasets available on first load, will retry in %s",
                    RETRY_INTERVAL,
                )
            if empty_only:
                raise EudaUpdateNotReady(
                    "waiting_for_portal_data_empty_snapshots",
                    translation_placeholders={
                        "portal_url": BASE_URL,
                        "empty_count": str(len(empty_only)),
                        "retry_minutes": str(int(RETRY_INTERVAL.total_seconds() // 60)),
                    },
                )
            raise EudaUpdateNotReady(
                "waiting_for_portal_data",
                translation_placeholders={
                    "portal_url": BASE_URL,
                    "retry_minutes": str(int(RETRY_INTERVAL.total_seconds() // 60)),
                },
            )

        # Try to load datasets, starting with newest and falling back to older ones
        last_error = None
        for dataset_entry in reversed(content):
            dataset_name = dataset_entry["name"]
            # Use fewer, faster retries during initial setup for better UX
            # Full retries kick in after first successful load
            max_retries = 3 if self._is_initial_setup else 5
            retry_delay = 3 if self._is_initial_setup else 5
            entry_error: Exception | None = None
            succeeded = False

            for attempt in range(max_retries):
                try:
                    raw = await self.client.async_download_dataset_raw(
                        self.vin, self.identifier, dataset_name
                    )
                    # Parse before caching so invalid bytes (truncated download,
                    # portal error body) never get written to the local cache.
                    payload = self.client.parse_dataset_zip(raw, dataset_name)
                    self._cached_dataset_meta = await self.hass.async_add_executor_job(
                        self._store_in_cache, dataset_name, raw
                    )
                    self.latest_dataset = Dataset.from_json(payload)
                    self.latest_dataset_name = dataset_name
                    self.dataset_created_at = (
                        _created_on(dataset_entry) or self.dataset_created_at
                    )
                    self._is_initial_setup = False
                    succeeded = True
                    entry_error = None
                    _LOGGER.info("Downloaded dataset %s", dataset_name)
                    break
                except AuthError as err:
                    # Session expired or credentials invalidated by the portal;
                    # trigger the HA reauth flow instead of silently retrying.
                    raise ConfigEntryAuthFailed(str(err)) from err
                except ApiError as err:
                    entry_error = err
                    is_server_error = _is_server_error(err)

                    if is_server_error and attempt < max_retries - 1:
                        _LOGGER.debug(
                            "Server error downloading %s (attempt %d/%d): %s, retrying in %ds",
                            dataset_name,
                            attempt + 1,
                            max_retries,
                            err,
                            retry_delay,
                        )
                        await asyncio.sleep(retry_delay)
                        continue
                    elif is_server_error:
                        _LOGGER.warning(
                            "Server error downloading %s after %d attempts: %s, trying previous dataset",
                            dataset_name,
                            max_retries,
                            err,
                        )
                        break
                    else:
                        _LOGGER.warning(
                            "Error downloading %s: %s", dataset_name, err
                        )
                        break

            self._record_download_attempt(
                dataset_name,
                success=succeeded,
                error=str(entry_error) if entry_error else None,
            )

            if succeeded:
                last_error = None
                break

            last_error = entry_error
            if last_error and not _is_server_error(last_error):
                break

        # If all downloads failed
        if last_error:
            if _is_server_error(last_error):
                self._note_server_error()
            else:
                self.update_interval = RETRY_INTERVAL
            if self.data:
                # Subsequent refresh: keep previous data on failure
                _LOGGER.debug(
                    "Could not download any dataset (last error: %s), keeping previous data",
                    last_error,
                )
                if not _is_server_error(last_error):
                    self._reschedule(listing)
                return self.data
            if cached_points:
                self.status_label = "listing_failed"
                _LOGGER.warning(
                    "Could not download any dataset (%s); using last cached dataset %s",
                    last_error,
                    self.latest_dataset_name,
                )
                return cached_points
            # First load failure: raise so HA retries setup
            _LOGGER.error(
                "Could not download any dataset on first load: %s. Will retry in %s.",
                last_error,
                RETRY_INTERVAL,
            )
            raise UpdateFailed(
                f"Failed to download dataset on first load: {last_error}"
            ) from last_error

        self._reschedule(listing)
        self._reset_server_error_backoff()
        self.status_label = "ok"
        self.empty_snapshot_count = 0

        new_points = stamp_source_dataset(
            self.latest_dataset.points, self.latest_dataset_name
        )
        if not new_points:
            if self.data:
                _LOGGER.debug(
                    "Downloaded dataset contained no data points; keeping previous data"
                )
                return self.data
            return new_points

        # Merge new data with existing: keep last good reading per key and for
        # fields omitted or sent as sentinel in the latest snapshot.
        if self.data:
            return merge_data_points(self.data, new_points)

        return new_points

    async def _async_list_with_refresh(self) -> list[dict]:
        """List datasets, self-healing a stale identifier once if needed.

        If the user deletes and recreates the continuous data subscription on
        the portal, the backend assigns a new identifier and the stored one
        stops working (the list errors or returns no files). Re-fetch the
        identifier from the metadata endpoint and retry once before giving up —
        so it recovers on the next cycle without needing a manual reload.
        """
        if not self.identifier:
            if await self._refresh_identifier():
                _LOGGER.info("Data-request identifier appeared during initial setup")
            else:
                self.status_label = "delivery_not_ready"
                raise EudaUpdateNotReady(
                    "delivery_not_ready",
                    translation_placeholders={
                        "portal_url": BASE_URL,
                        "retry_minutes": str(
                            int(RETRY_INTERVAL.total_seconds() // 60)
                        ),
                    },
                )

        # Use fewer, faster retries during initial setup
        max_retries = 3 if self._is_initial_setup else 5
        retry_delay = 3 if self._is_initial_setup else 5

        for identifier_retry in (False, True):
            last_error = None

            for attempt in range(max_retries):
                try:
                    listing = await self.client.async_list_datasets(
                        self.vin, self.identifier
                    )
                    # Empty listing might mean subscription was recreated
                    if (
                        not listing
                        and not identifier_retry
                        and await self._refresh_identifier()
                    ):
                        _LOGGER.info(
                            "Empty listing, retrying with refreshed identifier"
                        )
                        break  # Break inner loop to retry with new identifier
                    return listing

                except AuthError as err:
                    # Surface as ConfigEntryAuthFailed so HA prompts the user
                    # to re-enter credentials (with the brand preserved from
                    # the entry).
                    raise ConfigEntryAuthFailed(str(err)) from err

                except ApiError as err:
                    last_error = err
                    is_server_error = _is_server_error(err)

                    # Retry server errors with delay
                    if is_server_error and attempt < max_retries - 1:
                        _LOGGER.debug(
                            "Server error listing datasets (attempt %d/%d): %s, retrying in %ds",
                            attempt + 1,
                            max_retries,
                            err,
                            retry_delay,
                        )
                        await asyncio.sleep(retry_delay)
                        continue

            # After all retries, try refreshing identifier once if not already tried
            if last_error and not identifier_retry and await self._refresh_identifier():
                _LOGGER.info("Retrying list with refreshed identifier after failures")
                continue

            # All attempts failed
            if last_error:
                if _is_server_error(last_error):
                    self._note_server_error()
                else:
                    self.update_interval = RETRY_INTERVAL

                if self.data:
                    self._listing_failed = True
                    if isinstance(last_error, ApiError) and last_error.status == 400:
                        self.status_label = "delivery_not_ready"
                    else:
                        self.status_label = "listing_failed"
                    _LOGGER.warning(
                        "Failed to list datasets after %d attempts: %s. "
                        "Keeping previous data.",
                        max_retries,
                        last_error,
                    )
                    return []

                # HTTP 400 on first load: subscription not yet active
                if isinstance(last_error, ApiError) and last_error.status == 400:
                    self.status_label = "delivery_not_ready"
                    raise EudaUpdateNotReady(
                        "delivery_not_ready",
                        translation_placeholders={
                            "portal_url": BASE_URL,
                            "retry_minutes": str(
                                int(RETRY_INTERVAL.total_seconds() // 60)
                            ),
                        },
                    ) from last_error

                if _is_server_error(last_error):
                    self.status_label = "listing_failed"

                raise UpdateFailed(str(last_error)) from last_error

        return []

    async def _refresh_identifier(self) -> bool:
        """Re-fetch the data-request identifier; persist it if it changed.

        Returns True (and updates the config entry) when the portal has handed
        out a new identifier, e.g. after the subscription was recreated.
        """
        try:
            meta = await self.client.async_get_metadata(self.vin)
        except ApiError as err:
            _LOGGER.debug("Could not refresh data-request identifier: %s", err)
            return False
        new_id = meta.get("Identifier") or meta.get("identifier")
        if not new_id or new_id == self.identifier:
            return False
        _LOGGER.warning(
            "Data-request identifier changed (%s -> %s); the portal subscription "
            "was likely recreated. Updating the config entry.",
            self.identifier,
            new_id,
        )
        self.identifier = new_id
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, CONF_IDENTIFIER: new_id}
        )
        return True

    def _reschedule(self, listing: list[dict]) -> None:
        """Schedule the next poll for ~15 min after the newest known dataset.

        If that time has already passed (a new dataset is due but not yet
        present), poll every minute until it appears.
        """
        timestamps = [ts for e in listing if (ts := _created_on(e))]
        newest = max(timestamps) if timestamps else None
        if newest:
            target = newest + DATASET_INTERVAL + POST_DATASET_BUFFER
            delta = target - dt_util.utcnow()
            if delta > MIN_INTERVAL:
                self.update_interval = delta
                _LOGGER.debug("Next refresh in %s (after newest %s)", delta, newest)
                return
        # newest dataset is overdue (or unknown) -> short retry for the next drop
        self.update_interval = RETRY_INTERVAL
        _LOGGER.debug("Next dataset overdue; retrying in %s", RETRY_INTERVAL)
