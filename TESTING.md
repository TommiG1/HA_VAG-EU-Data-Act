# Testing guide

Thank you for helping test **VW Group EU Data Act** for Home Assistant.

Installation and portal setup are documented in the [README](README.md). This
page is for smoke tests and what to report.

## Supported brands

| Brand slug | Select in HA | Notes |
|------------|--------------|-------|
| `volkswagen` | Volkswagen | VW passenger cars |
| `volkswagen_commercial` | Volkswagen Commercial Vehicles | Crafter, etc. |
| `audi` | Audi | myAudi credentials |
| `skoda` | Škoda | MyŠkoda credentials |
| `seat` | SEAT | SEAT ID credentials |
| `cupra` | Cupra | Cupra ID / MyCupra credentials |
| `bentley` | Bentley | Bentley credentials |

Choose the brand that matches your account. VW credentials with the Cupra brand
(or vice versa) will fail login.

**EU(27) only:** the portal is intended for residents and vehicles registered in
the EU(27). Accounts from outside the EU (e.g. Switzerland) may log in but often
get no data delivery.

**VW Connect Plus** is not required (see
[Troubleshooting](docs/TROUBLESHOOTING.md)). If you test without it and still get
real ZIPs, please mention model, country, and whether basic Connect / trial
connectivity is active.

## Quick smoke test (no Home Assistant)

```bash
python3 -m venv .venv && .venv/bin/pip install aiohttp

# List brands
.venv/bin/python tools/test_login.py --list-brands

# Test your brand (replace brand, email, password)
.venv/bin/python tools/test_login.py --brand audi you@example.com 'your-password'
```

| Exit code | Meaning |
|-----------|---------|
| `0` | Login OK + real dataset downloaded |
| `1` | Error — wrong brand/credentials or portal issue |
| `2` | Login OK, waiting for portal data (`_no_content_found` is normal at first) |

## What to report

Please open a [GitHub issue](https://github.com/TommiG1/HA_VAG-EU-Data-Act/issues) with:

- Brand slug and vehicle model (no VIN required)
- `test_login.py` exit code and last lines of output (redact email)
- HA version
- Whether portal ZIPs contain real data or only `_no_content_found`
- Relevant log lines (`custom_components.cupra_eu_data_act: debug`)

## Offline tests (for developers)

```bash
.venv/bin/python tests/test_offline.py
.venv/bin/python tests/test_api_mock.py
.venv/bin/python tests/test_brands.py
```
