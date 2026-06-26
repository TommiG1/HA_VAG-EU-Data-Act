"""Local cache of downloaded portal ZIP files for support and debugging."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# Portal filenames are VIN/timestamp based; reject anything else.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\.zip$")


@dataclass(frozen=True)
class CachedDataset:
    """Metadata for one cached ZIP on disk."""

    name: str
    size: int
    mtime: datetime


def vin_cache_key(vin: str) -> str:
    """Return a non-reversible directory name for a VIN (no VIN in paths)."""
    return hashlib.sha256(vin.encode("utf-8")).hexdigest()[:16]


class DatasetCache:
    """Store the last N portal ZIPs per vehicle under the HA config directory."""

    def __init__(
        self,
        base_dir: Path,
        *,
        max_files: int = 10,
        max_bytes_per_vin: int = 50_000_000,
    ) -> None:
        self.base_dir = base_dir
        self.max_files = max_files
        self.max_bytes_per_vin = max_bytes_per_vin

    def _vin_dir(self, vin: str) -> Path:
        return self.base_dir / vin_cache_key(vin)

    def store(self, vin: str, name: str, data: bytes) -> None:
        """Write a ZIP and rotate older files for this vehicle."""
        if not _SAFE_NAME.match(name):
            _LOGGER.warning("Refusing to cache dataset with unsafe name: %s", name)
            return
        target_dir = self._vin_dir(vin)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / name
        path.write_bytes(data)
        _LOGGER.debug("Cached dataset %s (%d bytes)", name, len(data))
        self._rotate(target_dir)

    def list_entries(self, vin: str) -> list[CachedDataset]:
        """Return cached ZIPs for a vehicle, newest first."""
        target_dir = self._vin_dir(vin)
        if not target_dir.is_dir():
            return []
        entries: list[CachedDataset] = []
        for path in target_dir.glob("*.zip"):
            if not path.is_file():
                continue
            stat = path.stat()
            entries.append(
                CachedDataset(
                    name=path.name,
                    size=stat.st_size,
                    mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
            )
        entries.sort(key=lambda item: item.mtime, reverse=True)
        return entries

    def read_latest(self, vin: str) -> tuple[str, bytes] | None:
        """Return the newest cached ZIP (name, raw bytes), or None."""
        entries = self.list_entries(vin)
        if not entries:
            return None
        path = self._vin_dir(vin) / entries[0].name
        if not path.is_file():
            return None
        return entries[0].name, path.read_bytes()

    def read(self, vin: str, name: str) -> bytes | None:
        """Return the raw bytes of one cached ZIP, or None if missing."""
        path = self._vin_dir(vin) / name
        if not path.is_file():
            return None
        return path.read_bytes()

    def delete(self, vin: str, name: str) -> None:
        """Remove a cached ZIP (e.g. when it turned out to be unreadable)."""
        (self._vin_dir(vin) / name).unlink(missing_ok=True)

    def _rotate(self, target_dir: Path) -> None:
        """Drop oldest ZIPs when count or total size exceeds limits."""
        files = sorted(
            (p for p in target_dir.glob("*.zip") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
        )
        while len(files) > self.max_files:
            oldest = files.pop(0)
            oldest.unlink(missing_ok=True)
            _LOGGER.debug("Cache rotation removed %s", oldest.name)

        files = sorted(
            (p for p in target_dir.glob("*.zip") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
        )
        total = sum(p.stat().st_size for p in files)
        while files and total > self.max_bytes_per_vin:
            oldest = files.pop(0)
            total -= oldest.stat().st_size
            oldest.unlink(missing_ok=True)
            _LOGGER.debug("Cache size rotation removed %s", oldest.name)
