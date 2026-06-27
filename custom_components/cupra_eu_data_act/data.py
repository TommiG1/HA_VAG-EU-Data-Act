"""Pure-Python data layer: dataset parsing, value typing, curated registry.

This module intentionally has **no Home Assistant imports** so the parsing and
mapping logic can be unit-tested offline. Platform modules translate the plain
string device-class / unit values here into HA enums.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

# ---------------------------------------------------------------------------
# Data dictionary (generated from the portal PDF by tools/parse_dictionary.py;
# provenance: data_dictionary_meta.json — currently V5.0 / doc 1.0.5)
# ---------------------------------------------------------------------------

_DICT_PATH = Path(__file__).parent / "data_dictionary.json"


@lru_cache(maxsize=1)
def load_dictionary() -> dict[str, dict[str, str]]:
    """Return { key-uuid: {name, description, unit, type, cluster} }."""
    try:
        return json.loads(_DICT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Dataset format detection
# ---------------------------------------------------------------------------


def detect_dataset_format(points: dict[str, "DataPoint"]) -> str:
    """Detect whether dataset uses dotted (ID.x) or flat (eGolf) naming.

    Returns "dotted" if any field name contains a dot, otherwise "flat".
    ID.x/MEB cars use dotted names (battery_state_report.soc, mileage.value),
    while pre-ID.x cars use flat names (state_of_charge, mileage).
    """
    return "dotted" if any("." in dp.field_name for dp in points.values()) else "flat"


# ---------------------------------------------------------------------------
# Value typing
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*s$", re.I)
_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


def parse_duration_seconds(raw: str) -> float | None:
    """Parse values like "0s" / "1800s" into seconds."""
    m = _DURATION_RE.match(raw.strip())
    return float(m.group(1)) if m else None


def sticky(previous, current):
    """Keep the last known value when an update omits a field.

    The portal's snapshots don't include every field every cycle; a missing
    field means "no fresh reading", not "unavailable", so we fall back to the
    previous value instead of reporting unknown.
    """
    return current if current is not None else previous


def parse_value(raw: str | None, type_hint: str | None = None):
    """Coerce a raw string value into a typed Python value.

    ``type_hint`` comes from the data dictionary ("int", "float", "boolean",
    "enum", "string"). Falls back to structural detection so it works even
    without a dictionary entry.
    """
    if raw is None:
        return None
    s = raw.strip()
    if s == "":
        return None

    hint = (type_hint or "").lower()

    if hint == "boolean" or s.lower() in ("true", "false"):
        return s.lower() == "true"

    if hint in ("int", "integer") and _INT_RE.match(s):
        return int(s)
    if hint == "float":
        try:
            return float(s)
        except ValueError:
            return s

    # duration shorthand ("0s")
    dur = parse_duration_seconds(s)
    if dur is not None:
        return dur

    # structural fallbacks
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s):
        return float(s)

    return s  # enums, ISO timestamps, free text stay as strings


# ---------------------------------------------------------------------------
# Enum + naming helpers
# ---------------------------------------------------------------------------

_ENUM_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Bare field names that are meaningless on their own; for these we name the
# entity from the dictionary description instead.
_GENERIC_FIELD_NAMES = {"value", "state", "unit", "is_set", "type", "id"}

# Portal field-name aliases: same semantic field, different name on some models
# (e.g. Cupra Terramar PHEV flat format — issue #18).
_FIELD_ALIASES: dict[str, str] = {
    "remaining_climatisation_time": "remaining_climate_time",
    "charging_plug1_connectionstate": "plug_state",
}


def normalize_field_name(field_name: str, description: str | None) -> str:
    """Give generic portal field names a stable, matchable identity.

    Several dictionary entries use ``name: value`` with a descriptive sentence.
    Without this, curated sensors cannot target them and entity names would
    collide across unrelated ``value`` fields.
    """
    if field_name.lower() not in _GENERIC_FIELD_NAMES or not description:
        return _FIELD_ALIASES.get(field_name, field_name)
    desc = description.strip().lower()
    if "primary range" in desc:
        return "value_of_the_primary_range"
    return _FIELD_ALIASES.get(field_name, field_name)


def enum_members(description: str | None) -> list[str]:
    """Parse an ordered enum member list out of a dictionary description.

    Enum fields document their members as a comma-separated, index-ordered list
    (e.g. "IMMEDIATE_ACTION_STATE_INVALID, ..."). PDF extraction injects stray
    spaces inside the tokens, so whitespace is stripped before checking each
    token looks like an UPPER_SNAKE enum label. Returns [] for prose / non-enum
    descriptions.
    """
    if not description:
        return []
    members = [re.sub(r"\s+", "", part) for part in description.split(",")]
    members = [m for m in members if _ENUM_TOKEN_RE.match(m)]
    return members if len(members) >= 2 else []


def shorten_enum_label(field_name: str, value):
    """Shorten verbose VW enum labels for display.

    Removes repeated enum prefixes that are already implied by the field name,
    e.g. ``charging_state_report.current_charge_state`` +
    ``CHARGE_STATE_CHARGING_HV_BATTERY`` -> ``CHARGING_HV_BATTERY``.
    Only ALLCAPS strings are touched; anything else passes through unchanged.
    """
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9_]+", value):
        return value

    def normalize(text: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").upper()

    candidates: list[str] = []

    def add_candidate(text: str) -> None:
        normalized = normalize(text)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    field_name = field_name or ""
    add_candidate(field_name)
    for part in field_name.split("."):
        add_candidate(part)

    normalized_field = normalize(field_name)
    for removable in ("SETTINGS_", "STATUS_", "CHARGING_STATE_REPORT_"):
        if normalized_field.startswith(removable):
            add_candidate(normalized_field.removeprefix(removable))

    for candidate in list(candidates):
        tokens = candidate.split("_")
        for i in range(1, len(tokens)):
            add_candidate("_".join(tokens[i:]))

    for prefix in sorted(candidates, key=len, reverse=True):
        full_prefix = f"{prefix}_"
        if value.startswith(full_prefix) and len(value) > len(full_prefix):
            return value[len(full_prefix) :]

    return value


def friendly_name(field_name: str, description: str | None = None) -> str:
    """Entity name for a raw data point.

    Dotted field names are descriptive enough as-is, but some are bare and
    meaningless ("value", "state", ...). For those, fall back to the dictionary
    description (first sentence, trimmed).
    """
    if field_name.lower() in _GENERIC_FIELD_NAMES and description:
        text = description.strip().split(".")[0].strip()
        if text:
            return text[:60]
    return field_name


# ---------------------------------------------------------------------------
# Dataset model
# ---------------------------------------------------------------------------


@dataclass
class DataPoint:
    key: str
    field_name: str
    raw_value: str
    type_hint: str | None = None
    unit: str | None = None
    description: str | None = None
    cluster: str | None = None
    timestamp_utc: str | None = None
    sequence: int = 0
    # Capture moment of the dataset this point came from (its newest
    # car_captured_time), stamped on every point by ``Dataset.from_json``.
    # Value fields like soc/mileage carry no per-item ``timestampUtc``, so this
    # dataset-level stamp is their only freshness signal for cross-dataset
    # selection in ``find_by_field`` and ``merge_data_points``.
    captured_at: datetime | None = None
    # Portal ZIP filename that last supplied this point (upstream #31).
    source_dataset: str | None = None

    @property
    def value(self):
        v = parse_value(self.raw_value, self.type_hint)
        # Enum fields occasionally deliver the raw protobuf integer index instead
        # of the label; resolve it back to the string using the documented members.
        if self.type_hint == "enum" and isinstance(v, int) and not isinstance(v, bool):
            members = enum_members(self.description)
            if 0 <= v < len(members):
                return members[v]
        return v

    @property
    def timestamp(self) -> datetime | None:
        """Parse the timestampUtc field into a datetime object."""
        return _parse_timestamp(self.timestamp_utc) if self.timestamp_utc else None


@dataclass
class Dataset:
    """A parsed dataset JSON, enriched from the data dictionary."""

    vin: str
    user_id: str | None
    points: dict[str, DataPoint] = field(default_factory=dict)  # by key
    captured_at: datetime | None = None

    @classmethod
    def from_json(cls, payload: dict) -> "Dataset":
        dictionary = load_dictionary()
        points: dict[str, DataPoint] = {}
        captured: list[datetime] = []
        for sequence, item in enumerate(payload.get("Data", [])):
            key = item.get("key")
            if not key:
                continue
            meta = dictionary.get(key, {})
            field_name = item.get("dataFieldName") or meta.get("name") or key
            field_name = normalize_field_name(
                field_name, meta.get("description") or None
            )
            dp = DataPoint(
                key=key,
                field_name=field_name,
                raw_value=item.get("value", ""),
                sequence=sequence,
                type_hint=meta.get("type") or None,
                unit=meta.get("unit") or None,
                description=meta.get("description") or None,
                cluster=meta.get("cluster") or None,
                timestamp_utc=item.get("timestampUtc") or None,
            )
            points[key] = dp
            if field_name.rsplit(".", 1)[-1] in _CAPTURED_TIME_SUFFIXES:
                if ts := _parse_timestamp(dp.raw_value):
                    captured.append(ts)
        dataset_captured = max(captured) if captured else None
        # Stamp the dataset's capture moment onto every point so freshness-based
        # selection works for value fields (soc, mileage, …) that carry no
        # per-item timestampUtc of their own.
        if dataset_captured is not None:
            for dp in points.values():
                dp.captured_at = dataset_captured
        return cls(
            vin=payload.get("vin", ""),
            user_id=payload.get("user_id"),
            points=points,
            captured_at=dataset_captured,
        )

    def by_field(self, field_name: str) -> DataPoint | None:
        """Convenience wrapper for :func:`find_by_field` on this dataset."""
        return find_by_field(self.points, field_name)


_MIN_DT = datetime.min.replace(tzinfo=timezone.utc)


def _datapoint_freshness(dp: DataPoint) -> datetime | None:
    """Best-known time a single data point describes, or None if unknown.

    Uses the point's own ``timestampUtc`` when present; for captured-time
    fields the value itself *is* the timestamp. Value fields (soc, mileage, …)
    carry neither, so fall back to the dataset's car_captured_time stamped onto
    every point in ``Dataset.from_json`` — without it the freshness guard in
    ``merge_data_points`` and the ranking in ``find_by_field`` are no-ops for
    exactly the fields users see regress/oscillate.
    """
    if dp.timestamp:
        return dp.timestamp
    if dp.field_name.rsplit(".", 1)[-1] in _CAPTURED_TIME_SUFFIXES:
        return parse_timestamp(dp.raw_value)
    return dp.captured_at


def datapoint_freshness_source(dp: DataPoint) -> str:
    """Explain which signal backs :func:`_datapoint_freshness` for a point."""
    if dp.timestamp:
        return "timestamp_utc"
    if dp.field_name.rsplit(".", 1)[-1] in _CAPTURED_TIME_SUFFIXES:
        if parse_timestamp(dp.raw_value):
            return "field_captured_time"
    if dp.captured_at is not None:
        return "report_captured_time"
    return "unknown"


def datapoint_freshness_attributes(
    dp: DataPoint | None,
    *,
    now: datetime | None = None,
) -> dict[str, str | int]:
    """Entity attributes exposing when a reading was captured and how old it is."""
    if dp is None:
        return {}
    attrs: dict[str, str | int] = {}
    if dp.source_dataset:
        attrs["source_dataset"] = dp.source_dataset
    captured = _datapoint_freshness(dp)
    if captured is None:
        return attrs
    if now is None:
        now = datetime.now(timezone.utc)
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_minutes = max(0, int((now - captured).total_seconds() // 60))
    attrs.update(
        {
            "data_captured_at": captured.isoformat(),
            "age_minutes": age_minutes,
            "freshness_source": datapoint_freshness_source(dp),
        }
    )
    return attrs


def stamp_source_dataset(
    points: dict[str, DataPoint], dataset_name: str | None
) -> dict[str, DataPoint]:
    """Tag every point with the portal ZIP it came from."""
    if not dataset_name:
        return points
    for dp in points.values():
        dp.source_dataset = dataset_name
    return points


def _as_float(raw) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def find_by_field(
    points: dict[str, DataPoint], field_name: str, *, prefer_max_value: bool = False
) -> DataPoint | None:
    """Return a single data point for a (possibly duplicated) field name.

    The portal merges several report snapshots into one flat array with no
    ordering guarantee, so a field like
    ``charging_state_report.current_charge_state`` can appear several times
    under different UUIDs with conflicting values. We prefer usable readings,
    then the **freshest** one (by its own ``timestampUtc`` / captured time).
    When no timestamps distinguish the candidates we use the last occurrence in
    the ZIP. The portal often bundles minute-level snapshots in array order, so
    the last duplicate is the best proxy for the freshest value.

    ``prefer_max_value`` is for monotonic fields (the odometer): one dataset can
    carry several ``mileage.value`` slots from report snapshots that lag each
    other (e.g. 70876 vs 70908 at the same capture time), so the **highest**
    reading is the truest current value. With it set the largest numeric value
    wins outright; freshness then ZIP position only break exact-value ties.
    """
    matches = [dp for dp in points.values() if dp.field_name == field_name]
    if not matches:
        return None
    usable = [
        dp for dp in matches if is_usable_reading(dp.value, dp.field_name)
    ]
    candidates = usable or matches

    def rank(dp: DataPoint) -> tuple[bool, datetime]:
        fresh = _datapoint_freshness(dp)
        return (fresh is not None, fresh or _MIN_DT)

    if prefer_max_value:
        def value_rank(dp: DataPoint):
            num = _as_float(dp.raw_value)
            # numeric beats non-numeric, then highest value, then freshest,
            # then last occurrence in the ZIP
            return (num is not None, num if num is not None else 0.0, *rank(dp), dp.sequence)

        return max(candidates, key=value_rank)

    top = rank(max(candidates, key=rank))
    tied = [dp for dp in candidates if rank(dp) == top]
    return max(tied, key=lambda dp: dp.sequence)


# Field suffixes that carry when the vehicle last reported to the backend.
_CAPTURED_TIME_SUFFIXES = frozenset(
    {"car_captured_time", "car_captured_utc_timestamp"}
)

# Portal metadata fields we intentionally omit from raw diagnostic sensors.
# Exact names only (e.g. bare ``timestamp``) — avoids matching curated
# ``mileage.value.timestamp``.
RAW_METADATA_EXACT = frozenset(
    {
        "message_id",
        "report_type",
        "timestamp",
    }
)
RAW_METADATA_SUFFIXES = frozenset(
    {
        "car_captured_utc_timestamp",
        "car_captured_time",
    }
)


def is_superseded_instrument_cluster_field(
    field_name: str, present_field_names: set[str] | frozenset[str]
) -> bool:
    """True when bare instrument_cluster_time duplicates the dotted Cupra field."""
    return (
        field_name == "instrument_cluster_time"
        and "profile_state_report.instrument_cluster_time" in present_field_names
    )


def is_raw_metadata_field(field_name: str) -> bool:
    """True when a field is portal metadata, not a user-facing reading."""
    if field_name in RAW_METADATA_EXACT:
        return True
    for suffix in RAW_METADATA_SUFFIXES:
        if field_name == suffix or field_name.endswith(f".{suffix}"):
            return True
    return False


def latest_captured_time(points: dict[str, "DataPoint"]) -> datetime | None:
    """Newest car-to-backend timestamp across all report snapshots in a dataset.

    The portal merges several report snapshots into one payload, each with its
    own captured time. The maximum is when the vehicle itself was last heard
    from — distinct from when the portal generated the ZIP file.
    """
    times = [
        ts
        for dp in points.values()
        if dp.field_name.rsplit(".", 1)[-1] in _CAPTURED_TIME_SUFFIXES
        and (ts := parse_timestamp(dp.raw_value))
    ]
    return max(times) if times else None


_LAST_CONNECTED_BASE_FIELDS = ("mileage.value", "mileage")


def last_connected_time(points: dict[str, DataPoint]) -> datetime | None:
    """When the vehicle last reported mileage / odometer to the backend.

  Many Cupra/MEB datasets omit ``timestampUtc`` on the mileage data point even
  though mileage itself is present. Fall back to the newest car-captured
  timestamp in the payload so "Last connected" stays useful.
    """
    for field in _LAST_CONNECTED_BASE_FIELDS:
        dp = find_by_field(points, field)
        if dp and dp.timestamp:
            return dp.timestamp
    return latest_captured_time(points)


def parse_timestamp(raw) -> datetime | None:
    """Parse ISO / epoch-millis timestamp strings from portal value fields."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    # epoch millis
    if _INT_RE.match(s) and len(s) >= 12:
        try:
            return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
        except (ValueError, OSError):
            return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


_parse_timestamp = parse_timestamp  # internal alias


# ---------------------------------------------------------------------------
# Curated entity registry  (plain strings -> translated to HA enums in platforms)
# ---------------------------------------------------------------------------


# Distance unit enums (e.g. mileage.unit) -> HA unit. The portal reports
# mileage/range in either miles or kilometres depending on the vehicle, so the
# unit must not be hardcoded; it is read from a companion "*.unit" field.
DISTANCE_UNIT_BY_ENUM: dict[str, str] = {
    "MILES": "mi",
    "MILE": "mi",
    "KM": "km",
    "KILOMETER": "km",
    "KILOMETERS": "km",
    "KILOMETRE": "km",
    "KILOMETRES": "km",
}


def resolve_distance_unit(enum_value, default: str | None = None) -> str | None:
    """Map a distance-unit enum value (e.g. "MILES") to an HA unit ("mi")."""
    if isinstance(enum_value, str):
        return DISTANCE_UNIT_BY_ENUM.get(enum_value.strip().upper(), default)
    return default


# Companion fields tried in order when a range value has no dedicated *.unit
# (e.g. ``value_of_the_primary_range`` normalized from a generic portal ``value``).
PRIMARY_RANGE_UNIT_FIELDS: tuple[str, ...] = ("range.unit", "mileage.unit")


def resolve_distance_unit_from_companion_fields(
    points: dict[str, DataPoint],
    *field_names: str,
) -> str | None:
    """Resolve HA distance unit from the first available companion *.unit field."""
    for field_name in field_names:
        dp = find_by_field(points, field_name)
        if dp is not None:
            resolved = resolve_distance_unit(dp.value)
            if resolved:
                return resolved
    for dp in points.values():
        fn = dp.field_name
        if "cruising_ranges" in fn and fn.endswith(".unit"):
            resolved = resolve_distance_unit(dp.value)
            if resolved:
                return resolved
    return None


def resolve_primary_range_unit(points: dict[str, DataPoint]) -> str | None:
    """Distance unit for ``value_of_the_primary_range`` (no own *.unit field)."""
    return resolve_distance_unit_from_companion_fields(
        points, *PRIMARY_RANGE_UNIT_FIELDS
    )


# Charge-rate unit enums (battery_state_report.charge_rate_unit) -> HA unit.
# The charge rate is expressed as range gained over time and the unit (km vs
# miles, per hour vs per minute) varies by vehicle/region, so it is read from
# the companion charge_rate_unit field rather than hardcoded.
CHARGE_RATE_UNIT_BY_ENUM: dict[str, str] = {
    "CHARGE_RATE_UNIT_KM_PER_H": "km/h",
    "CHARGE_RATE_UNIT_KM_PER_MIN": "km/min",
    "CHARGE_RATE_UNIT_MILES_PER_H": "mi/h",
    "CHARGE_RATE_UNIT_MILES_PER_MIN": "mi/min",
    # Flat PHEV (Passat/Golf) charge_rate_unit strings
    "KM_PER_H": "km/h",
    "KM_PER_MIN": "km/min",
    "MILES_PER_H": "mi/h",
    "MILES_PER_MIN": "mi/min",
}


def resolve_charge_rate_unit(enum_value, default: str | None = None) -> str | None:
    """Map a charge-rate-unit enum (e.g. "CHARGE_RATE_UNIT_KM_PER_H") to "km/h"."""
    if isinstance(enum_value, str):
        return CHARGE_RATE_UNIT_BY_ENUM.get(enum_value.strip().upper(), default)
    return default


def decikelvin_to_celsius(raw: str) -> float | None:
    """Convert deci-Kelvin (e.g., "2921") to Celsius.

    Outside temperature is reported in deci-Kelvin (dK):
    - 2921 dK = 292.1 K = 19.06°C
    """
    try:
        dk = float(raw)
        kelvin = dk / 10
        celsius = kelvin - 273.15
        return round(celsius, 1)
    except (ValueError, TypeError):
        return None


def abs_value(value) -> int | float | None:
    """Return absolute value, handling negative maintenance intervals.

    Maintenance intervals can be negative (overdue). Take absolute value
    for display, as the sign indicates past-due status.
    """
    try:
        abs_val = abs(float(value))
        return int(abs_val) if abs_val == int(abs_val) else abs_val
    except (ValueError, TypeError):
        return None


def fuel_consumption_l_per_1000km_to_l_per_100km(value) -> float | None:
    """Convert fuel consumption from L/1000km to L/100km.

    The API reports fuel consumption in L/1000km (e.g., 168 L/1000km).
    Convert to standard L/100km by dividing by 10 (e.g., 16.8 L/100km).
    """
    try:
        return round(float(value) / 10, 1)
    except (ValueError, TypeError):
        return None


def deci_kwh_to_kwh(value) -> float | None:
    """Convert deci-kWh (0.1 kWh) portal values to kWh.

    ID.x energy_contents.*.physical_value fields use 0.1 kWh resolution
    (e.g., 496 -> 49.6 kWh).
    """
    try:
        return round(float(value) / 10, 1)
    except (ValueError, TypeError):
        return None


def total_charged_energy_kwh(points: dict[str, "DataPoint"]) -> float | None:
    """Return a cumulative charged-energy total in kWh from the dataset.

    Dotted datasets expose ``battery_state_report.charge_energy`` directly in
    kWh, while flat datasets expose ``charged_energy`` in deci-kWh.
    """
    dotted = find_by_field(points, "battery_state_report.charge_energy")
    if dotted is not None and not is_sentinel(dotted.value, dotted.field_name):
        try:
            return float(dotted.value)
        except (TypeError, ValueError):
            pass

    flat = find_by_field(points, "charged_energy")
    if flat is not None and not is_sentinel(flat.value, flat.field_name):
        return deci_kwh_to_kwh(flat.value)

    return None


def hectometers_to_km(value) -> float | None:
    """Convert portal distances in 100 m (hectometers) to km."""
    try:
        return round(float(value) / 10, 1)
    except (ValueError, TypeError):
        return None


def electr_consumption_kwh_per_1000km_to_kwh_per_100km(value) -> float | None:
    """Convert electric consumption from kWh/1000km to kWh/100km.

    The dictionary types `long_term_data_average_electr_engine_consumption`
    and friends as int with unit "kwH/1000km"; divide by 10 (mirrors the
    fuel-consumption transform).
    """
    try:
        return round(float(value) / 10, 1)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Sentinel values
# ---------------------------------------------------------------------------
#
# The portal occasionally reports "no reading" using out-of-band integer
# sentinels rather than omitting the field. These pollute long-term history
# (e.g. mileage spike to 4 294 967 295 km, charging-time stuck at 65 535 min)
# and must be filtered before the value reaches the sticky/HA layer.
#
# Numeric values are matched generously: int sentinels are also compared as
# floats so float-typed fields with the same magnitude are caught.

# Global integer sentinels: max-unsigned and max-signed for common widths.
_GLOBAL_NUMERIC_SENTINELS: frozenset[float] = frozenset(
    {
        2**16 - 1,   # 65535  (uint16 max)
        2**31 - 1,   # 2147483647 (int32 max)
        2**32 - 1,   # 4294967295 (uint32 max)
    }
)

# Field-specific extra sentinels: -1 ("not available") is too common as a
# legitimate value (e.g. negative maintenance interval = overdue) to filter
# globally, so it is only applied to fields where -1 cannot be valid.
_FIELD_SENTINELS: dict[str, frozenset[float]] = {
    "remaining_charging_time": frozenset({-1}),
    "battery_state_report.remaining_charging_time_complete": frozenset({-1}),
    "battery_state_report.remaining_charging_time_bulk": frozenset({-1}),
    "remaining_charging_time_target_soc": frozenset({-1}),
}

# VW tyre-pressure fields encode validity, not pressure: 0 = unsupported,
# 1 = invalid, otherwise the reading is a pressure value (issue #14). This
# applies to every tyre-pressure family (actual / required / differential),
# not just the actual reading. A "required" or "differential" of 0/1 bar is
# the same unsupported/invalid sentinel, never a real pressure.
_TYRE_PRESSURE_STATUS_CODES: frozenset[float] = frozenset({0, 1})


def is_sentinel(value, field_name: str | None = None) -> bool:
    """Return True if ``value`` is a portal sentinel for "no reading".

    Booleans are never sentinels (``True``/``False`` are valid). Strings and
    ``None`` are passed through unchanged.
    """
    if value is None or isinstance(value, bool):
        return False
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return False
    if as_float in _GLOBAL_NUMERIC_SENTINELS:
        return True
    if field_name and as_float in _FIELD_SENTINELS.get(field_name, frozenset()):
        return True
    if (
        field_name
        and field_name.startswith("tyre_pressure_")
        and as_float in _TYRE_PRESSURE_STATUS_CODES
    ):
        return True
    return False


def is_usable_reading(value, field_name: str | None = None) -> bool:
    """True when a parsed portal value is a real reading worth retaining."""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return not is_sentinel(value, field_name)


def merge_data_points(
    existing: dict[str, DataPoint],
    new: dict[str, DataPoint],
) -> dict[str, DataPoint]:
    """Merge a new portal snapshot into previous data, keeping last good readings.

    Rules per dataset key:
    - A sentinel/missing new value never overwrites an existing one (the
      previous good reading is kept; entity-level sticky covers display).
    - A usable new value replaces a previous sentinel/unusable one.
    - When both are usable but carry timestamps, an *older* new value (e.g. from
      a fallback to a previous dataset after a download failure) does not
      regress the state — the fresher reading wins (issue #24).
    """
    merged = dict(existing)
    for key, dp in new.items():
        old = merged.get(key)
        if old is None:
            merged[key] = dp
            continue
        if not is_usable_reading(dp.value, dp.field_name):
            continue
        if not is_usable_reading(old.value, old.field_name):
            merged[key] = dp
            continue
        old_fresh = _datapoint_freshness(old)
        new_fresh = _datapoint_freshness(dp)
        if old_fresh is not None and new_fresh is not None and new_fresh < old_fresh:
            continue
        merged[key] = dp
    return merged


# Named unit resolvers selectable per curated sensor via ``unit_resolver``.
UNIT_RESOLVERS = {
    "distance": resolve_distance_unit,
    "charge_rate": resolve_charge_rate_unit,
}


@dataclass(frozen=True)
class CuratedSensor:
    field_name: str
    name: str
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    icon: str | None = None
    # transform: "duration_min" converts portal seconds into minutes; None keeps parse_value
    transform: str | None = None
    # companion field holding the unit enum (e.g. "mileage.unit"); when set, the
    # sensor's unit is resolved from it at runtime, falling back to ``unit``.
    unit_field: str | None = None
    # fallback chain when the value field has no dedicated *.unit (tried in order).
    unit_fields: tuple[str, ...] = ()
    # which named resolver in UNIT_RESOLVERS to apply to ``unit_field``'s value.
    unit_resolver: str = "distance"
    # number of decimal places to show (None = auto)
    suggested_display_precision: int | None = None
    # HA entity translation key (name + enum state labels in translations/*.json)
    translation_key: str | None = None
    # monotonic non-decreasing fields (the odometer): pick the highest of the
    # duplicate value slots via find_by_field(prefer_max_value=...), so a lagging
    # report snapshot in the same dataset can't make mileage read low.
    monotonic: bool = False
    # fields to sum as a fallback when this sensor's own field carries no usable
    # reading. Some vehicles report a curated total (e.g. combined cruising
    # range) as an empty slot while still sending its per-engine components, so
    # the sum of these fields reconstructs the total. The portal value, when
    # present, always wins over the computed sum.
    sum_fallback_fields: tuple[str, ...] = ()
    # create the entity disabled in the registry (the user can enable it)
    enabled_by_default: bool = True


def curated_translation_key(field_name: str, translation_key: str | None = None) -> str:
    """Stable HA translation key for a curated sensor field."""
    if translation_key:
        return translation_key
    return field_name.replace(".", "_")


def maintenance_due_datetime(days_value, now):
    """Service due date from a signed "days until service" countdown.

    The portal encodes maintenance intervals as a countdown that rises toward 0:
    a negative value is the number of days remaining (e.g. -127 = due in 127
    days), zero is the due date, and a positive value is days overdue. Turning it
    into a timestamp removes the sign ambiguity (HA shows "in 4 months" vs "5
    days ago") that abs() used to hide.

    ``now`` is a timezone-aware datetime (HA local time); the result is anchored
    to local midnight so it stays stable between daily portal updates. Returns
    ``None`` for non-numeric input.
    """
    try:
        days = int(days_value)
    except (TypeError, ValueError):
        return None
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=days)


@dataclass(frozen=True)
class CuratedBinary:
    field_name: str
    name: str
    device_class: str | None = None
    invert: bool = False  # is_on = (value is False) when True
    icon: str | None = None
    # How the field's integer value maps to on/off (see decode_binary_state).
    # Default "open" matches the dominant 2/3 encoding for doors/windows/locks.
    encoding: str = "open"


def decode_binary_state(
    value, encoding: str = "open", invert: bool = False
) -> bool | None:
    """Decode a curated binary field's raw value into on / off / unknown.

    Vehicle status fields encode their boolean in several ways, selected per
    sensor via ``CuratedBinary.encoding`` rather than guessed from the field
    name at runtime:

      "open"   - 0/1 = unsupported/invalid (-> unknown); 2 = active (open /
                 locked / safe / …), 3 = inactive. The dominant encoding for
                 doors, windows, sunroofs and lock/safe states.
      "onoff"  - 0 = off, 1 = on (e.g. parking_brake).
      "lights" - 0/1 = unsupported/invalid; 2 = off; 3/4/5 = on (parking_lights).
      "string_onoff" - ``"on"`` / ``"off"`` (case-insensitive; PHEV flat fields).
      "plug"   - ``"connected"`` / ``"disconnected"`` (``plug_state``).
      "string_lock" - ``"locked"`` / ``"unlocked"`` (``lock_state``).

    Plain booleans are returned as-is regardless of ``encoding``. ``invert``
    flips a decoded True/False (a "lock" sensor reads on when *un*locked); it
    never turns a known state into unknown. Returns ``None`` when the value is
    missing or carries an unsupported/invalid sentinel.
    """
    if isinstance(value, bool):
        result: bool | None = value
    elif isinstance(value, str):
        text = value.strip().lower()
        if encoding == "string_onoff":
            if text == "on":
                result = True
            elif text == "off":
                result = False
            else:
                result = None
        elif encoding == "plug":
            if text == "connected":
                result = True
            elif text == "disconnected":
                result = False
            else:
                result = None
        elif encoding == "string_lock":
            if text == "locked":
                result = True
            elif text == "unlocked":
                result = False
            else:
                result = None
        else:
            result = None
    elif isinstance(value, int):
        if encoding == "onoff":
            result = value == 1
        elif encoding == "lights":
            result = None if value in (0, 1) else value in (3, 4, 5)
        elif value in (0, 1):
            result = None  # unsupported / invalid sentinel
        else:  # "open": 2 = active, 3 = inactive
            result = value == 2
    else:
        result = None
    if result is None:
        return None
    return (not result) if invert else result


# ---------------------------------------------------------------------------
# Curated sensors for ID.x/MEB vehicles (dotted field names)
# ---------------------------------------------------------------------------

CURATED_SENSORS_DOTTED: tuple[CuratedSensor, ...] = (
    # === Charging & Battery ===
    CuratedSensor("battery_state_report.soc", "Battery", "battery", "%", "measurement"),
    CuratedSensor(
        "settings.target_soc",
        "Target charge level",
        None,
        "%",
        "measurement",
        icon="mdi:battery-charging-80",
    ),
    CuratedSensor(
        "battery_state_report.charge_bulk_threshold",
        "Charge bulk threshold",
        None,
        "%",
        "measurement",
        icon="mdi:battery-charging-100",
    ),
    CuratedSensor(
        "battery_state_report.charge_power",
        "Charge power",
        "power",
        "kW",
        "measurement",
    ),
    CuratedSensor(
        "battery_state_report.charge_rate",
        "Charge rate",
        None,
        "km/h",
        "measurement",
        icon="mdi:speedometer",
        unit_field="battery_state_report.charge_rate_unit",
        unit_resolver="charge_rate",
    ),
    CuratedSensor(
        "battery_state_report.charge_energy",
        "Charged energy",
        "energy",
        "kWh",
        "total_increasing",
        icon="mdi:lightning-bolt-circle",
    ),
    CuratedSensor(
        "last_charge_kwh",
        "Last charge",
        None,
        "kWh",
        "measurement",
        icon="mdi:battery-charging-wireless",
        translation_key="last_charge_kwh",
    ),
    CuratedSensor(
        "battery_state_report.remaining_charging_time_complete",
        "Remaining charging time",
        "duration",
        "min",
        "measurement",
        transform="duration_min",
        icon="mdi:battery-clock",
    ),
    CuratedSensor(
        "battery_state_report.remaining_charging_time_bulk",
        "Remaining time to bulk",
        "duration",
        "min",
        "measurement",
        transform="duration_min",
        icon="mdi:battery-clock",
    ),
    CuratedSensor(
        "energy_contents.current_energy_content.physical_value",
        "Battery energy",
        None,
        "kWh",
        "measurement",
        transform="deci_kwh",
        icon="mdi:battery-high",
    ),
    CuratedSensor(
        "energy_contents.maximal_energy_content.physical_value",
        "Battery capacity",
        None,
        "kWh",
        "measurement",
        transform="deci_kwh",
        icon="mdi:battery-sync",
    ),
    CuratedSensor(
        "battery_care_mode.charge_bcam_threshold",
        "BCAM charge threshold",
        None,
        "%",
        "measurement",
        icon="mdi:battery-heart",
    ),
    CuratedSensor(
        "charging_state_report.error_code",
        "Charging error code",
        None,
        None,
        None,
        icon="mdi:alert-circle",
    ),
    # === Distance & Range ===
    CuratedSensor(
        "mileage.value",
        "Mileage",
        "distance",
        "km",
        "total_increasing",
        icon="mdi:counter",
        unit_field="mileage.unit",
        unit_resolver="distance",
        suggested_display_precision=0,
        monotonic=True,
    ),
    CuratedSensor(
        "range.value",
        "Electric range",
        "distance",
        "km",
        "measurement",
        icon="mdi:map-marker-distance",
        unit_field="range.unit",
        unit_resolver="distance",
        suggested_display_precision=0,
    ),
    # Cupra/MEB portal sometimes exposes range as a flat dataFieldName instead of
    # range.value; the dictionary entry has no unit — inherit from range/mileage.
    CuratedSensor(
        "value_of_the_primary_range",
        "Electric range",
        "distance",
        "km",
        "measurement",
        icon="mdi:map-marker-distance",
        unit_fields=PRIMARY_RANGE_UNIT_FIELDS,
        suggested_display_precision=0,
    ),
    # === Climate ===
    CuratedSensor(
        "remaining_climate_time",
        "Remaining climate time",
        "duration",
        "s",
        "measurement",
        transform="duration_s",
    ),
    CuratedSensor(
        "residual_energy_in_percent",
        "Residual energy",
        None,
        "%",
        "measurement",
        icon="mdi:battery",
    ),
    CuratedSensor(
        "additional_consumptions.residual_consumption",
        "Residual consumption",
        None,
        "kWh/100km",
        "measurement",
        icon="mdi:flash",
        suggested_display_precision=1,
    ),
    CuratedSensor(
        "additional_consumptions.interior_climatization_consumption",
        "Climate consumption",
        None,
        "kWh/100km",
        "measurement",
        icon="mdi:air-conditioner",
        suggested_display_precision=1,
    ),
    CuratedSensor(
        "slope_consumption_values.ascent_slope_consumption.physical_value",
        "Uphill consumption",
        None,
        "kWh/100km",
        "measurement",
        icon="mdi:terrain",
        suggested_display_precision=1,
    ),
    CuratedSensor(
        "slope_consumption_values.descent_slope_consumption.physical_value",
        "Downhill consumption",
        None,
        "kWh/100km",
        "measurement",
        icon="mdi:terrain",
        suggested_display_precision=1,
    ),
    # === Temperature ===
    CuratedSensor(
        "outdoor_temperature",
        "Outside temperature",
        "temperature",
        "°C",
        "measurement",
    ),
    CuratedSensor(
        "min_temperature", "Battery min temperature", "temperature", "°C", "measurement"
    ),
    CuratedSensor(
        "max_temperature", "Battery max temperature", "temperature", "°C", "measurement"
    ),
    # === Vehicle Status ===
    # Both the bare and dotted field names occur on dotted (ID.x/Cupra) cars.
    # Some payloads carry only one of them, so keep both registered; discovery
    # skips the bare one when the dotted field is also present (see sensor.py).
    CuratedSensor(
        "instrument_cluster_time",
        "Vehicle clock",
        "timestamp",
        None,
        None,
        transform="iso_timestamp",
        icon="mdi:car-clock",
        translation_key="instrument_cluster_time",
    ),
    CuratedSensor(
        "profile_state_report.instrument_cluster_time",
        "Vehicle clock",
        "timestamp",
        None,
        None,
        transform="iso_timestamp",
        icon="mdi:car-clock",
        translation_key="instrument_cluster_time",
    ),
    CuratedSensor(
        "battery_level_HV.value",
        "HV battery level",
        "battery",
        "%",
        "measurement",
        suggested_display_precision=1,
        translation_key="hv_battery_level",
    ),
    # === Enum/Status Sensors ===
    CuratedSensor(
        "charging_state_report.current_charge_state",
        "Charge state",
        icon="mdi:ev-station",
        translation_key="charge_state",
    ),
    CuratedSensor(
        "charging_state_report.charge_mode",
        "Charge mode",
        icon="mdi:ev-station",
        translation_key="charge_mode",
    ),
    CuratedSensor(
        "charging_state_report.charge_type",
        "Charge type",
        icon="mdi:power-plug",
        translation_key="charge_type",
    ),
    CuratedSensor(
        "charging_state_report.charging_scenario",
        "Charging scenario",
        icon="mdi:ev-station",
        translation_key="charging_scenario",
    ),
    CuratedSensor(
        "charging_state_report.immediate_action_state",
        "Charging action state",
        icon="mdi:ev-station",
        translation_key="immediate_action_state",
    ),
    CuratedSensor(
        "settings.charge_mode_selection",
        "Charge mode selection",
        icon="mdi:cog",
        translation_key="charge_mode_selection",
    ),
    CuratedSensor(
        "settings.max_charge_current_ac",
        "Max AC charge current",
        icon="mdi:current-ac",
        translation_key="max_ac_charge_current",
    ),
    CuratedSensor(
        "settings.auto_unlock_ac",
        "Auto unlock AC",
        icon="mdi:lock-open",
        translation_key="auto_unlock_ac",
    ),
    CuratedSensor(
        "setting.bcam_activation",
        "BCAM activation",
        icon="mdi:battery-heart",
        translation_key="bcam_activation",
    ),
    CuratedSensor(
        "profile_state_report.next_charging_timer_information.target_reachability",
        "Charging timer reachability",
        icon="mdi:timer-outline",
        translation_key="charging_timer_reachability",
    ),
    CuratedSensor(
        "window_heating_state",
        "Window heating",
        icon="mdi:car-defrost-rear",
        translation_key="window_heating_state",
    ),
    CuratedSensor("bem_level", "BEM level", None, None, None, icon="mdi:information"),
)

CURATED_BINARY_DOTTED: tuple[CuratedBinary, ...] = (
    # === General Lock State ===
    CuratedBinary("locked", "Vehicle locked", "lock", invert=True, icon="mdi:car-key"),
    CuratedBinary(
        "open",
        "Vehicle open",
        "door",
        icon="mdi:car-door-open",
        encoding="onoff",
    ),
    # ID.x datasets carry a flat-named parking_brake field even though most of
    # their fields are dotted, so it belongs in the dotted group too.
    CuratedBinary(
        "parking_brake",
        "Parking brake",
        None,
        icon="mdi:car-brake-parking",
        encoding="onoff",
    ),
    # === Parking Lights ===
    CuratedBinary(
        "parking_light_left", "Parking light left", "light", icon="mdi:car-parking-lights"
    ),
    CuratedBinary(
        "parking_light_right", "Parking light right", "light", icon="mdi:car-parking-lights"
    ),
    # === Charge Mode Options ===
    CuratedBinary(
        "charge_mode_selection_options.immediate_charging",
        "Immediate charging",
        None,
        icon="mdi:ev-station",
    ),
    CuratedBinary(
        "charge_mode_selection_options.immediate_discharging",
        "Immediate discharging",
        None,
        icon="mdi:ev-station",
    ),
    CuratedBinary(
        "charge_mode_selection_options.timer_charging",
        "Timer charging",
        None,
        icon="mdi:timer",
    ),
    CuratedBinary(
        "charge_mode_selection_options.timer_charging_climatization",
        "Timer charging climatization",
        None,
        icon="mdi:timer",
    ),
    CuratedBinary(
        "charge_mode_selection_options.home_storage_charging",
        "Home storage charging",
        None,
        icon="mdi:home-battery",
    ),
    CuratedBinary(
        "charge_mode_selection_options.only_own_current",
        "Only own current",
        None,
        icon="mdi:current-ac",
    ),
    CuratedBinary(
        "charge_mode_selection_options.preferred_charging_times",
        "Preferred charging times",
        None,
        icon="mdi:clock-outline",
    ),
)

# ---------------------------------------------------------------------------
# Curated sensors for pre-ID.x vehicles (flat field names)
# ---------------------------------------------------------------------------

CURATED_SENSORS_FLAT: tuple[CuratedSensor, ...] = (
    # === Distance & Range ===
    CuratedSensor(
        "mileage",
        "Mileage",
        "distance",
        "km",
        "total_increasing",
        icon="mdi:counter",
        suggested_display_precision=0,
        monotonic=True,
    ),
    CuratedSensor(
        "cruising_range_combined",
        "Range (combined)",
        "distance",
        "km",
        "measurement",
        icon="mdi:map-marker-distance",
        suggested_display_precision=0,
        sum_fallback_fields=(
            "cruising_range_primary_engine",
            "cruising_range_secondary_engine",
        ),
    ),
    CuratedSensor(
        "cruising_range_primary_engine",
        "Range (primary)",
        "distance",
        "km",
        "measurement",
        icon="mdi:gas-station",
        suggested_display_precision=0,
    ),
    CuratedSensor(
        "value_of_the_primary_range",
        "Electric range",
        "distance",
        "km",
        "measurement",
        icon="mdi:map-marker-distance",
        unit_fields=PRIMARY_RANGE_UNIT_FIELDS,
        suggested_display_precision=0,
    ),
    CuratedSensor(
        "cruising_range_secondary_engine",
        "Range (secondary)",
        "distance",
        "km",
        "measurement",
        icon="mdi:ev-station",
        suggested_display_precision=0,
    ),
    CuratedSensor(
        "range",
        "Electric range",
        "distance",
        "km",
        "measurement",
        icon="mdi:map-marker-distance",
        suggested_display_precision=0,
    ),
    CuratedSensor(
        "scr_range",
        "SCR range",
        "distance",
        "km",
        "measurement",
        icon="mdi:map-marker-distance",
        suggested_display_precision=0,
    ),
    # === Battery (PHEV / hybrid: flat field) ===
    CuratedSensor(
        "state_of_charge",
        "Battery",
        "battery",
        "%",
        "measurement",
    ),
    CuratedSensor(
        "charging_power",
        "Charge power",
        "power",
        "kW",
        "measurement",
        icon="mdi:flash",
    ),
    CuratedSensor(
        "actual_charge_rate",
        "Charge rate",
        None,
        "km/h",
        "measurement",
        icon="mdi:speedometer",
        unit_field="charge_rate_unit",
        unit_resolver="charge_rate",
    ),
    CuratedSensor(
        "remaining_charging_time",
        "Remaining charging time",
        "duration",
        "min",
        "measurement",
        icon="mdi:battery-clock",
    ),
    CuratedSensor(
        "charged_energy",
        "Total energy charged",
        "energy",
        "kWh",
        "total_increasing",
        transform="deci_kwh",
        icon="mdi:lightning-bolt-circle",
    ),
    CuratedSensor(
        "boardnetBatteryVoltageIndication",
        "12V battery voltage",
        "voltage",
        "V",
        "measurement",
        icon="mdi:car-battery",
        suggested_display_precision=2,
    ),
    CuratedSensor(
        "last_charge_kwh",
        "Last charge",
        None,
        "kWh",
        "measurement",
        icon="mdi:battery-charging-wireless",
        translation_key="last_charge_kwh",
    ),
    # === Fuel ===
    CuratedSensor(
        "fuel_level_current_level",
        "Fuel level",
        None,
        "%",
        "measurement",
        icon="mdi:gas-station",
    ),
    CuratedSensor(
        "fuel_level__accuracy",
        "Fuel level accuracy",
        None,
        None,
        None,
        icon="mdi:gauge",
    ),
    CuratedSensor(
        "cng_gas_level",
        "CNG gas level",
        None,
        "%",
        "measurement",
        icon="mdi:gas-cylinder",
    ),
    # === Temperature ===
    CuratedSensor(
        "outside_temperature",
        "Outside temperature",
        "temperature",
        "°C",
        "measurement",
        transform="decikelvin_to_celsius",
    ),
    CuratedSensor(
        "min_temperature", "Battery min temperature", "temperature", "°C", "measurement"
    ),
    CuratedSensor(
        "max_temperature", "Battery max temperature", "temperature", "°C", "measurement"
    ),
    # === Climate ===
    # Flat PHEV format (issue #18) delivers remaining_climatisation_time as an
    # integer count of MINUTES, aliased to remaining_climate_time. The dotted
    # format instead sends a "<seconds>s" string (see the dotted registry entry,
    # which keeps unit "s"/duration_s). Declare minutes here and skip duration_s
    # so a flat value of 10 renders as "10 min" rather than "10 s".
    CuratedSensor(
        "remaining_climate_time",
        "Remaining climate time",
        "duration",
        "min",
        "measurement",
    ),
    CuratedSensor(
        "residual_energy_in_percent",
        "Residual energy",
        None,
        "%",
        "measurement",
        icon="mdi:battery",
    ),
    # === Tire Pressure ===
    CuratedSensor(
        "tyre_pressure_actual_front_left",
        "Tire pressure FL",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:car-tire-alert",
    ),
    CuratedSensor(
        "tyre_pressure_actual_front_right",
        "Tire pressure FR",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:car-tire-alert",
    ),
    CuratedSensor(
        "tyre_pressure_actual_rear_left",
        "Tire pressure RL",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:car-tire-alert",
    ),
    CuratedSensor(
        "tyre_pressure_actual_rear_right",
        "Tire pressure RR",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:car-tire-alert",
    ),
    CuratedSensor(
        "tyre_pressure_actual_spare_tyre",
        "Tire pressure spare",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:car-tire-alert",
    ),
    CuratedSensor(
        "tyre_pressure_required_front_left",
        "Required tire pressure FL",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:car-tire-alert",
    ),
    CuratedSensor(
        "tyre_pressure_required_front_right",
        "Required tire pressure FR",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:car-tire-alert",
    ),
    CuratedSensor(
        "tyre_pressure_required_rear_left",
        "Required tire pressure RL",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:car-tire-alert",
    ),
    CuratedSensor(
        "tyre_pressure_required_rear_right",
        "Required tire pressure RR",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:car-tire-alert",
    ),
    CuratedSensor(
        "tyre_pressure_required_spare_tyre",
        "Required tire pressure spare",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:car-tire-alert",
    ),
    CuratedSensor(
        "tyre_pressure_differential_front_left",
        "Tire pressure diff FL",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:gauge",
    ),
    CuratedSensor(
        "tyre_pressure_differential_front_right",
        "Tire pressure diff FR",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:gauge",
    ),
    CuratedSensor(
        "tyre_pressure_differential_rear_left",
        "Tire pressure diff RL",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:gauge",
    ),
    CuratedSensor(
        "tyre_pressure_differential_rear_right",
        "Tire pressure diff RR",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:gauge",
    ),
    CuratedSensor(
        "tyre_pressure_differential_spare_tyre",
        "Tire pressure diff spare",
        "pressure",
        "bar",
        "measurement",
        icon="mdi:gauge",
    ),
    # === Window Positions (0-100%) ===
    CuratedSensor(
        "position_front_left_door_window_lifter",
        "Front left window position",
        None,
        "%",
        None,
        icon="mdi:window-open-variant",
    ),
    CuratedSensor(
        "position_front_right_door_window_lifter",
        "Front right window position",
        None,
        "%",
        None,
        icon="mdi:window-open-variant",
    ),
    CuratedSensor(
        "position_rear_left_door_window_lifter",
        "Rear left window position",
        None,
        "%",
        None,
        icon="mdi:window-open-variant",
    ),
    CuratedSensor(
        "position_rear_right_door_window_lifter",
        "Rear right window position",
        None,
        "%",
        None,
        icon="mdi:window-open-variant",
    ),
    # === Sunroof ===
    CuratedSensor(
        "position_sunroof_motor_hood_1",
        "Sunroof position",
        None,
        "%",
        None,
        icon="mdi:car-convertible",
    ),
    # === Maintenance ===
    # The portal encodes these intervals as a countdown that rises toward 0:
    # negative = remaining (e.g. -127 d / -23500 km until service), 0 = due,
    # positive = overdue. The previous abs() collapsed both states to a positive
    # number, so an overdue service was indistinguishable from a remaining one.
    # Keep the raw sign here; the *_due_date sensors below re-express the
    # time-based intervals as an unambiguous timestamp, so the raw day counters
    # are disabled by default in favour of those dates.
    CuratedSensor(
        "maintenance_interval__time_until_inspection",
        "Inspection interval",
        None,
        "d",
        "measurement",
        icon="mdi:calendar-clock",
        suggested_display_precision=0,
        enabled_by_default=False,
    ),
    CuratedSensor(
        "maintenance_interval__time_until_oil_change",
        "Oil change interval",
        None,
        "d",
        "measurement",
        icon="mdi:oil",
        suggested_display_precision=0,
        enabled_by_default=False,
    ),
    CuratedSensor(
        "maintenance_interval_distance_until_inspection",
        "Inspection distance",
        "distance",
        "km",
        "measurement",
        icon="mdi:car-wrench",
        suggested_display_precision=0,
    ),
    CuratedSensor(
        "maintenance_interval_distance_until_oil_change",
        "Oil change distance",
        "distance",
        "km",
        "measurement",
        icon="mdi:oil",
        suggested_display_precision=0,
    ),
    # Time-based intervals re-expressed as a concrete due date, derived from the
    # signed day countdown above (see maintenance_due_datetime and the
    # ".due_date" handling in sensor.py).
    CuratedSensor(
        "maintenance_interval__time_until_inspection.due_date",
        "Inspection due",
        "timestamp",
        translation_key="inspection_due_date",
        icon="mdi:calendar-clock",
    ),
    CuratedSensor(
        "maintenance_interval__time_until_oil_change.due_date",
        "Oil change due",
        "timestamp",
        translation_key="oil_change_due_date",
        icon="mdi:oil",
    ),
    # === Trip Statistics - Long Term ===
    CuratedSensor(
        "long_term_data_mileage",
        "Trip distance (long)",
        "distance",
        "km",
        "total_increasing",
        icon="mdi:map-marker-distance",
        suggested_display_precision=0,
    ),
    CuratedSensor(
        "long_term_data_start_mileage",
        "Trip start mileage (long)",
        "distance",
        "km",
        None,
        icon="mdi:counter",
        suggested_display_precision=0,
    ),
    CuratedSensor(
        "long_term_data_average_fuel_consumption",
        "Avg fuel consumption (long)",
        None,
        "L/100km",
        "measurement",
        icon="mdi:gas-station",
        transform="fuel_consumption",
        suggested_display_precision=1,
    ),
    CuratedSensor(
        "long_term_data_average_electr_engine_consumption",
        "Avg electric consumption (long)",
        None,
        "kWh/100km",
        "measurement",
        icon="mdi:lightning-bolt",
        transform="electr_consumption",
        suggested_display_precision=1,
    ),
    CuratedSensor(
        "long_term_data_average_speed",
        "Avg speed (long)",
        None,
        "km/h",
        "measurement",
        icon="mdi:speedometer",
    ),
    CuratedSensor(
        "long_term_data_travel_time",
        "Travel time (long)",
        "duration",
        "min",
        "total_increasing",
        icon="mdi:clock-outline",
    ),
    # === Trip Statistics - Short Term ===
    CuratedSensor(
        "short_term_data_mileage",
        "Trip distance (short)",
        "distance",
        "km",
        "total_increasing",
        icon="mdi:map-marker-distance",
        suggested_display_precision=0,
    ),
    CuratedSensor(
        "short_term_data_start_mileage",
        "Trip start mileage (short)",
        "distance",
        "km",
        None,
        icon="mdi:counter",
        suggested_display_precision=0,
    ),
    CuratedSensor(
        "short_term_data_average_fuel_consumption",
        "Avg fuel consumption (short)",
        None,
        "L/100km",
        "measurement",
        icon="mdi:gas-station",
        transform="fuel_consumption",
        suggested_display_precision=1,
    ),
    CuratedSensor(
        "short_term_data_average_electr_engine_consumption",
        "Avg electric consumption (short)",
        None,
        "kWh/100km",
        "measurement",
        icon="mdi:lightning-bolt",
        transform="electr_consumption",
        suggested_display_precision=1,
    ),
    CuratedSensor(
        "short_term_data_travel_time",
        "Travel time (short)",
        "duration",
        "min",
        "total_increasing",
        icon="mdi:clock-outline",
    ),
    CuratedSensor(
        "short_term_data_zero_emission_distance",
        "Zero-emission distance (short)",
        "distance",
        "km",
        "measurement",
        icon="mdi:leaf",
        transform="hectometers_to_km",
        suggested_display_precision=1,
    ),
    CuratedSensor(
        "short_term_data_range_gain_distance",
        "Range gain distance (short)",
        "distance",
        "km",
        "measurement",
        icon="mdi:map-marker-distance",
        transform="hectometers_to_km",
        suggested_display_precision=1,
    ),
    CuratedSensor(
        "long_term_data_zero_emission_distance",
        "Zero-emission distance (long)",
        "distance",
        "km",
        "measurement",
        icon="mdi:leaf",
        transform="hectometers_to_km",
        suggested_display_precision=1,
    ),
    CuratedSensor(
        "long_term_data_range_gain_distance",
        "Range gain distance (long)",
        "distance",
        "km",
        "measurement",
        icon="mdi:map-marker-distance",
        transform="hectometers_to_km",
        suggested_display_precision=1,
    ),
    # === Oil Level ===
    CuratedSensor(
        "oil_level_actual_level", "Oil level", None, "%", "measurement", icon="mdi:oil"
    ),
    CuratedSensor(
        "oil_level_additional_oil_level",
        "Additional oil level",
        None,
        "%",
        "measurement",
        icon="mdi:oil",
    ),
    CuratedSensor(
        "oil_level_total_max", "Max oil level", None, "L", None, icon="mdi:oil"
    ),
    CuratedSensor(
        "oil_level_dipstick_indicator_function",
        "Oil dipstick indicator",
        None,
        None,
        None,
        icon="mdi:gauge",
    ),
    # === Vehicle Status ===
    CuratedSensor(
        "instrument_cluster_time",
        "Vehicle clock",
        "timestamp",
        None,
        None,
        transform="iso_timestamp",
        icon="mdi:car-clock",
        translation_key="instrument_cluster_time",
    ),
    CuratedSensor(
        "mileage.timestamp",
        "Last connected",
        "timestamp",
        None,
        None,
        icon="mdi:clock",
    ),
    # === Enum/Status Sensors (PHEV flat string enums) ===
    CuratedSensor(
        "charging_state",
        "Charge state",
        icon="mdi:ev-station",
        translation_key="charging_state",
    ),
    CuratedSensor(
        "charging_mode",
        "Charge mode",
        icon="mdi:ev-station",
        translation_key="charging_mode",
    ),
    CuratedSensor(
        "charging_reason_trigger",
        "Charging reason",
        icon="mdi:timer-outline",
        translation_key="charging_reason_trigger",
    ),
    CuratedSensor(
        "last_battery_charger_update_trigger",
        "Charger update trigger",
        icon="mdi:flash",
        translation_key="last_battery_charger_update_trigger",
    ),
    CuratedSensor(
        "window_heating_state",
        "Window heating",
        icon="mdi:car-defrost-rear",
        translation_key="window_heating_state",
    ),
    CuratedSensor("bem_level", "BEM level", None, None, None, icon="mdi:information"),
)

CURATED_BINARY_FLAT: tuple[CuratedBinary, ...] = (
    # === General Lock State ===
    CuratedBinary("locked", "Vehicle locked", "lock", invert=True, icon="mdi:car-key"),
    # === Individual Door Lock States (value 2=locked, 3=unlocked) ===
    CuratedBinary(
        "locked_state_front_left_door",
        "Front left door lock",
        "lock",
        invert=True,
        icon="mdi:car-door-lock",
    ),
    CuratedBinary(
        "locked_state_front_right_door",
        "Front right door lock",
        "lock",
        invert=True,
        icon="mdi:car-door-lock",
    ),
    CuratedBinary(
        "locked_state__rear_left_door",
        "Rear left door lock",
        "lock",
        invert=True,
        icon="mdi:car-door-lock",
    ),
    CuratedBinary(
        "locked_state_rear_right_door",
        "Rear right door lock",
        "lock",
        invert=True,
        icon="mdi:car-door-lock",
    ),
    CuratedBinary(
        "locked_state_tailgate",
        "Tailgate lock",
        "lock",
        invert=True,
        icon="mdi:car-door-lock",
    ),
    CuratedBinary(
        "locked_state_front_engine_bonnet",
        "Hood lock",
        "lock",
        invert=True,
        icon="mdi:car-door-lock",
    ),
    # === Door Open States (value 2=open, 3=closed, 0=unsupported, 1=invalid) ===
    CuratedBinary(
        "open_state_front_left_door", "Front left door", "door", icon="mdi:car-door"
    ),
    CuratedBinary(
        "open_state_front_right_door", "Front right door", "door", icon="mdi:car-door"
    ),
    CuratedBinary(
        "open_state_rear_left_door", "Rear left door", "door", icon="mdi:car-door"
    ),
    CuratedBinary(
        "open_state_rear_right_door", "Rear right door", "door", icon="mdi:car-door"
    ),
    CuratedBinary("open_state_tailgate", "Tailgate", "door", icon="mdi:car-back"),
    CuratedBinary("open_state_front_engine_bonnet", "Hood", "door", icon="mdi:car"),
    # === Door Safe States (value 2=safe, 3=unsafe, 0=unsupported, 1=invalid) ===
    CuratedBinary(
        "safe_state_front_right_door",
        "Front right door safe",
        "safety",
        invert=True,
        icon="mdi:shield-car",
    ),
    CuratedBinary(
        "safe_state_rear_left_door",
        "Rear left door safe",
        "safety",
        invert=True,
        icon="mdi:shield-car",
    ),
    CuratedBinary(
        "safe_state_rear_right_door",
        "Rear right door safe",
        "safety",
        invert=True,
        icon="mdi:shield-car",
    ),
    CuratedBinary(
        "safe_state_tailgate",
        "Tailgate safe",
        "safety",
        invert=True,
        icon="mdi:shield-car",
    ),
    CuratedBinary(
        "safe_state_front_engine_bonnet",
        "Hood safe",
        "safety",
        invert=True,
        icon="mdi:shield-car",
    ),
    # === Window States (value 2=open, 3=closed, 0=unsupported, 1=invalid) ===
    CuratedBinary(
        "state_front_left_door_window_lifter",
        "Front left window",
        "window",
        icon="mdi:window-open-variant",
    ),
    CuratedBinary(
        "state_front_right_door_window_lifter",
        "Front right window",
        "window",
        icon="mdi:window-open-variant",
    ),
    CuratedBinary(
        "state_rear_left_door_window_lifter",
        "Rear left window",
        "window",
        icon="mdi:window-open-variant",
    ),
    CuratedBinary(
        "state_rear_right_door_window_lifter",
        "Rear right window",
        "window",
        icon="mdi:window-open-variant",
    ),
    # === Sunroof States ===
    CuratedBinary(
        "state_sunroof_motor_hood_1", "Sunroof", "window", icon="mdi:car-convertible"
    ),
    CuratedBinary(
        "state_sunroof_motor_hood_3",
        "Sunroof motor 3",
        None,
        icon="mdi:car-convertible",
    ),
    # === Other Binary States ===
    CuratedBinary(
        "parking_brake",
        "Parking brake",
        None,
        icon="mdi:car-brake-parking",
        encoding="onoff",
    ),
    CuratedBinary(
        "parking_lights",
        "Parking lights",
        "light",
        icon="mdi:car-parking-lights",
        encoding="lights",
    ),
    CuratedBinary("state_of_hood", "Hood state", None, icon="mdi:car"),
    CuratedBinary("state_service_hatch", "Service hatch", None, icon="mdi:gas-station"),
    CuratedBinary("state_spoiler", "Spoiler", None, icon="mdi:car-sports"),
    # === PHEV flat string booleans ===
    CuratedBinary(
        "window_heating_state_front",
        "Window heating front",
        "heat",
        icon="mdi:car-defrost-rear",
        encoding="string_onoff",
    ),
    CuratedBinary(
        "window_heating_state_rear",
        "Window heating rear",
        "heat",
        icon="mdi:car-defrost-rear",
        encoding="string_onoff",
    ),
    CuratedBinary(
        "led_state",
        "Charging LED",
        None,
        icon="mdi:led-outline",
        encoding="string_onoff",
    ),
    CuratedBinary(
        "energy_flow",
        "Energy flow",
        "power",
        icon="mdi:transmission-tower",
        encoding="string_onoff",
    ),
    CuratedBinary(
        "plug_state",
        "Charging plug",
        "plug",
        icon="mdi:ev-plug-type2",
        encoding="plug",
    ),
    CuratedBinary(
        "lock_state",
        "Central lock",
        "lock",
        icon="mdi:lock",
        encoding="string_lock",
    ),
)

# ---------------------------------------------------------------------------
# Combined fields for backward compatibility and field validation
# ---------------------------------------------------------------------------

CURATED_FIELDS: frozenset[str] = frozenset(
    [s.field_name for s in CURATED_SENSORS_DOTTED]
    + [s.field_name for s in CURATED_SENSORS_FLAT]
    + [b.field_name for b in CURATED_BINARY_DOTTED]
    + [b.field_name for b in CURATED_BINARY_FLAT]
)


def field_coverage(points: dict[str, DataPoint]) -> dict[str, object]:
    """Summarise which dataset fields are curated vs exposed only as raw diagnostics."""
    present = {dp.field_name for dp in points.values()}
    omitted = {f for f in present if is_raw_metadata_field(f)}
    curated = sorted(present & CURATED_FIELDS)
    uncurated = sorted(present - CURATED_FIELDS - omitted)
    return {
        "field_count": len(present),
        "curated_count": len(curated),
        "uncurated_count": len(uncurated),
        "curated_fields": curated,
        "uncurated_fields": uncurated,
    }
