"""Offline tests for the HA-independent core (data.py + api.py helpers).

Loads the integration's pure modules without importing Home Assistant by
constructing a minimal `cupra_eu_data_act` package namespace and loading the
submodules that have no HA dependency.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from _loader import FIXTURES, load_modules  # noqa: E402


def main() -> int:
    mods = load_modules("const", "data", "api")
    const = mods["const"]
    data = mods["data"]
    api = mods["api"]
    failures: list[str] = []

    def check(label, got, want):
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {got!r}" + ("" if ok else f" (want {want!r})"))
        if not ok:
            failures.append(label)

    # --- value parsing ----------------------------------------------------
    print("value parsing:")
    check("int", data.parse_value("116803", "int"), 116803)
    check("float", data.parse_value("0.0", "float"), 0.0)
    check("bool true", data.parse_value("true", "boolean"), True)
    check("bool false", data.parse_value("false"), False)
    check("duration 0s", data.parse_value("0s"), 0.0)
    check("duration 1800s", data.parse_value("1800s"), 1800.0)
    check("enum stays str", data.parse_value("WINDOW_HEATING_STATE_OFF"), "WINDOW_HEATING_STATE_OFF")
    check("empty -> None", data.parse_value(""), None)

    # --- dictionary -------------------------------------------------------
    print("data dictionary:")
    dd = data.load_dictionary()
    check("dict non-empty", len(dd) > 1000, True)
    check(
        "remaining_climate_time name",
        dd.get("3c19831c-38b8-3dc5-9ead-bb333616d925", {}).get("name"),
        "remaining_climate_time",
    )

    # --- Terramar / PHEV flat field aliases (#18) -------------------------
    print("Terramar field aliases (#18):")
    check(
        "climatisation alias",
        data.normalize_field_name("remaining_climatisation_time", None),
        "remaining_climate_time",
    )
    check(
        "plug1 connection alias",
        data.normalize_field_name("charging_plug1_connectionstate", None),
        "plug_state",
    )
    check("charging_power curated flat", "charging_power" in data.CURATED_FIELDS, True)
    terramar = data.Dataset.from_json(
        {
            "vin": "V",
            "Data": [
                {
                    "key": "rc",
                    "dataFieldName": "remaining_climatisation_time",
                    "value": "0",
                },
                {
                    "key": "plug",
                    "dataFieldName": "charging_plug1_connectionstate",
                    "value": "disconnected",
                },
                {"key": "cp", "dataFieldName": "charging_power", "value": "0"},
            ],
        }
    )
    check(
        "climatisation normalised in dataset",
        data.find_by_field(terramar.points, "remaining_climate_time") is not None,
        True,
    )
    check(
        "plug normalised in dataset",
        data.find_by_field(terramar.points, "plug_state") is not None,
        True,
    )
    flat_climate = next(
        s for s in data.CURATED_SENSORS_FLAT if s.field_name == "remaining_climate_time"
    )
    check("flat climate time unit = minutes (issue #18)", flat_climate.unit, "min")
    check("flat climate time has no duration transform", flat_climate.transform, None)
    dotted_climate = next(
        s for s in data.CURATED_SENSORS_DOTTED if s.field_name == "remaining_climate_time"
    )
    check("dotted climate time unit = seconds", dotted_climate.unit, "s")
    check(
        "charging_power in dataset",
        data.find_by_field(terramar.points, "charging_power").value,
        0,
    )
    terramar_12v = data.Dataset.from_json(
        {
            "vin": "V",
            "Data": [
                {
                    "key": "bnv",
                    "dataFieldName": "boardnetBatteryVoltageIndication",
                    "value": "12.85",
                },
            ],
        }
    )
    check(
        "boardnetBatteryVoltageIndication curated flat",
        "boardnetBatteryVoltageIndication" in data.CURATED_FIELDS,
        True,
    )
    check(
        "12V boardnet voltage value",
        data.find_by_field(terramar_12v.points, "boardnetBatteryVoltageIndication").value,
        12.85,
    )

    # --- dataset (committed fixture) --------------------------------------
    print("sample dataset:")
    sample_path = FIXTURES / "sample_dataset.json"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    ds = data.Dataset.from_json(sample)
    check("vin", ds.vin, "WVWZZZTESTVIN0001")
    check("soc", _field_val(ds, "battery_state_report.soc"), 69)
    check("mileage", _field_val(ds, "mileage.value"), 116803)
    check("target_soc", _field_val(ds, "settings.target_soc"), 80)
    check("charge_power", _field_val(ds, "battery_state_report.charge_power"), 0.0)
    check("min_temperature", _field_val(ds, "min_temperature"), 19.5)
    check("locked", _field_val(ds, "locked"), True)
    check("parking_brake", _field_val(ds, "parking_brake"), True)
    check("remaining_climate_time", _field_val(ds, "remaining_climate_time"), 0.0)
    check("range", _field_val(ds, "range.value"), 312)
    check("captured_at present", ds.captured_at is not None, True)
    ict = data.parse_timestamp(_field_val(ds, "instrument_cluster_time"))
    check("instrument_cluster_time parses", ict is not None and ict.year == 2026, True)

    # --- timestamp parsing ------------------------------------------------
    print("timestamp parsing:")
    cct = data.parse_timestamp("2026-05-29T22:59:27Z")
    check("iso Z", cct is not None and cct.tzinfo is not None, True)
    check("iso offset", data.parse_timestamp("2026-05-29T22:59:27+02:00") is not None, True)

    # --- duplicate field: latest array occurrence wins without timestamps ---
    print("duplicate field selection:")
    ds_d = data.Dataset.from_json(
        {
            "vin": "V",
            "user_id": "u",
            "Data": [
                {"key": "aaa", "dataFieldName": "charging_state_report.current_charge_state", "value": "A"},
                {"key": "bbb", "dataFieldName": "charging_state_report.current_charge_state", "value": "B"},
            ],
        }
    )
    check("last duplicate wins", _field_val(ds_d, "charging_state_report.current_charge_state"), "B")

    # --- curated / raw classification ------------------------------------
    print("curated registry:")
    check("soc is curated", "battery_state_report.soc" in data.CURATED_FIELDS, True)
    check("locked is curated", "locked" in data.CURATED_FIELDS, True)
    check(
        "flat state_of_charge curated (PHEV)",
        "state_of_charge" in data.CURATED_FIELDS,
        True,
    )
    check(
        "flat remaining_charging_time curated",
        "remaining_charging_time" in data.CURATED_FIELDS,
        True,
    )
    check(
        "flat electr consumption curated",
        "long_term_data_average_electr_engine_consumption" in data.CURATED_FIELDS,
        True,
    )
    check(
        "flat charged_energy curated",
        "charged_energy" in data.CURATED_FIELDS,
        True,
    )
    check(
        "car_captured_time not curated (P6)",
        "car_captured_time" in data.CURATED_FIELDS,
        False,
    )
    check(
        "instrument_cluster_time curated",
        "instrument_cluster_time" in data.CURATED_FIELDS,
        True,
    )
    print("raw metadata field blocklist:")
    check("report_type is metadata", data.is_raw_metadata_field("report_type"), True)
    check("message_id is metadata", data.is_raw_metadata_field("message_id"), True)
    check("bare timestamp is metadata", data.is_raw_metadata_field("timestamp"), True)
    check(
        "mileage.value.timestamp is not metadata",
        data.is_raw_metadata_field("mileage.value.timestamp"),
        False,
    )
    check(
        "dotted car_captured_time is metadata",
        data.is_raw_metadata_field("profile_state_report.car_captured_time"),
        True,
    )
    check("soc is not metadata", data.is_raw_metadata_field("battery_state_report.soc"), False)
    check(
        "instrument_cluster_time is not metadata",
        data.is_raw_metadata_field("instrument_cluster_time"),
        False,
    )
    print("cupra dotted extras curated:")
    check(
        "profile ict curated",
        "profile_state_report.instrument_cluster_time" in data.CURATED_FIELDS,
        True,
    )
    check(
        "hv battery level curated",
        "battery_level_HV.value" in data.CURATED_FIELDS,
        True,
    )
    check(
        "open binary curated",
        "open" in {b.field_name for b in data.CURATED_BINARY_DOTTED},
        True,
    )
    check("open bool decode", data.decode_binary_state(True, encoding="onoff"), True)
    extras_ds = data.Dataset.from_json(
        json.loads((FIXTURES / "cupra_dotted_uncurated_sample.json").read_text())
    )
    extras_cov = data.field_coverage(extras_ds.points)
    check("extras fixture fully curated", extras_cov["uncurated_count"], 0)
    _charge_state = next(
        s
        for s in data.CURATED_SENSORS_DOTTED
        if s.field_name == "charging_state_report.current_charge_state"
    )
    check("charge_state has translation_key", _charge_state.translation_key, "charge_state")
    check(
        "curated_translation_key derived",
        data.curated_translation_key("mileage.value"),
        "mileage_value",
    )
    check(
        "curated_translation_key keeps short key",
        data.curated_translation_key(
            "charging_state_report.current_charge_state", "charge_state"
        ),
        "charge_state",
    )
    _charged = next(s for s in data.CURATED_SENSORS_FLAT if s.field_name == "charged_energy")
    check("charged_energy total_increasing", _charged.state_class, "total_increasing")
    check("charged_energy device_class energy", _charged.device_class, "energy")
    _last_charge = next(
        s for s in data.CURATED_SENSORS_DOTTED if s.field_name == "last_charge_kwh"
    )
    check("last_charge has translation_key", _last_charge.translation_key, "last_charge_kwh")
    check(
        "last_charge no invalid energy+measurement",
        _last_charge.device_class is None and _last_charge.state_class == "measurement",
        True,
    )
    _batt_energy = next(
        s
        for s in data.CURATED_SENSORS_DOTTED
        if s.field_name == "energy_contents.current_energy_content.physical_value"
    )
    check(
        "battery energy no invalid energy+measurement",
        _batt_energy.device_class is None and _batt_energy.state_class == "measurement",
        True,
    )
    _mintemp = next(s for s in data.CURATED_SENSORS_DOTTED if s.field_name == "min_temperature")
    check("min_temperature named battery", _mintemp.name, "Battery min temperature")
    format_type = data.detect_dataset_format(ds.points)
    check("fixture format dotted", format_type, "dotted")
    curated_present = {dp.field_name for dp in ds.points.values()} & data.CURATED_FIELDS
    check("fixture has curated fields", len(curated_present) >= 5, True)
    coverage = data.field_coverage(ds.points)
    check("field_coverage counts", coverage["field_count"] == len(ds.points), True)
    check("field_coverage curated subset", coverage["curated_count"] == len(curated_present), True)

    # --- consumption transforms ------------------------------------------
    print("consumption transforms:")
    check(
        "fuel L/1000km -> L/100km",
        data.fuel_consumption_l_per_1000km_to_l_per_100km(168),
        16.8,
    )
    check(
        "electr kWh/1000km -> kWh/100km",
        data.electr_consumption_kwh_per_1000km_to_kwh_per_100km(180),
        18.0,
    )
    check(
        "distance 100m -> km (issue #33)",
        data.hectometers_to_km(160),
        16.0,
    )
    check(
        "issue #33 curated distance fields registered",
        "short_term_data_zero_emission_distance" in data.CURATED_FIELDS,
        True,
    )
    check(
        "issue #33 required tyre pressure registered",
        "tyre_pressure_required_front_left" in data.CURATED_FIELDS,
        True,
    )

    # --- raw unique_id namespaced by VIN (multi-vehicle) ----------------
    print("raw unique_id namespacing:")
    key = "1763a4fe-d8a6-3b8c-b095-70081f3e61c7"
    check("vin-prefixed", const.raw_unique_id("VINA", key), f"VINA_{key}")
    check("distinct per vehicle", const.raw_unique_id("VINA", key) != const.raw_unique_id("VINB", key), True)

    # --- sticky values ----------------------------------------------------
    print("sticky values:")
    check("fresh value kept", data.sticky(50, 55), 55)
    check("missing -> previous retained", data.sticky(55, None), 55)
    check("zero is not missing", data.sticky(55, 0), 0)
    check("false is not missing", data.sticky(True, False), False)

    # --- merge_data_points / find_by_field preference ---------------------
    print("merge_data_points:")
    good = data.DataPoint(
        key="aaaa",
        field_name="battery",
        raw_value="72",
    )
    bad = data.DataPoint(
        key="aaaa",
        field_name="battery",
        raw_value="4294967295",
    )
    merged = data.merge_data_points({"aaaa": good}, {"aaaa": bad})
    check("sentinel does not overwrite good key", merged["aaaa"].value, 72)
    merged2 = data.merge_data_points(
        {"aaaa": good},
        {"bbbb": data.DataPoint(key="bbbb", field_name="mileage", raw_value="100")},
    )
    check("new usable key added", merged2["bbbb"].value, 100)
    check("old key retained", merged2["aaaa"].value, 72)
    print("find_by_field prefers usable reading:")
    points = {
        "bad": data.DataPoint(
            key="bad",
            field_name="mileage",
            raw_value="4294967295",
        ),
        "good": data.DataPoint(
            key="good",
            field_name="mileage",
            raw_value="20717",
        ),
    }
    check(
        "usable mileage wins over sentinel",
        data.find_by_field(points, "mileage").value,
        20717,
    )

    # --- P5: timestamp-aware find_by_field & merge (issue #24) ------------
    print("timestamp-aware find_by_field:")
    dated = {
        "old": data.DataPoint(
            key="aaa",
            field_name="mileage",
            raw_value="100",
            timestamp_utc="2026-01-01T10:00:00Z",
        ),
        "new": data.DataPoint(
            key="zzz",
            field_name="mileage",
            raw_value="120",
            timestamp_utc="2026-01-02T10:00:00Z",
        ),
    }
    check(
        "freshest duplicate wins over min(key)",
        data.find_by_field(dated, "mileage").value,
        120,
    )
    no_ts = {
        "ccc": data.DataPoint("ccc", "mileage", "3", sequence=0),
        "aaa": data.DataPoint("aaa", "mileage", "1", sequence=1),
    }
    check(
        "no timestamps -> latest sequence",
        data.find_by_field(no_ts, "mileage").value,
        1,
    )

    print("merge_data_points freshness guard:")
    cur = data.DataPoint(
        key="k", field_name="mileage", raw_value="120",
        timestamp_utc="2026-01-02T10:00:00Z",
    )
    older = data.DataPoint(
        key="k", field_name="mileage", raw_value="100",
        timestamp_utc="2026-01-01T10:00:00Z",
    )
    newer = data.DataPoint(
        key="k", field_name="mileage", raw_value="130",
        timestamp_utc="2026-01-03T10:00:00Z",
    )
    check(
        "older fallback does not regress mileage",
        data.merge_data_points({"k": cur}, {"k": older})["k"].value,
        120,
    )
    check(
        "fresher snapshot updates mileage",
        data.merge_data_points({"k": cur}, {"k": newer})["k"].value,
        130,
    )

    # Value fields (soc, mileage) carry no per-item timestampUtc, so their
    # freshness must come from the dataset's car_captured_time stamped by
    # from_json. Without it the guards above are no-ops for exactly these
    # fields and soc oscillates / mileage regresses on a fallback download.
    print("value-field freshness from dataset captured_at:")

    def _soc_dataset(soc_value, soc_key, car_captured_time):
        return data.Dataset.from_json(
            {
                "vin": "V",
                "Data": [
                    {
                        "key": soc_key,
                        "dataFieldName": "battery_state_report.soc",
                        "value": soc_value,
                    },
                    {
                        "key": "cct",
                        "dataFieldName": "car_captured_time",
                        "value": car_captured_time,
                    },
                ],
            }
        )

    newer_ds = _soc_dataset("61", "soc", "2026-01-02T10:00:00Z")
    older_ds = _soc_dataset("55", "soc", "2026-01-01T10:00:00Z")
    check(
        "from_json stamps captured_at on value point",
        newer_ds.points["soc"].captured_at is not None,
        True,
    )
    # Same UUID key: an older fallback dataset must not regress soc.
    guarded = data.merge_data_points(dict(newer_ds.points), dict(older_ds.points))
    check(
        "older fallback does not regress soc (no per-item ts)",
        data.find_by_field(guarded, "battery_state_report.soc").value,
        61,
    )
    # Distinct UUID keys lingering in the merged store: the fresher dataset's
    # reading wins instead of an arbitrary array position.
    lingering = {
        "soc-old": _soc_dataset("55", "soc-old", "2026-01-01T10:00:00Z").points[
            "soc-old"
        ],
        "soc-new": _soc_dataset("61", "soc-new", "2026-01-02T10:00:00Z").points[
            "soc-new"
        ],
    }
    check(
        "fresher dataset's soc wins among lingering keys",
        data.find_by_field(lingering, "battery_state_report.soc").value,
        61,
    )

    print("datapoint_freshness_attributes:")
    from datetime import datetime, timezone

    soc_dp = newer_ds.points["soc"]
    attrs = data.datapoint_freshness_attributes(
        soc_dp,
        now=datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc),
    )
    check(
        "soc uses report_captured_time source",
        attrs.get("freshness_source"),
        "report_captured_time",
    )
    check(
        "soc age_minutes from captured_at",
        attrs.get("age_minutes"),
        120,
    )
    mileage_dp = data.DataPoint(
        key="k",
        field_name="mileage",
        raw_value="120",
        timestamp_utc="2026-01-02T10:00:00Z",
    )
    check(
        "timestampUtc source",
        data.datapoint_freshness_attributes(mileage_dp).get("freshness_source"),
        "timestamp_utc",
    )
    check(
        "missing point -> no attrs",
        data.datapoint_freshness_attributes(None),
        {},
    )
    zip_name = "WVWZZZTESTVIN0001_20260102000000.zip"
    stamped = data.stamp_source_dataset(
        {"k": data.DataPoint(key="k", field_name="mileage", raw_value="100")},
        zip_name,
    )
    check(
        "source_dataset attribute (issue #31)",
        data.datapoint_freshness_attributes(stamped["k"]).get("source_dataset"),
        zip_name,
    )

    # Monotonic fields (the odometer): one dataset can carry two mileage.value
    # slots from report snapshots that lag each other. The freshest/last-in-ZIP
    # default would pick the lower one; prefer_max_value picks the truest (max).
    print("monotonic odometer prefers the highest duplicate slot:")
    dual = data.Dataset.from_json(
        {
            "vin": "V",
            "Data": [
                {"key": "m-hi", "dataFieldName": "mileage.value", "value": "70908"},
                {"key": "m-lo", "dataFieldName": "mileage.value", "value": "70876"},
                {
                    "key": "cct",
                    "dataFieldName": "car_captured_time",
                    "value": "2026-01-02T10:00:00Z",
                },
            ],
        }
    )
    check(
        "default picks last-in-ZIP slot",
        data.find_by_field(dual.points, "mileage.value").value,
        70876,
    )
    check(
        "prefer_max_value picks highest slot",
        data.find_by_field(
            dual.points, "mileage.value", prefer_max_value=True
        ).value,
        70908,
    )
    check(
        "mileage curated sensor is flagged monotonic",
        any(
            c.field_name == "mileage.value" and c.monotonic
            for c in data.CURATED_SENSORS_DOTTED
        ),
        True,
    )

    print("last_connected_time:")
    sample = json.loads(
        (Path(__file__).parent / "fixtures" / "sample_dataset.json").read_text()
    )
    ds = data.Dataset.from_json(sample)
    ts = data.last_connected_time(ds.points)
    check("falls back to car_captured_time", ts is not None, True)
    check(
        "uses car_captured_time value",
        ts.isoformat().startswith("2026-05-29"),
        True,
    )

    # --- sentinel detection -----------------------------------------------
    print("sentinel detection:")
    check("uint32 max mileage", data.is_sentinel(4294967295, "mileage"), True)
    check("uint32 max mileage.value", data.is_sentinel(4294967295, "mileage.value"), True)
    check("uint16 max charging time", data.is_sentinel(65535, "remaining_charging_time"), True)
    check(
        "uint16 max dotted charging time",
        data.is_sentinel(65535, "battery_state_report.remaining_charging_time_complete"),
        True,
    )
    check(
        "-1 charging time (field-specific)",
        data.is_sentinel(-1, "remaining_charging_time"),
        True,
    )
    check(
        "-1 mileage NOT sentinel (might be valid)",
        data.is_sentinel(-1, "mileage"),
        False,
    )
    check("normal mileage 116803", data.is_sentinel(116803, "mileage"), False)
    check("zero is not sentinel", data.is_sentinel(0, "remaining_charging_time"), False)
    check("None is not sentinel", data.is_sentinel(None, "mileage"), False)
    check("string is not sentinel", data.is_sentinel("FOO", "state"), False)
    check("boolean True not sentinel", data.is_sentinel(True, "locked"), False)
    check(
        "uint32 max without field name",
        data.is_sentinel(4294967295),
        True,
    )
    check(
        "int32 max without field name",
        data.is_sentinel(2147483647),
        True,
    )
    check(
        "tyre pressure 1 = invalid (issue #14)",
        data.is_sentinel(1, "tyre_pressure_actual_front_left"),
        True,
    )
    check(
        "tyre pressure 0 = unsupported",
        data.is_sentinel(0, "tyre_pressure_actual_front_right"),
        True,
    )
    check(
        "tyre pressure 24 bar plausible",
        data.is_sentinel(24, "tyre_pressure_actual_front_left"),
        False,
    )
    check(
        "required tyre pressure 1 bar plausible (issue #33)",
        data.is_sentinel(1, "tyre_pressure_required_front_left"),
        False,
    )
    check(
        "tyre pressure 1 not sentinel without field name",
        data.is_sentinel(1),
        False,
    )

    # --- binary decoding --------------------------------------------------
    print("binary decoding:")
    check("open 2 -> True (door open)", data.decode_binary_state(2, "open"), True)
    check("open 3 -> False (door closed)", data.decode_binary_state(3, "open"), False)
    check("open 0 -> None (unsupported)", data.decode_binary_state(0, "open"), None)
    check("open 1 -> None (invalid)", data.decode_binary_state(1, "open"), None)
    check(
        "open invert 2 -> False (locked sensor on)",
        data.decode_binary_state(2, "open", invert=True),
        False,
    )
    check(
        "open invert 3 -> True (locked sensor off)",
        data.decode_binary_state(3, "open", invert=True),
        True,
    )
    check("onoff 0 -> False", data.decode_binary_state(0, "onoff"), False)
    check("onoff 1 -> True", data.decode_binary_state(1, "onoff"), True)
    check(
        "lights 0/1 -> None",
        (data.decode_binary_state(0, "lights"), data.decode_binary_state(1, "lights")),
        (None, None),
    )
    check("lights 2 -> False (off)", data.decode_binary_state(2, "lights"), False)
    check("lights 3 -> True (left)", data.decode_binary_state(3, "lights"), True)
    check("lights 4 -> True (right)", data.decode_binary_state(4, "lights"), True)
    check("lights 5 -> True (both)", data.decode_binary_state(5, "lights"), True)
    check("bool True passthrough", data.decode_binary_state(True), True)
    check(
        "bool False passthrough w/ invert",
        data.decode_binary_state(False, invert=True),
        True,
    )
    check("string -> None", data.decode_binary_state("OFF"), None)
    check("None -> None", data.decode_binary_state(None), None)
    check(
        "string_onoff on -> True",
        data.decode_binary_state("on", encoding="string_onoff"),
        True,
    )
    check(
        "string_onoff off -> False",
        data.decode_binary_state("OFF", encoding="string_onoff"),
        False,
    )
    check(
        "plug connected -> True",
        data.decode_binary_state("connected", encoding="plug"),
        True,
    )
    check(
        "plug disconnected -> False",
        data.decode_binary_state("disconnected", encoding="plug"),
        False,
    )
    check(
        "string_lock locked -> True",
        data.decode_binary_state("locked", encoding="string_lock"),
        True,
    )
    check(
        "string_lock unlocked -> False",
        data.decode_binary_state("unlocked", encoding="string_lock"),
        False,
    )
    check(
        "PHEV flat binary fields registered",
        {
            "window_heating_state_front",
            "plug_state",
            "lock_state",
        }.issubset({b.field_name for b in data.CURATED_BINARY_FLAT}),
        True,
    )
    check(
        "PHEV flat enum sensors registered",
        {
            "charging_state",
            "charging_mode",
            "charging_reason_trigger",
        }.issubset({s.field_name for s in data.CURATED_SENSORS_FLAT}),
        True,
    )

    # --- enum label shortening -------------------------------------------
    print("enum label shortening:")
    check(
        "charge state prefix stripped",
        data.shorten_enum_label(
            "charging_state_report.current_charge_state",
            "CHARGE_STATE_CHARGING_HV_BATTERY",
        ),
        "CHARGING_HV_BATTERY",
    )
    check(
        "non-enum passthrough",
        data.shorten_enum_label("mileage.value", "12345"),
        "12345",
    )
    check(
        "charge mode prefix shortened",
        data.shorten_enum_label("charge_mode", "CHARGE_MODE_INVALID"),
        "INVALID",
    )
    check(
        "no matching prefix unchanged",
        data.shorten_enum_label("battery_state_report.soc", "CHARGE_MODE_INVALID"),
        "CHARGE_MODE_INVALID",
    )

    # --- latest captured time --------------------------------------------
    print("latest captured time:")
    from datetime import datetime, timezone

    ts_old = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    ts_new = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    points = {
        "a": data.DataPoint(
            key="a",
            field_name="car_captured_time",
            raw_value=ts_old.isoformat(),
        ),
        "b": data.DataPoint(
            key="b",
            field_name="profile_state_report.car_captured_time",
            raw_value=ts_new.isoformat(),
        ),
    }
    check("max across captured fields", data.latest_captured_time(points), ts_new)
    check("empty dataset", data.latest_captured_time({}), None)

    # --- ApiError carries HTTP status ------------------------------------
    print("api error status:")
    err500 = api.ApiError("GET x -> HTTP 500", status=500)
    err_no = api.ApiError("Connection broken")
    check("status preserved on ApiError", err500.status, 500)
    check("status defaults to None", err_no.status, None)
    auth_err = api.AuthError("Login rejected")
    check("AuthError is ApiError", isinstance(auth_err, api.ApiError), True)
    check("AuthError default status None", auth_err.status, None)

    # --- find_by_field duplicate handling -------------------------------
    print("find_by_field:")
    points = {
        "ccc": data.DataPoint("ccc", "charging_state_report.current_charge_state", "C", sequence=0),
        "aaa": data.DataPoint("aaa", "charging_state_report.current_charge_state", "A", sequence=1),
        "bbb": data.DataPoint("bbb", "charging_state_report.current_charge_state", "B", sequence=2),
    }
    dp = data.find_by_field(points, "charging_state_report.current_charge_state")
    check("latest sequence wins", dp.key, "bbb")
    check("missing field -> None", data.find_by_field(points, "nope"), None)
    check(
        "Dataset.by_field still works",
        data.Dataset(
            vin="V", user_id=None, points=points
        ).by_field("charging_state_report.current_charge_state").key,
        "bbb",
    )

    # --- api zip helper ---------------------------------------------------
    print("api helpers:")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("WVWZZZTESTVIN0001_x.json", json.dumps(sample))
    parsed = api.EudaApiClient.parse_dataset_zip(buf.getvalue(), "x.zip")
    check("unzip vin", parsed["vin"], "WVWZZZTESTVIN0001")
    vins = api._extract_vins({"vehicles": [{"vin": "WVWZZZTESTVIN0001", "vehicleNickname": "Born"}]})
    check("extract_vins", vins, [{"vin": "WVWZZZTESTVIN0001", "nickname": "Born"}])

    # --- login field extraction -------------------------------------------
    print("login field extraction:")
    auth_page = (
        "<html><script>window._IDK = { templateModel: "
        '{"relayState":"RS","hmac":"HM","postAction":"login/authenticate",'
        '"error":null,"emailPasswordForm":{"email":"a@b.c"}}, '
        "csrf_token: 'CSRF1' }</script></html>"
    )
    f2, _ = api._login_fields(auth_page)
    check("templateModel hmac", f2.get("hmac"), "HM")
    check("templateModel _csrf", f2.get("_csrf"), "CSRF1")
    check("templateModel relayState", f2.get("relayState"), "RS")
    err_page = auth_page.replace('"error":null', '"error":{"text":"Bad creds"}')
    check("login error text", api._login_error(err_page), "Bad creds")
    email_page = (
        '<form action="/x/login/identifier"><input name=_csrf value=HC>'
        "<input name=hmac value=HH><input name=relayState value=RS><input name=email></form>"
    )
    fe, ae = api._login_fields(email_page)
    check("html-input _csrf not overridden", fe.get("_csrf"), "HC")
    check("html-input action", ae, "/x/login/identifier")

    # --- sticky unit (mirrors EudaEntity._sticky_unit) --------------------
    print("sticky unit:")

    class _StickyUnitProbe:
        """Offline stand-in for EudaEntity._sticky_unit (entity.py)."""

        def __init__(self) -> None:
            self._last_resolved_unit: str | None = None
            self._unit_confirm_count = 0
            self._pending_unit: str | None = None

        def sticky_unit(
            self, resolved: str | None, *, confirm_required: int = 2
        ) -> str | None:
            if resolved is None:
                return self._last_resolved_unit
            if resolved == self._last_resolved_unit:
                self._unit_confirm_count = 0
                self._pending_unit = None
                return self._last_resolved_unit
            if resolved == self._pending_unit:
                self._unit_confirm_count += 1
            else:
                self._pending_unit = resolved
                self._unit_confirm_count = 1
            if self._unit_confirm_count >= confirm_required:
                self._last_resolved_unit = resolved
                self._unit_confirm_count = 0
                self._pending_unit = None
            return self._last_resolved_unit

    probe = _StickyUnitProbe()
    check("none resolved -> no unit yet", probe.sticky_unit(None), None)
    check("first km/h not adopted yet", probe.sticky_unit("km/h"), None)
    check("second km/h adopted", probe.sticky_unit("km/h"), "km/h")
    check("same unit resets confirm", probe.sticky_unit("km/h"), "km/h")
    check("single mi/h flip ignored", probe.sticky_unit("mi/h"), "km/h")
    check("mi/h still pending after one", probe.sticky_unit("km/h"), "km/h")
    check("mi/h adopted after two consecutive", probe.sticky_unit("mi/h"), "km/h")
    check("mi/h adopted on second poll", probe.sticky_unit("mi/h"), "mi/h")
    check("none keeps stable unit", probe.sticky_unit(None), "mi/h")

    # --- charge rate unit resolution ----------------------------------------
    print("charge rate unit resolution:")
    check(
        "KM_PER_H -> km/h",
        data.resolve_charge_rate_unit("CHARGE_RATE_UNIT_KM_PER_H"),
        "km/h",
    )
    check(
        "MILES_PER_H -> mi/h",
        data.resolve_charge_rate_unit("CHARGE_RATE_UNIT_MILES_PER_H"),
        "mi/h",
    )
    charge_rate = next(
        s
        for s in data.CURATED_SENSORS_DOTTED
        if s.field_name == "battery_state_report.charge_rate"
    )
    check("charge_rate declares unit_field", charge_rate.unit_field, "battery_state_report.charge_rate_unit")
    check("charge_rate unit_resolver", charge_rate.unit_resolver, "charge_rate")
    check(
        "flat km_per_h -> km/h",
        data.resolve_charge_rate_unit("km_per_h"),
        "km/h",
    )
    check(
        "flat miles_per_h -> mi/h",
        data.resolve_charge_rate_unit("miles_per_h"),
        "mi/h",
    )
    check(
        "flat invalid -> None",
        data.resolve_charge_rate_unit("invalid"),
        None,
    )
    check("actual_charge_rate curated flat", "actual_charge_rate" in data.CURATED_FIELDS, True)
    flat_charge_rate = next(
        s
        for s in data.CURATED_SENSORS_FLAT
        if s.field_name == "actual_charge_rate"
    )
    check(
        "flat charge_rate declares unit_field",
        flat_charge_rate.unit_field,
        "charge_rate_unit",
    )
    check("flat charge_rate unit_resolver", flat_charge_rate.unit_resolver, "charge_rate")

    def _charge_rate_unit(
        sticky: _StickyUnitProbe, value, unit_enum, *, usable_value=True
    ):
        """Inline gate matching EudaCuratedSensor.native_unit_of_measurement."""
        value_raw = str(value) if usable_value else "4294967295"
        ds_cr = data.Dataset.from_json(
            {
                "vin": "V",
                "user_id": "u",
                "Data": [
                    {
                        "key": "r1",
                        "dataFieldName": "battery_state_report.charge_rate",
                        "value": value_raw,
                    },
                    {
                        "key": "u1",
                        "dataFieldName": "battery_state_report.charge_rate_unit",
                        "value": unit_enum,
                    },
                ],
            }
        )
        pts = ds_cr.points
        unit_dp = data.find_by_field(pts, charge_rate.unit_field)
        resolved = data.resolve_charge_rate_unit(unit_dp.value)
        value_dp = data.find_by_field(pts, charge_rate.field_name)
        consider = resolved
        if value_dp is None or not data.is_usable_reading(
            value_dp.value, charge_rate.field_name
        ):
            consider = None
        return sticky.sticky_unit(consider) or charge_rate.unit

    probe = _StickyUnitProbe()
    check(
        "usable reading + two km/h polls",
        (
            _charge_rate_unit(probe, 42, "CHARGE_RATE_UNIT_KM_PER_H"),
            _charge_rate_unit(probe, 42, "CHARGE_RATE_UNIT_KM_PER_H"),
        ),
        ("km/h", "km/h"),
    )
    probe = _StickyUnitProbe()
    check(
        "unusable value ignores unit flip",
        (
            _charge_rate_unit(probe, 0, "CHARGE_RATE_UNIT_KM_PER_H", usable_value=False),
            _charge_rate_unit(probe, 0, "CHARGE_RATE_UNIT_MILES_PER_H", usable_value=False),
        ),
        ("km/h", "km/h"),
    )
    probe = _StickyUnitProbe()
    _charge_rate_unit(probe, 10, "CHARGE_RATE_UNIT_KM_PER_H")
    check(
        "single spurious mi/h ignored when value usable",
        _charge_rate_unit(probe, 10, "CHARGE_RATE_UNIT_MILES_PER_H"),
        "km/h",
    )

    # --- distance unit resolved from companion *.unit field ----------------
    print("distance unit resolution:")
    check("MILES -> mi", data.resolve_distance_unit("MILES"), "mi")
    check("KM -> km", data.resolve_distance_unit("KM"), "km")
    check("lowercase miles -> mi", data.resolve_distance_unit("miles"), "mi")
    check("unknown -> None", data.resolve_distance_unit("LIGHTYEARS"), None)
    mileage = next(s for s in data.CURATED_SENSORS_DOTTED if s.field_name == "mileage.value")
    check("mileage declares unit_field", mileage.unit_field, "mileage.unit")
    ds_mi = data.Dataset.from_json({"vin": "V", "user_id": "u", "Data": [
        {"key": "m1", "dataFieldName": "mileage.value", "value": "43531"},
        {"key": "m2", "dataFieldName": "mileage.unit", "value": "MILES"},
    ]})
    unit_dp = ds_mi.by_field("mileage.unit")
    check("resolved unit from dataset", data.resolve_distance_unit(unit_dp.value), "mi")
    primary = next(
        s for s in data.CURATED_SENSORS_DOTTED if s.field_name == "value_of_the_primary_range"
    )
    check(
        "primary range declares unit_fields",
        primary.unit_fields,
        data.PRIMARY_RANGE_UNIT_FIELDS,
    )
    ds_range_mi = data.Dataset.from_json({"vin": "V", "user_id": "u", "Data": [
        {"key": "r1", "dataFieldName": "value", "value": "180",
         "description": "Range for the corresponding engine primary range"},
        {"key": "r2", "dataFieldName": "mileage.unit", "value": "MILES"},
    ]})
    check(
        "primary range unit from mileage.unit",
        data.resolve_primary_range_unit(ds_range_mi.points),
        "mi",
    )
    ds_range_km = data.Dataset.from_json({"vin": "V", "user_id": "u", "Data": [
        {"key": "r1", "dataFieldName": "value_of_the_primary_range", "value": "280"},
        {"key": "r2", "dataFieldName": "range.unit", "value": "KM"},
    ]})
    check(
        "primary range prefers range.unit",
        data.resolve_primary_range_unit(ds_range_km.points),
        "km",
    )
    ds_cruising = data.Dataset.from_json({"vin": "V", "user_id": "u", "Data": [
        {"key": "r1", "dataFieldName": "value_of_the_primary_range", "value": "200"},
        {"key": "r2", "dataFieldName": "battery_state_report.cruising_ranges.0.unit",
         "value": "MILES"},
    ]})
    check(
        "primary range falls back to cruising_ranges unit",
        data.resolve_primary_range_unit(ds_cruising.points),
        "mi",
    )

    # --- duplicate field ordering within one portal ZIP --------------------
    print("duplicate field ordering:")
    ds_duplicate = data.Dataset.from_json({"vin": "V", "user_id": "u", "Data": [
        {"key": "first", "dataFieldName": "battery_state_report.charge_power",
         "value": "10.0"},
        {"key": "second", "dataFieldName": "battery_state_report.charge_power",
         "value": "0.0"},
    ]})
    check(
        "last duplicate without timestamp wins",
        data.find_by_field(ds_duplicate.points, "battery_state_report.charge_power").value,
        0.0,
    )

    # --- charged-energy harmonisation across dataset formats ----------------
    print("charged-energy harmonisation:")
    dotted_energy = data.Dataset.from_json(
        {
            "vin": "V",
            "user_id": "u",
            "Data": [
                {
                    "key": "c1",
                    "dataFieldName": "battery_state_report.charge_energy",
                    "value": "12.4",
                }
            ],
        }
    )
    flat_energy = data.Dataset.from_json(
        {
            "vin": "V",
            "user_id": "u",
            "Data": [{"key": "c2", "dataFieldName": "charged_energy", "value": "124"}],
        }
    )
    check(
        "dotted charged energy -> kWh",
        data.total_charged_energy_kwh(dotted_energy.points),
        12.4,
    )
    check(
        "flat charged_energy deci-kWh -> kWh",
        data.total_charged_energy_kwh(flat_energy.points),
        12.4,
    )

    # --- friendly names for bare fields ------------------------------------
    print("friendly raw names:")
    check("bare value -> description", data.friendly_name("value", "Value of the primary range"), "Value of the primary range")
    check("dotted name kept", data.friendly_name("battery_state_report.soc", "State of charge"), "battery_state_report.soc")
    check("bare value no desc -> value", data.friendly_name("value", None), "value")

    # --- enum integer fallback ---------------------------------------------
    print("enum integer fallback:")
    enum_desc = (
        "IMMEDIATE_ACTION_STAT E_INVALID, IMMEDIATE_ACTION_STAT E_IMMEDIATE_ACTION_TI ME, "
        "IMMEDIATE_ACTION_STAT E_IMMEDIATE_CHARGING , IMMEDIATE_ACTION_STAT E_IMMEDIATE_ACTION_ST OPPED, "
        "IMMEDIATE_ACTION_STAT E_IMMEDIATE_ACTION_R ANGE, IMMEDIATE_ACTION_STAT E_IMMEDIATE_ACTION_S OC, "
        "IMMEDIATE_ACTION_STAT E_CHARGE_MODE_SELEC TION"
    )
    members = data.enum_members(enum_desc)
    check("parses 7 enum members", len(members), 7)
    dp_int = data.DataPoint("k", "charging_state_report.immediate_action_state", "6", "enum", None, enum_desc)
    check("int 6 -> label", dp_int.value, "IMMEDIATE_ACTION_STATE_CHARGE_MODE_SELECTION")
    dp_str = data.DataPoint("k", "f", "IMMEDIATE_ACTION_STATE_IMMEDIATE_CHARGING", "enum", None, enum_desc)
    check("string label unchanged", dp_str.value, "IMMEDIATE_ACTION_STATE_IMMEDIATE_CHARGING")
    dp_prose = data.DataPoint("k", "report_type", "3", "enum", None, "The enum value of report type")
    check("prose enum desc -> int kept", dp_prose.value, 3)

    print()
    if failures:
        print(f"FAILED: {len(failures)} -> {failures}")
        return 1
    print("ALL OFFLINE TESTS PASSED")
    return 0


def _field_val(ds, field_name):
    dp = ds.by_field(field_name)
    return dp.value if dp else None


if __name__ == "__main__":
    raise SystemExit(main())
