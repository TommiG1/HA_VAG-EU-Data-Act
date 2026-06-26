# Release notes

## v0.6.27 — Climate time, combined range & maintenance due dates (2026-06-27)

### Summary

Integrates community PRs from Pulpyyyy: flat **Remaining climate time** in
minutes ([#32](https://github.com/TommiG1/HA_VAG-EU-Data-Act/pull/32)),
**combined cruising range** fallback for PHEVs
([#30](https://github.com/TommiG1/HA_VAG-EU-Data-Act/pull/30)), and
**maintenance due date** sensors with preserved interval sign
([#35](https://github.com/TommiG1/HA_VAG-EU-Data-Act/pull/35)).

### Flat remaining climate time (#32)

- Flat PHEVs deliver `remaining_climatisation_time` as **minutes**, not seconds.
  The curated sensor now uses unit `min` without the dotted `duration_s`
  transform.
- Entity registry migration resets stale `s` → `min` overrides on existing
  `remaining_climate_time` entities.

### Combined cruising range (#30)

- When `cruising_range_combined` is empty but per-engine components are present,
  the sensor sums `cruising_range_primary_engine` +
  `cruising_range_secondary_engine`. A usable portal value always wins.

### Maintenance intervals (#35)

- Drops `abs()` on maintenance interval sensors so **negative = remaining**,
  **positive = overdue** (portal countdown semantics).
- Adds **Inspection due** and **Oil change due** timestamp sensors derived from
  the signed day countdown.
- Raw day counters are **disabled by default** in favour of the due-date
  sensors; distance counters stay enabled with raw sign.

### Note for existing installs

- **Remaining climate time:** reload the integration or reset the entity unit if
  it still shows seconds.
- **Maintenance day counters:** values flip from always-positive to signed;
  use the new due-date sensors for dashboards.

### Tests

- Offline checks for climate units, maintenance due-date math, and combined
  range fallback registration.
- Harness: corrupt-cache test cleans up disk cache to avoid cross-test leakage.

---

## v0.6.26 — Corrupt cache no longer blocks setup (#33) (2026-06-27)

### Summary

Fixes a startup crash when the newest local dataset ZIP is unreadable (truncated
download or portal error body saved as a `.zip`). Reported for a VW ID.3 after
HA restart ([#33](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/33)).

### Cache restore

- **`async_restore_from_cache`** now walks cached ZIPs newest-first, drops
  unreadable files, and tries the next older dataset instead of failing setup.
- Corrupt cache entries are **deleted** automatically with a warning in the log.

### Download path

- Portal ZIPs are **parsed before** they are written to the local cache, so
  invalid bytes never poison `/config/cupra_eu_data_act_cache/`.

### Tests

- Harness test `test_corrupt_cache_is_skipped_and_deleted_on_restore` covers the
  BadZipFile regression from #33.

---

## v0.6.25 — Passat PHEV flat charge rate (#27) (2026-06-25)

### Summary

Adds a curated **Charge rate** sensor for flat-format PHEVs (e.g. VW Passat,
Golf) that expose `actual_charge_rate` and `charge_rate_unit` instead of the
dotted `battery_state_report.*` fields ([#27](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/27)).
No scaling change — raw portal values are shown as delivered.

**Charge rate ≠ charge power.** For wallbox power in kW, use **Charge power**
(`charging_power` on flat PHEVs, `battery_state_report.charge_power` on
ID.x/MEB). Charge rate is range gained over time (km/h or mi/h).

### Flat PHEV charge rate (#27)

- **`actual_charge_rate`** — curated flat sensor with `mdi:speedometer`, unit
  resolved from companion `charge_rate_unit` (`km_per_h`, `miles_per_h`, etc.).
- **`resolve_charge_rate_unit`** — maps flat unit strings in addition to existing
  `CHARGE_RATE_UNIT_*` enums; `invalid` yields no unit.
- **Unit gating** — same invalid/unusable-reading rules as the dotted charge-rate
  sensor apply to `actual_charge_rate`.
- **Translations** — `actual_charge_rate` entity name in EN/DE/FR/IT/NL.

### Legacy helper: *Monthly electric consumption*

If you upgraded from **v0.6.22 or earlier**, you may still have a
`utility_meter` helper named *Monthly electric consumption*. The integration
**no longer creates** this helper (removed in v0.6.23,
[#24](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/24)) — it summed
driving-efficiency readings (`kWh/100km`) and produced meaningless monthly
totals.

- **Delete** the old helper under **Settings → Devices & services → Helpers**
  if it is still present.
- **Use instead:** *Monthly charged energy* (kWh) for monthly charging totals.

### Tests

- Offline checks for flat `actual_charge_rate` curation, flat unit resolution,
  and `CURATED_FIELDS` registration.

---

## v0.6.24 — Tyre-pressure curation, distance units & source_dataset (2026-06-20)

### Summary

Addresses the remaining sensor-mapping gaps from upstream
[mikrohard#33](https://github.com/mikrohard/hass-vw-eu-data-act/issues/33) and
completes per-entity provenance from
[mikrohard#31](https://github.com/mikrohard/hass-vw-eu-data-act/issues/31).

### Sensor mapping (#33)

- **`tyre_pressure_required_*`** (5 wheels) — curated as `bar` with
  `device_class: pressure` instead of the ambiguous portal unit
  `"10kPA / Bar / PSI/ kPA"`.
- **`tyre_pressure_differential_*`** — now also `bar` + `device_class: pressure`.
- **Zero-emission / range-gain distances** — `short_term_data_zero_emission_distance`,
  `short_term_data_range_gain_distance`, and long-term counterparts convert
  portal `100m` hectometers to **km** (÷10).
- Sentinel filtering for tyre validity codes (`0`/`1`) is limited to
  **`tyre_pressure_actual_*`** so required-pressure readings around 1.0 bar are
  not treated as invalid.

### Source dataset attribute (#31)

Every curated sensor, binary sensor, and raw diagnostic now exposes
**`source_dataset`** (portal ZIP filename) alongside the existing
`data_captured_at` / `age_minutes` freshness attributes. Populated on download
and cache restore.

### Tests

- Offline coverage for `hectometers_to_km`, curated field registration, required
  tyre-pressure sentinel behaviour, and `source_dataset` attributes.

---

## v0.6.23 — Remove incorrect monthly electric consumption helper (2026-06-19)

### Summary

Stops auto-creating the *Monthly electric consumption* `utility_meter` helper
([#24](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/24)). It was wired
to average driving-efficiency sensors (`kWh/100km`), so the helper reported the
wrong unit and meaningless totals. Use **Monthly charged energy** (kWh) for
monthly energy instead.

### Fix

- Removed the third auto-provisioned utility meter (sources were
  `long_term_data_average_electr_engine_consumption`,
  `short_term_data_average_electr_engine_consumption`, or
  `additional_consumptions.residual_consumption` — all `kWh/100km`).
- README note: delete any existing *Monthly electric consumption* helper
  manually; the integration no longer creates new ones.

---

## v0.6.22 — German charging labels & Terramar 12V voltage (2026-06-18)

### Summary

Renames three German entity display names that confused users testing a Cupra
Born ([#23](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/23)), and
exposes **12V boardnet battery voltage** for Terramar PHEV / flat-format
payloads ([#21](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/21)).
English and other languages are unchanged for the label renames. Entity IDs are
unchanged — only friendly names in the HA UI update after reload.

### Terramar 12V battery voltage (#21)

- Curated flat-field sensor for `boardnetBatteryVoltageIndication` (`device_class:
  voltage`, unit `V`, 2 decimal places).
- Appears only when the portal delivers the field (e.g. Cupra Terramar PHEV).

### German label changes

| translation_key | Old (DE) | New (DE) |
|-----------------|----------|----------|
| `battery_state_report_charge_bulk_threshold` | Bulk-Ladeschwelle | **Schwelle Langsamladung** |
| `battery_state_report_remaining_charging_time_bulk` | Restzeit bis Bulk | **Restzeit bis Langsamladung** |
| `immediate_action_state` | Ladeaktionsstatus | **Sofortlade-Status** |

- **Schwelle Langsamladung** — SOC % at which charging switches to the slower
  phase toward 100% (replaces VW-internal “bulk” jargon).
- **Sofortlade-Status** — active immediate-charging action; clearly distinct
  from **Lademodus** (*charge mode* setting).

---

## v0.6.21 — Per-sensor data freshness attributes (2026-06-18)

### Summary

Exposes when each curated and raw sensor reading was captured and how old it is,
so users can tell fresh vehicle data from stale portal snapshots without
comparing diagnostic sensors manually ([#22](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/22)).

### Entity attributes

Curated and raw (diagnostic) sensors now expose:

| Attribute | Meaning |
|-----------|---------|
| `data_captured_at` | Best-known capture time for the displayed value (ISO 8601) |
| `age_minutes` | Minutes between that capture time and now |
| `freshness_source` | `timestamp_utc`, `field_captured_time`, or `report_captured_time` |

Value fields such as `battery_state_report.soc` usually have no per-item
`timestampUtc`; their age comes from the report's `car_captured_time` stamped
onto the point in `Dataset.from_json`.

Distinct from HA entity `last_updated` (portal poll time) and from the global
`last_vehicle_update` / `dataset_generated` diagnostic sensors.

---

## v0.6.20 — Monotonic odometer & Terramar PHEV aliases (2026-06-17)

### Summary

Fixes **mileage reading low** when a single portal ZIP carries several
`mileage.value` slots from lagging report snapshots at the same capture time.
Also adds **Terramar PHEV** flat-field aliases so climate time, plug state, and
charge power resolve on those payloads.

v0.6.19 fixed cross-dataset freshness for value fields; this release closes the
remaining **intra-dataset** odometer case it left optional.

### Monotonic odometer

A single dataset can carry multiple `mileage.value` entries (e.g. `70876` vs
`70908` at the same `car_captured_time`). They tie on freshness, so
`find_by_field` fell back to last-in-ZIP — which can be the **lower** reading.

- Add `prefer_max_value` to `find_by_field`: for monotonic fields the largest
  numeric value wins; freshness and ZIP position only break exact-value ties.
- Add `monotonic` on the `mileage.value` / `mileage` curated sensors and
  thread it through the curated resolver in `sensor.py`.

The default `find_by_field` path is unchanged; only mileage uses
`prefer_max_value=True`.

Completes the integration-side odometer part of
[mikrohard#24](https://github.com/mikrohard/hass-vw-eu-data-act/issues/24).

### Terramar PHEV flat fields (#18)

- Alias `remaining_climatisation_time` → `remaining_climate_time`
- Alias `charging_plug1_connectionstate` → `plug_state`
- Expose flat `charging_power` as **Charge power**
- Use `charging_power` when detecting active charge on PHEV payloads

### Tests

- Offline regression: two `mileage.value` slots in one dataset — default picks
  last-in-ZIP, `prefer_max_value=True` picks the highest.
- Terramar alias and `charging_power` curated-sensor coverage.

---

## v0.6.19 — SoC/mileage freshness guard fix (2026-06-17)

### Summary

Fixes **battery level (SoC) oscillation** and **mileage regression** when the
portal delivers duplicate field slots or when the coordinator falls back to an
older dataset after a download failure.

Value fields such as `battery_state_report.soc` and `mileage.value` carry no
per-item `timestampUtc`. The existing freshness guard in `merge_data_points` and
the ranking in `find_by_field` therefore did nothing for exactly the fields
users report — stale readings could win by ZIP byte order or overwrite fresher
state on fallback.

### Change

- Stamp each `DataPoint` with the dataset's `car_captured_time` during
  `Dataset.from_json`.
- `_datapoint_freshness` falls back to that dataset-level timestamp when a point
  has no per-item timestamp.

No call-site changes. Fields that already expose `timestampUtc` behave as before.

Fixes [#15](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/15) (integration-side
part of [mikrohard#24](https://github.com/mikrohard/hass-vw-eu-data-act/issues/24)).

**Scope:** This addresses cross-dataset regression/oscillation and duplicate-key
selection. It does **not** reorder conflicting snapshots **within** a single ZIP
(portal-side). Two SoC slots at the same capture time may still tie on freshness;
a follow-up `prefer_max_value` hardening for mileage/SoC remains optional.

### Tests

- Offline regression: `from_json` stamps `captured_at` on value points.
- Older fallback dataset does not regress SoC (no per-item timestamp).
- Fresher dataset's SoC wins among lingering duplicate keys in the merged store.

---

## v0.6.18 — Tyre pressure validity fix (2026-06-16)

### Summary

Fixes curated tyre-pressure sensors showing **1 bar** when the portal reports
no valid per-wheel reading.

### Tyre pressure validity codes

VW `tyre_pressure_*` fields encode validity, not pressure directly:

- `0` = unsupported
- `1` = invalid
- any other integer = actual pressure reading

The integration now treats `0` and `1` as **unavailable** instead of displaying
them as bar values. Affected sensors include `tyre_pressure_actual_*` and
`tyre_pressure_differential_*`.

Addresses [#14](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/14).

**Note:** Per-wheel pressure is only available on vehicles with **direct TPMS**
(pressure sensors in the wheel valves). Many VAG cars use **indirect** monitoring
(RKA, via ABS wheel-speed sensors), which detects pressure loss but does not
expose individual bar/psi readings — in that case these sensors will correctly
stay unavailable.

### Tests

- Offline sentinel checks for tyre-pressure validity codes `0` and `1`.

---

## v0.6.17 — Cache restore, charging time fixes & HV battery label (2026-06-16)

### Summary

Restores vehicle data from the local ZIP cache after a Home Assistant restart or
when the portal listing fails, fixes the **`refresh_now`** service, and improves
remaining-charge-time sensors and duplicate-field handling.

### Cache restore on startup / portal outage

- After HA restart, the integration now loads the **newest local dataset ZIP**
  immediately so curated sensors keep their last-known values instead of showing
  **unavailable**.
- When portal listing or download fails but a cache exists, the coordinator
  serves cached data with status **`listing_failed`** instead of clearing all
  entities.

### Remaining charging time

- **Remaining charging time** and **Remaining time to bulk** now display in
  **minutes** (portal values are converted from seconds).
- Values are hidden when the car is not actively charging (e.g. charge power
  ≤ 0 or charging scenario OFF).
- Entity registry migration clears stale **`sensor.private`** unit overrides
  that forced seconds and sets the unit to **`min`**.

### HV battery level label

- Curated **`battery_level_HV.value`** now uses translation key
  **`hv_battery_level`** (e.g. **HV-Batteriestand** in German) so it no longer
  duplicates the generic **Battery** name from **`battery_state_report.soc`**.

### Duplicate field selection

- When the portal sends the same field multiple times without distinct
  timestamps, the integration now keeps the **last occurrence in the ZIP**
  (array order) instead of the smallest UUID key.

### Bug fix

- **`refresh_now`** service — fixed handler registration so Home Assistant can
  trigger an immediate portal refresh again.

### Tests

- Cache `read_latest` and coordinator restore-from-cache on HTTP 503.
- Updated duplicate-field and duration-transform offline checks.

---

## v0.6.16 — Timestamp labels & vehicle clock dedup (2026-06-15)

### Summary

Localized names for the dedicated timestamp sensors, consolidation of duplicate
**Vehicle clock** entities on Cupra/MEB cars, and curated PHEV flat-format
charging enums/binary sensors.

### Timestamp sensor localization

- **`last_vehicle_update`**, **`last_connected`**, and **`dataset_generated`**
  now have proper names in `de`, `en`, `fr`, `it`, and `nl` (no more generic
  “Timestamp” fallback in German).

Addresses [#12](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/12).

### Vehicle clock deduplication

Cupra/MEB payloads often expose both `instrument_cluster_time` and
`profile_state_report.instrument_cluster_time` with the same value, which
created duplicate curated sensors.

- Discovery prefers the dotted field when both are present; bare-only dotted
  cars still get a curated **Vehicle clock**.
- Registry migration disables legacy bare curated duplicates and old raw
  diagnostic copies when the dotted sensor exists.

### PHEV flat-format sensors

- Curated enum sensors: `charging_state`, `charging_mode`,
  `charging_reason_trigger`, `last_battery_charger_update_trigger`.
- Curated binary sensors with string encodings: window heating front/rear,
  charging LED, energy flow, plug state, central lock.
- Localized names and enum state labels in all supported languages.

### Tests

- Entity migration coverage for instrument-cluster dedup.
- Offline checks for PHEV flat binary/enum registration and string decoders.

---

## v0.6.15 — Last charge sensor state class (2026-06-14)

### Summary

Fixes a Home Assistant 2026.6 warning for the **Last charge** sensor
(`last_charge_kwh`): `device_class: energy` combined with
`state_class: measurement` is no longer valid.

### Bug fix

- **`last_charge_kwh`** — removed `device_class: energy`; keeps `kWh` unit,
  `measurement` state class, and existing delta logic (kWh from the last
  charging session). Same pattern as **Battery energy**.

Fixes [#10](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/10).

---

## v0.6.14 — Primary range distance units (2026-06-13)

### Summary

Fixes hardcoded **km** on the `value_of_the_primary_range` electric-range sensor
(Cupra/MEB datasets that expose a generic portal `value` field). Units are now
resolved from companion portal fields — important for UK vehicles reporting
range in **miles**.

### Distance unit resolution

- **`value_of_the_primary_range`** (curated + raw diagnostic) inherits units via
  fallback chain: `range.unit` → `mileage.unit` →
  `battery_state_report.cruising_ranges.*.unit` → default `km`.
- New helpers: `resolve_distance_unit_from_companion_fields()`,
  `resolve_primary_range_unit()`, and `CuratedSensor.unit_fields` for ordered
  fallbacks.
- **`mileage.value`** / **`range.value`** behaviour unchanged (still use their
  dedicated `*.unit` fields).

### Bug fix

- **Raw diagnostic sensors** no longer crash entity setup with
  `AttributeError` when `native_unit_of_measurement` was never set (e.g.
  enum/string raw fields).

### Tests

- Offline coverage for primary-range unit resolution (mileage.unit, range.unit,
  cruising_ranges fallback).

---

## v0.6.13 — Data dictionary V5.0 (2026-06-12)

### Summary

Bundled `data_dictionary.json` regenerated from the latest portal dictionary
**DataDictionary_V5.0_Continuous Data.pdf** (document version 1.0.5,
2026-02-25).

### Changes

- **1142** data points (+1 vs. previous bundle): new OBD MIL field
  (`OBD_MIL_XIX_OBD_04_XIX_HCP5_CAN03`).
- Provenance recorded in `data_dictionary_meta.json`.
- Regenerate locally: `python tools/parse_dictionary.py <PDF_PATH>`.

---

## v0.6.12 — Cupra dotted field mappings (2026-06-12)

### Summary

Curated sensors for additional ID.x / Cupra fields seen in live cache ZIPs
(upstream #2, iterative P7).

### New curated entities

- **`profile_state_report.instrument_cluster_time`** — vehicle clock (same as
  flat `instrument_cluster_time`; shares translation).
- **`battery_level_HV.value`** — HV battery level (%).
- **`open`** (binary) — vehicle open status from bare `open` boolean field.

### Tests

- Fixture `tests/fixtures/cupra_dotted_uncurated_sample.json` and offline
  coverage check.

---

## v0.6.11 — Portal backoff and listing status (2026-06-12)

### Summary

Clearer integration status when the portal listing API fails and slower retries
after repeated upstream 5xx errors (upstream #17, #25).

### Portal robustness

- New status **`listing_failed`** when dataset listing fails (HTTP 5xx or other
  non-400 errors) — distinct from **`waiting_for_portal_data`** (empty but
  successful listing).
- **`consecutive_server_errors`** counter with exponential backoff: next retry
  after 5 → 15 → 30 minutes (cap). Resets on a successful dataset load.
- Status sensor and diagnostics expose `consecutive_server_errors` and
  `next_retry_minutes`. Repairs issue **`listing_failed`** links to the portal.

---

## v0.6.10 — Disable legacy meta/raw entities (2026-06-12)

### Summary

Existing portal metadata raw sensors and the legacy **Last telemetry** curated
entity are now disabled in the entity registry on upgrade — not only blocked
for new installs (P6 follow-up).

### Registry migration

- Disables legacy `{vin}_car_captured_time` (use **Last vehicle update**).
- Disables existing raw diagnostic entities whose field name matches the
  metadata blocklist (`message_id`, `report_type`, `timestamp`,
  `car_captured_utc_timestamp`, `car_captured_time`, and dotted variants).
- Bare `timestamp` is blocked; curated `mileage.value.timestamp` is not.

Reload the integration once after updating to apply the migration.

---

## v0.6.9 — Timestamp entity consolidation (2026-06-12)

### Summary

Fewer duplicate timestamp and metadata sensors (upstream #23). Dedicated
diagnostic sensors cover the same information without per-report raw copies.

### Removed curated duplicates

- `car_captured_time` (Last telemetry) — use **Last vehicle update**
  (`last_vehicle_update`).
- `mileage.value.timestamp` (Last connected legacy) — use **Last connected**
  (`last_connected`).

`instrument_cluster_time` (vehicle clock) is unchanged.

### Metadata field blocklist

- Raw diagnostic sensors are no longer created for portal metadata fields
  (`message_id`, `report_type`, `car_captured_time`, and dotted variants).
- `field_coverage` / **Uncurated fields count** excludes these intentionally
  omitted fields.

### Registry migration

- Legacy curated `car_captured_time` entities are disabled on upgrade.
- Existing `mileage.value.timestamp` / `mileage.timestamp` entities continue to
  migrate to `last_connected`.

---

## v0.6.8 — Timestamp-aware ordering (2026-06-12)

### Summary

Sensor history no longer jumps backwards when the portal delivers duplicate
fields or an older fallback dataset (upstream #24).

### Freshest reading wins

- `find_by_field` prefers the **freshest** matching data point (by its own
  `timestampUtc` / captured time) instead of an arbitrary `min(key)`. When no
  timestamps distinguish duplicates it still falls back to the stable
  `min(key)` choice, so sensors don't flip-flop.
- `merge_data_points` no longer regresses a usable value with an *older* one:
  after a download failure that falls back to a previous dataset, a stale
  snapshot can't overwrite fresher coordinator state.

### Tests

- Offline tests for freshest-duplicate selection, stable fallback, and the
  merge freshness guard.

---

## v0.6.7 — Local ZIP cache (2026-06-12)

### Summary

Downloaded portal ZIP files are cached locally for debugging and support
(upstream #31 part 2).

### Local dataset cache

- Successful downloads are stored under
  `config/cupra_eu_data_act_cache/<hash>/` (VIN is hashed — not in the path).
- Keeps the last **10** ZIPs per vehicle, max **50 MB** per vehicle; oldest
  files are removed automatically.
- **Integration status** attributes and diagnostics list cached filenames,
  sizes, and timestamps.

### API

- `async_download_dataset_raw()` returns ZIP bytes; `parse_dataset_zip()` parses
  them (coordinator caches before parsing).

### Tests

- `tests/test_cache.py` — rotation, unsafe-name rejection, size cap.

---

## v0.6.6 — Portal docs, charge-rate units & dataset metadata (2026-06-12)

### Summary

Addresses upstream feedback on portal setup (#14, #22), charge-rate unit
flip-flopping (#30), and dataset traceability (#31 part 1).

### Portal documentation

- README and TESTING now recommend **All Data** (not Charging-only) for the
  15-minute continuous request.
- Limitations note: service targets EU(27) residents with EU(27)-registered
  vehicles; accounts outside the EU may get no data delivery.
- English setup/repair strings updated accordingly.

### Charge rate unit stability

- Curated sensors with dynamic units use `_sticky_unit()` — a new unit is
  adopted only after two consecutive polls with the same enum.
- For `battery_state_report.charge_rate`, unit changes are ignored when the
  charge-rate value itself is missing or a portal sentinel.

### Dataset metadata

- Coordinator tracks `latest_dataset_name` and the last five download attempts
  (success/failure, error, timestamp).
- **Integration status** sensor and config-entry diagnostics expose these fields
  for support without manual portal downloads.

### Tests

- Offline tests for sticky unit and charge-rate gating.
- Coordinator test for successful download metadata.

---

## v0.6.5 — Last-known values & last-connected fix (2026-06-12)

### Summary

Sensor values no longer regress when the portal delivers empty snapshots,
sentinel readings, or temporary API errors. The **Last connected** entity is
registered reliably and works on Cupra/MEB datasets that omit `timestampUtc`
on the mileage field.

### Last-known value retention

- **Coordinator merge** — new snapshots no longer overwrite good readings with
  portal sentinels or missing fields (`merge_data_points` / `is_usable_reading`).
- **`find_by_field`** — when duplicate field names exist, usable values are
  preferred over sentinel garbage.
- **Listing failures** — if data was loaded before, poll errors (including HTTP
  400 “delivery not ready”) keep the previous dataset instead of failing the
  update cycle.

Entity-level sticky semantics are unchanged; this release hardens the shared
coordinator state underneath.

### Last connected sensor

- Dedicated **`last_connected`** sensor, registered at setup (not discovery-only).
- **`last_connected_time()`** — uses the mileage timestamp when present, otherwise
  falls back to the newest car-captured time in the payload.
- **Registry migration** — legacy `unique_id`s (`mileage.value.timestamp` /
  `mileage.timestamp`) are renamed to `last_connected` *before* platforms load,
  so restored/orphan entities are adopted instead of staying unavailable.

### Tests

- Offline tests for merge, sentinel preference, and `last_connected_time` fallback.
- Coordinator tests for HTTP 400 with existing data and sentinel merge behaviour.

---

## v0.6.4 — Data freshness sensors & readable enum labels (2026-06-11)

### Summary

Clearer enum display, stricter timestamp sensor creation, and two diagnostic
sensors that separate vehicle freshness from portal delivery time.

### Readable enum values

Long VW enum strings (e.g. `CHARGE_STATE_CHARGING_HV_BATTERY`) are shortened for
display on raw diagnostic sensors and curated text fields without a dedicated
`translation_key`. Curated enum sensors with existing state translations are
unchanged.

### Data freshness diagnostics

| Entity | Purpose |
|--------|---------|
| `last_vehicle_update` | When the vehicle last reported to the backend (`car_captured_time` and variants) |
| `dataset_generated` | When the portal generated the currently loaded dataset ZIP |

`minutes_since_last_snapshot` and `last_snapshot_at` now consider all captured-time
field variants, not only flat `car_captured_time`.

### Timestamp curated sensors

`.timestamp` curated entities are created only when the base field carries a
real `timestampUtc` value — avoids forever-unknown sensors on datasets that
list the field name but omit the timestamp.

---

## v0.6.3 — Localization, health, energy & Lovelace hints (2026-06-11)

### Summary

Localized binary sensors, subscription and snapshot health monitoring, energy
helpers, and Lovelace entity guidance. Includes a startup fix for
`utility_meter` (`slugify` import).

### Binary sensors localized (Tier A1)

All ~40 curated binary sensors use `translation_key` + multilingual names
(de / en / fr / it / nl). Entity registry migration covers `binary_sensor`
domain entries.

### Portal health (Tier A3 + B11 + B12)

| Entity | Purpose |
|--------|---------|
| `days_until_subscription_expires` | Estimated days left on ~12-month portal subscription |
| `minutes_since_last_snapshot` | Age of last real vehicle telemetry |
| `uncurated_fields_count` | Count of dataset fields without curated mapping |

**Repairs issues:** `subscription_expiring_soon` (≤30 days), `stale_snapshot`
(>12h). Diagnostics download lists up to 20 uncurated field names.

### Energy (Tier A2 + B8)

- **`last_charge_kwh`** — kWh from the last charging session (delta of cumulative
  totals when `battery_state_report.charge_energy` or `charged_energy` is present)
- **Auto utility meters** — monthly helpers for charged energy, mileage, and
  electric consumption (created on first data if source sensors exist)

See README for Energy dashboard entity recommendations.

### Lovelace hints (Tier B9)

`dashboards/README.md` — which curated entities to add in your own dashboard
(no YAML templates; entity IDs differ per installation).

---

## v0.6.2 — Service schema compatibility fix (2026-06-11)

### Summary

Fixes a startup crash on Home Assistant versions that do not provide
`cv.config_entry_id`. The integration failed to import and could prevent
Home Assistant from starting when the custom component was installed.

### Fix

`cupra_eu_data_act.refresh_now` now validates the optional vehicle selector
with `cv.string`; the config entry is resolved and checked at runtime.

---

## v0.6.1 — Refresh button on device (2026-06-11)

### Summary

Adds a native **Button** entity on each vehicle device so users can trigger a
portal fetch from the device page — no need to open Developer Tools.

### New entity

| Entity | Action |
|--------|--------|
| **Refresh now** (`button.*`) | Queries the EU Data Act portal immediately |

Localized in de / en / fr / it / nl. Always available, even before the first
dataset arrives. Reload the integration once after updating to register the
new platform.

---

## v0.6.0 — Manual refresh service (2026-06-11)

### Summary

New service to poll the portal on demand instead of waiting for the next
scheduled coordinator interval (~15 minutes after the last snapshot).

### Service

`cupra_eu_data_act.refresh_now`

- Optional `config_entry` field to target one vehicle; omit to refresh all.
- Also callable with a device target in automations.
- Waits until the fetch completes (`async_refresh`).

---

## v0.5.5 — Entity registry migration import fix (2026-06-11)

### Summary

Fixes a circular import that prevented the integration from loading after
v0.5.4 (`entity_migration` imported `EudaConfigEntry` from `__init__.py`).

### Fix

`entity_migration.py` now uses `ConfigEntry` from Home Assistant directly,
matching `issues.py` and `diagnostics.py`.

---

## v0.5.4 — Curated sensor name display fix (2026-06-11)

### Summary

Fixes all curated sensors showing only the device nickname (e.g.
`All_Data_Cupra`) instead of translated names like **Battery** / **Batterie**.

### Cause & fix

Setting `_attr_name = None` tells Home Assistant to use the **device name only**
and skips `translation_key` lookup. Removed explicit `_attr_name = None` on
curated sensors; names now come from entity translations.

### Entity registry migration

Existing installations get `translation_key` and cleared custom names via
`entity_migration.py` on setup.

---

## v0.5.3 — All curated sensor names localized (2026-06-11)

### Summary

Every curated sensor now uses HA entity translations for its **name** in
de / en / fr / it / nl (88 translation keys covering all dotted and flat
curated fields). Enum sensors keep their localized state labels from v0.5.2.

Translation keys are derived automatically from the field name
(`mileage.value` → `mileage_value`) unless a shorter key is set explicitly
(e.g. `charge_state`).

Catalog: `tools/sensor_name_labels.py` — verify with
`python tools/verify_sensor_translations.py`, regenerate JSON with
`python tools/build_entity_translations.py`.

---

## v0.5.2 — Multilingual enum labels (2026-06-11)

### Summary

Enum and status sensors now use Home Assistant entity translations instead of
raw `SCREAMING_SNAKE_CASE` portal strings — shorter, localized labels in the
entity list (de / en / fr / it / nl).

### Translated sensors

Charge state, charge mode, charge type, charging scenario, immediate action
state, charge mode selection, max AC current, auto unlock AC, BCAM activation,
charging timer reachability, window heating, and integration status.

Catalog: `tools/entity_translation_catalog.py` — regenerate JSON with
`python tools/build_entity_translations.py`.

---

## v0.5.1 — Telemetry timestamps (2026-06-11)

### Summary

Curated timestamp sensors for portal capture time and the vehicle's
instrument-cluster clock — more reliable "when was the car last online" than
derived mileage timestamps.

### New sensors (dotted / ID.x format)

| Field | Entity | Notes |
|-------|--------|-------|
| `car_captured_time` | Last telemetry | ISO timestamp from the portal snapshot |
| `instrument_cluster_time` | Vehicle clock | Car-local time used for charging timers |

Values are parsed via new `iso_timestamp` transform (`parse_timestamp` in
`data.py`).

---

## v0.5.0 — Energy dashboard, Repairs & Diagnostics (2026-06-11)

### Summary

Fixes invalid energy sensor metadata so cumulative charging kWh can appear in
Home Assistant's Energy dashboard, surfaces portal delivery problems in the
native Repairs center, and adds a redacted diagnostics download for support.

### Energy dashboard compatibility
Sensors with `device_class: energy` must use `state_class: total_increasing`
(or `total`), not `measurement`. Battery level/capacity sensors
(`energy_contents.*`) no longer claim the `energy` device class — they report
instantaneous kWh content, not cumulative consumption.

Added curated flat-format sensor **`charged_energy`** (total energy charged,
`deci_kwh` transform, `total_increasing`) for PHEV/hybrid vehicles that expose
lifetime charging totals.

### Repairs issues for portal states
When the integration status is `delivery_not_ready`, `waiting_for_portal_data`,
or `empty_snapshots`, a clickable issue now appears under **Settings → Repairs**
with a link to the EU Data Act portal and setup guidance. Issues clear
automatically when data delivery succeeds.

### Diagnostics download
**Download diagnostics** on the config entry returns redacted JSON with
integration version, status, field coverage (curated vs uncurated), and latest
dataset metadata — no email, password, or VIN.

---

## v0.4.1 — Reauth flow, robust API errors, binary refactor (2026-06-11)

### Summary

Hardens the integration around session expiry and upstream flakiness, and
cleans up the binary-sensor decoding so each field declares how it encodes
on/off instead of being guessed by name. Inspired by
[mikrohard/hass-vw-eu-data-act PR #28](https://github.com/mikrohard/hass-vw-eu-data-act/pull/28),
adapted to this fork's multi-brand setup and non-blocking startup.

### Session expiry now triggers HA's reauth dialog
The coordinator used to swallow expired-session errors during the dataset
download as generic update failures, so the integration silently retried for
hours instead of asking you to log in again. `AuthError` is now caught
explicitly on both the listing and download paths and surfaces as
`ConfigEntryAuthFailed`, which is what Home Assistant uses to prompt for
re-authentication. The reauth step preserves your brand (Škoda, Cupra, …)
from the stored entry, so re-login goes to the right OIDC client.

### `ApiError` carries the HTTP status
HTTP failures used to be detected by grepping `"HTTP 500"` out of the
exception message — fragile and easy to break with rewording. `ApiError`
now has a typed `status` attribute, and the coordinator branches on
`status == 400` (subscription not yet active, surfaced as the existing
`delivery_not_ready` state) and `status in {500, 502, 503, 504}` (transient
upstream errors worth retrying / keeping the previous dataset). The
integration status sensor reports `delivery_not_ready` in this case so you
can see at a glance why no fresh data is arriving.

### Binary sensors: explicit encoding instead of name guessing
The 50-line if/elif chain in `binary_sensor.py` that decided how to read a
boolean from a field name (`parking_brake` vs `parking_lights` vs
`open_state` vs `locked_state` …) is gone. `CuratedBinary` now declares its
`encoding` (`open`, `onoff`, `lights`) and a single `decode_binary_state`
helper does the conversion. Same behavior as before, but adding a new
binary field is now one line and the decoding is fully unit-tested.

### HA 2026.8 compatibility
The coordinator now passes `config_entry=entry` to `DataUpdateCoordinator.__init__`.
The ContextVar-based fallback is deprecated and stops working in
Home Assistant 2026.8.

### Test coverage
New `tests/test_coordinator.py` and `tests/test_config_flow.py` use
`pytest-homeassistant-custom-component` to verify the reauth behavior end
to end with a real `hass` instance. The existing offline tests cover the
new `decode_binary_state`, `ApiError.status`, and the centralized
`find_by_field` helper. Both suites run in CI on every push and PR. See
[`tests/README.md`](tests/README.md) for how to run them locally.

---

## v0.4.0 — Data quality, hybrid coverage, non-blocking setup (2026-06-11)

### Summary

Addresses the open beta feedback at
[issues #1–#6](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues): the
integration now filters portal sentinel values (e.g. uint32-max mileage),
discovers new entities as fields appear without a reload, sets up immediately
without blocking on the first portal dataset, and adds curated entities for
PHEV/hybrid vehicles like the Cupra Formentor.

### Sentinel values are no longer recorded
[issue #4](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/4),
[issue #6](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/6)

Some portal fields use out-of-band integer sentinels to mean "no reading"
(`4294967295` mileage, `65535` charging time left, `-1` charging time). These
spikes used to land in long-term history. They are now dropped before the
sticky/last-known-value layer: the entity keeps showing the last good value
instead of recording the garbage one.

Filtered globally for all numeric fields:

- `65535` (uint16 max)
- `2147483647` (int32 max)
- `4294967295` (uint32 max)

Filtered for known fields where `-1` cannot be valid:

- `remaining_charging_time` (flat) and `remaining_charging_time_*` (dotted)
- `remaining_charging_time_target_soc`

### New entities appear without a reload
[issue #3](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/3)

The platform setup previously created entities **once** from the first
dataset, so fields that appeared in later refreshes never got an entity
without a reload. A coordinator listener now compares the present fields
on every refresh and adds the missing curated/raw entities incrementally.

### Non-blocking setup with status sensor
[issue #1](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/1)

`async_setup_entry` no longer blocks on the first portal dataset. The entry
loads immediately with a device that has a single diagnostic sensor:

- **Integration status** — values: `starting`, `waiting_for_portal_data`,
  `empty_snapshots`, `ok`. Attributes include `empty_snapshot_count` and
  `latest_dataset_captured_at`.

Dataset-derived entities appear via the discovery listener as soon as the
first real ZIP is downloaded (typically 15–60 minutes after subscribing).

### Cupra Formentor Hybrid / PHEV coverage
[issue #2](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/2)

Flat-format PHEV vehicles previously landed in disabled raw diagnostics
because the curated registry was BEV-focused. Added:

| Field | Entity |
|-------|--------|
| `state_of_charge` | Battery (%) |
| `remaining_charging_time` | Remaining charging time (min) |

### Electric trip-statistics consumption
[issue #5](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/5)

The dictionary lists `long_term_data_average_electr_engine_consumption` and
its short-term sibling with unit `kwH/1000km`. New curated entities convert
this to standard `kWh/100km` (mirrors the fuel-consumption transform):

| Field | Entity |
|-------|--------|
| `long_term_data_average_electr_engine_consumption` | Avg electric consumption (long) |
| `short_term_data_average_electr_engine_consumption` | Avg electric consumption (short) |

### Technical changes

- `data.is_sentinel(value, field_name)` and `entity.EudaEntity._filtered()`
  share a single sentinel policy across curated and raw sensors
- `coordinator.status_label` + `empty_snapshot_count` track what the diagnostic
  sensor surfaces
- `EudaCoordinator.async_add_listener` is now used by both platforms for
  incremental entity discovery; format detection is pinned after the first
  non-empty refresh
- `electr_consumption_kwh_per_1000km_to_kwh_per_100km()` transform mirrors
  the fuel-consumption one

### Upgrade notes

- Reload the integration or restart Home Assistant after updating
- A new `Integration status` diagnostic sensor will appear on every vehicle
- Previously-broken mileage history entries (uint32-max spikes) are still
  in the recorder DB; they can be removed with the developer-tools state-history
  cleanup if desired

---

## v0.3.0 — ID.x sensors & clearer setup messages (2026-06-11)

### Summary

Expands curated entity coverage for ID.x/MEB vehicles (Cupra, Škoda Enyaq, VW ID.,
Audi, etc.) and improves the experience while waiting for the first portal dataset.
Setup no longer shows a cryptic English-only message — users get a detailed,
translated explanation that login succeeded and what to check on the portal.

Addresses common beta feedback such as
[issue #1](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues/1) (integration
stuck waiting for first data with an Enyaq).

### New curated sensors (ID.x / dotted datasets)

| Field | Entity |
|-------|--------|
| `outdoor_temperature` | Outside temperature (°C) |
| `energy_contents.current_energy_content.physical_value` | Battery energy (kWh) |
| `energy_contents.maximal_energy_content.physical_value` | Battery capacity (kWh) |
| `battery_care_mode.charge_bcam_threshold` | BCAM charge threshold (%) |
| `charging_state_report.error_code` | Charging error code |
| `additional_consumptions.residual_consumption` | Residual consumption |
| `additional_consumptions.interior_climatization_consumption` | Climate consumption |
| `slope_consumption_values.ascent_slope_consumption.physical_value` | Uphill consumption |
| `slope_consumption_values.descent_slope_consumption.physical_value` | Downhill consumption |
| `settings.auto_unlock_ac` | Auto unlock AC |
| `setting.bcam_activation` | BCAM activation |
| `profile_state_report.next_charging_timer_information.target_reachability` | Charging timer reachability |
| `value` (normalized) | Electric range (km) |

Energy content values are converted from deci-kWh (portal format, e.g. `496` → `49.6 kWh`).

### New binary sensors (ID.x)

- `parking_light_left` / `parking_light_right`
- All seven `charge_mode_selection_options.*` flags (immediate charging, timer
  charging, home storage, etc.)

### Clearer “waiting for portal data” messages

Three distinct, **translated** `ConfigEntryNotReady` messages replace the old
generic English string:

1. **`waiting_for_portal_data`** — no real ZIPs yet
2. **`waiting_for_portal_data_empty_snapshots`** — only `_no_content_found` files
   (subscription active, car sent no telemetry yet)
3. **`delivery_not_ready`** — HTTP 400, backend not ready after new subscription

Each message explains that **login succeeded**, lists portal checklist items,
mentions typical wait times, and tells users **not to remove and re-add** the
integration (HA retries automatically).

### Translations

Exception messages and existing config-flow strings are now available in:

- English (`en`)
- German (`de`)
- French (`fr`)
- Italian (`it`)
- Dutch (`nl`)

Other UI languages fall back to English.

### Technical changes

- `normalize_field_name()` maps generic portal `value` fields to
  `value_of_the_primary_range` when the dictionary description indicates primary range
- `deci_kwh_to_kwh()` transform for `energy_contents.*.physical_value`
- `EudaUpdateNotReady` exception maps coordinator state to HA translation keys

### Upgrade notes

- Reload the integration or restart Home Assistant after updating
- New entities appear automatically when the corresponding fields are present in
  portal datasets; no reconfiguration required
- Existing installs waiting for first data will show the new messages on the next
  setup retry

### Tester checklist

```bash
.venv/bin/python tests/test_offline.py
.venv/bin/python tools/test_login.py --brand skoda you@example.com 'secret'
```

| `test_login.py` exit | Meaning |
|----------------------|---------|
| `0` | End-to-end OK with real data |
| `2` | Login OK, waiting for portal ZIPs (new messages explain this) |
| `1` | Error — check brand and credentials |

---

## v0.2.0 — Multi-brand support (2026-06-10)

### Summary

All major VW Group brands on the EU Data Act portal are now supported in one
integration. Select your brand during setup — OIDC login uses the correct
`client_id` and state for each marque.

### Supported brands

- Volkswagen (passenger cars)
- Volkswagen Commercial Vehicles
- Audi
- Škoda
- SEAT
- Cupra
- Bentley

### Changes

- Brand selector in config flow (`CONF_BRAND` stored per vehicle)
- `brands.py` registry with per-brand OIDC parameters (from evcc / ioBroker, MIT)
- Device `manufacturer` reflects selected brand
- `tools/test_login.py --brand <slug>` and `--list-brands` for testers
- [TESTING.md](TESTING.md) guide for beta testers
- Display name renamed to **VW Group EU Data Act** (domain `cupra_eu_data_act` unchanged for compatibility)

### Upgrade notes

- Existing Cupra installs without `brand` in config default to **Cupra**
- Re-add the integration to change brand, or edit `core.config_entries` manually

### Tester checklist

```bash
.venv/bin/python tools/test_login.py --list-brands
.venv/bin/python tools/test_login.py --brand <your-brand> email password
```

Report results via GitHub issues — see [TESTING.md](TESTING.md).

---

## v0.1.2 — Initial public beta (2026-06-10)

First public release of the Cupra EU Data Act Home Assistant integration.

### Summary

This integration connects Home Assistant to the official Volkswagen Group EU Data
Act portal for Cupra vehicles. It provides read-only sensors (battery, charging,
range, mileage, lock state, and more) with roughly 15-minute update intervals.

### What's included

- **Config flow** — sign in with Cupra ID, select vehicle, automatic identifier detection
- **Curated sensors** — battery SoC, target SoC, charge power/rate, range, mileage,
  charge state/mode, temperatures, last-connected timestamp, and more
- **Binary sensors** — vehicle locked, parking brake
- **Diagnostic sensors** — optional raw data points from the official VW data dictionary
- **Adaptive polling** — refresh interval aligned with portal dataset delivery (~15 min)
- **German translations** — config flow strings in `de.json`
- **Offline test suite** — parsing, ZIP extraction, login HTML helpers, API response handling
- **CI workflow** — GitHub Actions runs tests on push and pull requests
- **Smoke-test tool** — `tools/test_login.py` for live portal verification outside HA

### Setup behaviour

- On first load, if no dataset with real content is available yet, the integration
  raises `ConfigEntryNotReady` and retries automatically instead of failing with a
  permanent setup error.
- HTTP **404** on the dataset list endpoint (no ZIPs delivered yet) is treated as
  an empty list.
- **`_no_content_found.zip`** files (empty portal snapshots) are skipped; the
  integration waits for the next interval.
- If the portal subscription is recreated, the data-request **identifier** is
  refreshed automatically from the metadata endpoint.

### Portal requirements

Users must configure a **continuous 15-minute data request** on
[eu-data-act.drivesomethinggreater.com](https://eu-data-act.drivesomethinggreater.com/)
before adding the integration in Home Assistant.

### Known limitations

- **Read-only** — no climate control, charging commands, or other vehicle actions
- **~15 minute latency** — not suitable for real-time automations
- **Portal dependency** — if the VW portal delivers only empty snapshots, no sensors
  will appear until real telemetry is available; this is outside the integration's control
- **Beta quality** — tested with real portal login and dataset listing; community
  feedback on different Cupra models is welcome

### Verifying your installation

```bash
# Offline (no credentials)
.venv/bin/python tests/test_offline.py
.venv/bin/python tests/test_api_mock.py

# Live portal check
EUDA_EMAIL='you@example.com' EUDA_PASSWORD='secret' .venv/bin/python tools/test_login.py
```

| `test_login.py` exit code | Interpretation |
|---------------------------|----------------|
| `0` | Working — real vehicle data downloaded |
| `2` | Working — waiting for portal to deliver data |
| `1` | Error — check credentials or portal status |

### Installation

**HACS:** Add `https://github.com/TommiG1/HA_VAG-EU-Data-Act` as a custom
integration repository, install **Cupra EU Data Act**, restart Home Assistant.

**Manual:** Copy `custom_components/cupra_eu_data_act` to your `config/custom_components/`
folder and restart.

### Requirements

- Home Assistant 2024.12.0+
- Cupra ID account with an active EU Data Act data subscription

### Credits

Derived from [hass-vw-eu-data-act](https://github.com/mikrohard/hass-vw-eu-data-act)
(MIT) by Jernej Fijačko, adapted for Cupra OIDC and branding.

API behaviour informed by MIT-licensed projects [evcc](https://github.com/evcc-io/evcc)
and [ioBroker.vw-connect](https://github.com/TA2k/ioBroker.vw-connect).

---

## Upgrade notes

This is the first release. No upgrade path from a previous version.
