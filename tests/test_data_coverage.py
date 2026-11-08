"""Edge-case coverage for the pure data helpers."""
from __future__ import annotations

from datetime import datetime
from custom_components.cupra_eu_data_act import data
from custom_components.cupra_eu_data_act.data import CuratedSensor, DataPoint, Dataset


def test_parse_and_conversion_error_edges() -> None:
    assert data.parse_value(None) is None
    assert data.parse_value("bad", "float") == "bad"
    assert data.normalize_field_name("value", None) == "value"
    assert data.normalize_field_name("value", "The primary range.") == "value_of_the_primary_range"
    assert data.enum_members(None) == []
    assert data.shorten_enum_label("field", 1) == 1
    assert data.friendly_name("value", "   ") == "value"
    assert data._as_float("bad") is None
    assert data.resolve_distance_unit(1, "km") == "km"
    assert data.resolve_charge_rate_unit(1, "km/h") == "km/h"
    assert data.scale_charge_rate_to_per_hour(None, "KM_PER_MIN") is None
    assert data.scale_charge_rate_to_per_hour(2, 1) == 2
    assert data.scale_charge_rate_to_per_hour(2, "KM_PER_H") == 2
    assert data.scale_charge_rate_to_per_hour("bad", "KM_PER_MIN") is None
    for func in (
        data.decikelvin_to_celsius,
        data.abs_value,
        data.fuel_consumption_l_per_1000km_to_l_per_100km,
        data.electr_consumption_kwh_per_1000km_to_kwh_per_100km,
        data.hectometers_to_km,
        data.deci_kwh_to_kwh,
        data.deci_kw_to_kw,
    ):
        assert func("bad") is None


def test_timestamp_and_dataset_edge_paths() -> None:
    assert data.parse_timestamp(None) is None
    now = datetime.now()
    assert data.parse_timestamp(now) is now
    assert data.parse_timestamp("") is None
    assert data.parse_timestamp("not-a-date") is None
    assert data.parse_timestamp("999999999999999999") is None
    dataset = Dataset.from_json({"Data": [{"dataFieldName": "missing-key", "value": "1"}]})
    assert not dataset.points
    point = DataPoint("k", "x", "1", timestamp_utc="bad")
    assert point.timestamp is None
    assert data.datapoint_freshness_source(point) == "unknown"
    assert data.stamp_source_dataset({"k": point}, None)["k"].source_dataset is None


def test_miscellaneous_data_branches() -> None:
    bad_power = Dataset.from_json(
        {"Data": [{"key": "p", "dataFieldName": "charging_power", "value": "bad"}]}
    ).points
    assert data.is_actively_charging(bad_power) is None
    invalid_capture = {
        "a": DataPoint("a", "car_captured_time", "bad"),
        "b": DataPoint("b", "car_captured_time", "2026-01-01T00:00:00Z"),
        "c": DataPoint("c", "car_captured_time", "2025-01-01T00:00:00Z"),
    }
    assert data.latest_captured_point(invalid_capture).key == "b"
    assert data.last_connected_info({}).source == "none"
    assert data.redact_dataset_filename(None, "VIN") is None
    assert data.redact_dataset_filename("file.zip", "VIN") == "file.zip"
    curated = CuratedSensor("x", "X")
    assert data.resolve_curated_distance_unit(curated, {}) is None
    curated = CuratedSensor("x", "X", unit_resolver="other", unit_field="x.unit")
    assert data.resolve_curated_distance_unit(curated, {}) is None
    curated = CuratedSensor("x", "X", unit_resolver="distance", unit_field="x.unit")
    assert data.resolve_curated_distance_unit(curated, {}) is None
