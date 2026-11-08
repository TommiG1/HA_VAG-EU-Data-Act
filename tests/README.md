# Tests

Two layers, run independently.

## Offline core tests (no Home Assistant)

`test_offline.py`, `test_api_mock.py`, `test_brands.py` exercise the pure-Python
pieces (data parsing, transforms, sentinel detection, binary decoding, brand
registry, login HTML parsing). They depend only on `aiohttp` and run on the
project's regular Python venv:

```bash
python tests/test_offline.py
python tests/test_api_mock.py
python tests/test_brands.py
```

These are the fast feedback loop for refactors that don't touch Home Assistant.

## HA-harness tests (full Home Assistant)

Pytest under `tests/` (except the offline scripts above) uses
[`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
to spin up a real `hass` instance and load the integration the same way Home
Assistant does at runtime.

Install and run from a Python 3.13+ venv:

```bash
pip install -r requirements_test.txt
pytest tests/ --ignore=tests/test_offline.py -v
```

## Coverage (Silver floor)

Silver requires **≥95% line coverage in every module**. CI combines offline
scripts and the HA harness:

```bash
coverage erase
coverage run --source=custom_components/cupra_eu_data_act tests/test_offline.py
coverage run -a --source=custom_components/cupra_eu_data_act tests/test_api_mock.py
coverage run -a --source=custom_components/cupra_eu_data_act tests/test_brands.py
coverage run -a --source=custom_components/cupra_eu_data_act tests/test_cache.py
coverage run -a --source=custom_components/cupra_eu_data_act \
  -m pytest tests/ --ignore=tests/test_offline.py -q
coverage report --fail-under=95
coverage json -o coverage.json
python scripts/check_module_coverage.py --min 95
```

On Windows, run the harness from WSL or a Linux container — HA's test
dependencies (`uvloop`, native bluetooth bindings) don't build on native
Windows. The offline tests work everywhere.
