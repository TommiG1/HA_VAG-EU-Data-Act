# VW Group EU Data Act for Home Assistant

<p align="center">
  <img src="custom_components/cupra_eu_data_act/brand/icon.png" alt="VW Group EU Data Act" width="128" height="128">
</p>

[![Test](https://github.com/TommiG1/HA_VAG-EU-Data-Act/actions/workflows/test.yml/badge.svg)](https://github.com/TommiG1/HA_VAG-EU-Data-Act/actions/workflows/test.yml)
[![Home Assistant Community](https://img.shields.io/badge/Forum-Home%20Assistant-41BDF5?logo=homeassistant&logoColor=white)](https://community.home-assistant.io/t/beta-vw-group-eu-data-act-vehicle-data-for-vw-audi-skoda-seat-cupra-bentley-official-portal/1013514)
[![Donate](https://img.shields.io/badge/Donate-PayPal-00457C?logo=paypal&logoColor=white)](https://www.paypal.com/paypalme/tommigraf)

A Home Assistant custom integration that reads vehicle data from the official
[Volkswagen Group EU Data Act portal](https://eu-data-act.drivesomethinggreater.com/).

Supports Volkswagen, Volkswagen Commercial Vehicles, Audi, Škoda, SEAT, Cupra,
and Bentley.

After VW restricted unofficial third-party API access in 2026, this integration
provides a **legal, read-only** alternative using the portal intended for
vehicle owners under the EU Data Act.

> **Not a replacement for WeConnect integrations:** no climate control, no
> charging commands, no real-time polling. Data updates roughly every 15 minutes.

## Requirements

- Home Assistant **2024.12.0** or newer
- Account for your brand on the EU Data Act portal (VW ID, Cupra ID, myAudi, etc.)
- You must be the **Primary User** of the vehicle on that account
- Active **continuous 15-minute** data request on the portal (free; renew on the portal about every 12 months)

## Portal setup (required)

**Do this first**, before adding the integration in Home Assistant.

The continuous **15-minute** request is created on the official Volkswagen Group
**EU Data Act portal** only. It is not in myAudi, the VW/Cupra/Škoda app, or
Home Assistant. Brand apps are only for signing in.

1. Open [eu-data-act.drivesomethinggreater.com](https://eu-data-act.drivesomethinggreater.com/)
2. Sign in with your brand account and connect the vehicle under
   **Data clusters → Vehicle overview**
3. Create a **continuous** (not one-time) data request with frequency
   **15 minutes**
4. Select the **All Data** preset (not only **Charging**, and not a manual tick
   of every field)
5. Wait until ZIP files with real content appear for your VIN (minutes up to
   **1–3 days** in some cases)

Then install the integration and complete setup in Home Assistant. If something
fails, see [Troubleshooting](docs/TROUBLESHOOTING.md).

## Installation

### Marketplace / HACS

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=TommiG1&repository=HA_VAG-EU-Data-Act&category=integration)

Use the badge (or [this My link](https://my.home-assistant.io/redirect/marketplace_repository/?owner=TommiG1&repository=HA_VAG-EU-Data-Act&category=integration))
on a device that can reach your Home Assistant. On Home Assistant 2026.11+ it
opens the **Marketplace**; on older versions it opens **HACS**. If the
repository is not in the catalog yet, Home Assistant offers to add it as a
custom repository first. Then install **VW Group EU Data Act** and restart.

You can also add `https://github.com/TommiG1/HA_VAG-EU-Data-Act` manually under
HACS → **⋮** → **Custom repositories** (type **Integration**).

### Manual

Copy `custom_components/cupra_eu_data_act` to `config/custom_components/` and restart.

### Add the integration

**Settings → Devices & Services → Add Integration → VW Group EU Data Act**

Select brand, enter credentials, choose vehicle. Use the brand that matches your
account credentials (VW ID, myAudi, Cupra ID, etc.).

## After setup

Right after setup you typically see a handful of diagnostic sensors. Vehicle
sensors (SoC, range, mileage, charging, …) appear automatically once the first
ZIP with real content arrives. No reload needed.

Details and common portal issues:
[Troubleshooting](docs/TROUBLESHOOTING.md).

## Further reading

| Topic | Doc |
|-------|-----|
| FAQ and portal problems | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Automation states and freshness | [docs/AUTOMATIONS.md](docs/AUTOMATIONS.md) |
| Energy dashboard and utility meters | [docs/ENERGY.md](docs/ENERGY.md) |
| Dashboard entity hints | [dashboards/README.md](dashboards/README.md) |
| Login smoke tests | [TESTING.md](TESTING.md) |
| Version history | [RELEASE_NOTES.md](RELEASE_NOTES.md) |

## Limitations

- Read-only, ~15 min latency, portal-dependent delivery
- Empty `_no_content_found.zip` snapshots are skipped automatically
- Porsche is not on this portal
- Intended for persons living in the **EU(27)** with vehicles **registered in
  the EU(27)**. Users outside the EU (e.g. Switzerland) may register on the
  portal but often receive no actual data delivery

## Support

Questions and feedback:
[Home Assistant Community thread](https://community.home-assistant.io/t/beta-vw-group-eu-data-act-vehicle-data-for-vw-audi-skoda-seat-cupra-bentley-official-portal/1013514)

If this integration saves you time, you can
[donate via PayPal](https://www.paypal.com/paypalme/tommigraf).

## License

MIT — see [LICENSE](LICENSE). Attributions: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
