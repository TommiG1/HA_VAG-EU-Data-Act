"""Filesystem edge coverage for the dataset cache."""
from custom_components.cupra_eu_data_act.cache import DatasetCache


def test_list_entries_skips_zip_named_directory(tmp_path) -> None:
    cache = DatasetCache(tmp_path)
    target = cache._vin_dir("VIN")
    target.mkdir(parents=True)
    (target / "directory.zip").mkdir()
    assert cache.list_entries("VIN") == []
