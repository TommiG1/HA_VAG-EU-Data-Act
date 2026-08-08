# VW Group EU Data Act for Home Assistant

<p align="center">
  <img src="custom_components/cupra_eu_data_act/brand/icon.png" alt="VW Group EU Data Act" width="128" height="128">
</p>

[![Test](https://github.com/TommiG1/HA_VAG-EU-Data-Act/actions/workflows/test.yml/badge.svg)](https://github.com/TommiG1/HA_VAG-EU-Data-Act/actions/workflows/test.yml)
[![Home Assistant Community](https://img.shields.io/badge/Forum-Home%20Assistant-41BDF5?logo=homeassistant&logoColor=white)](https://community.home-assistant.io/t/beta-vw-group-eu-data-act-vehicle-data-for-vw-audi-skoda-seat-cupra-bentley-official-portal/1013514)
[![Donate](https://img.shields.io/badge/Donate-PayPal-00457C?logo=paypal&logoColor=white)](https://www.paypal.com/paypalme/tommigraf)

A Home Assistant custom integration that reads vehicle data from the official
[Volkswagen Group EU Data Act portal](https://eu-data-act.drivesomethinggreater.com/).

Supports **all major VAG brands** on the portal: Volkswagen, Audi, Škoda, SEAT,
Cupra, Bentley, and Volkswagen Commercial Vehicles.

After VW restricted unofficial third-party API access in 2026, this integration
provides a **legal, read-only** alternative using the portal intended for vehicle
owners under the EU Data Act.

> **Beta** — see [TESTING.md](TESTING.md) if you want to help test your brand.
> See [RELEASE_NOTES.md](RELEASE_NOTES.md) for version history.

> **Not a replacement for WeConnect integrations:** no climate control, no
> charging commands, no real-time polling. Data updates roughly every 15 minutes.

## Supported brands

| Home Assistant | Brand slug (`test_login.py`) |
|----------------|------------------------------|
| Volkswagen | `volkswagen` |
| Volkswagen Commercial Vehicles | `volkswagen_commercial` |
| Audi | `audi` |
| Škoda | `skoda` |
| SEAT | `seat` |
| Cupra | `cupra` |
| Bentley | `bentley` |

Use the brand that matches your account credentials (VW ID, myAudi, Cupra ID, etc.).

## Requirements

- Home Assistant **2024.12.0** or newer
- Account for your brand on the EU Data Act portal (VW ID, Cupra ID, myAudi, etc.)
- You must be the **Primary User** of the vehicle on that account
- Active **continuous 15-minute** data request on the portal (free; renew on the portal about every 12 months)

## FAQ

### Do I need VW Connect Plus (paid app subscription)?

**No.** VW Connect Plus is a separate paid package for remote app features (climate,
charge control, etc.) — not for the EU Data Act portal. The [official portal
FAQ](https://eu-data-act.drivesomethinggreater.com/pl/en/service/faq.html) states
that access to your vehicle data is **free of charge** under the EU Data Act; you
only need a Volkswagen Group brand account linked to the vehicle.

Do not confuse that with the portal’s own **continuous data request** (the
15-minute “subscription” you create under **Data clusters** on
[eu-data-act.drivesomethinggreater.com](https://eu-data-act.drivesomethinggreater.com/),
not in the brand app). That is free and is what this integration downloads —
it is unrelated to Connect Plus.

### Does the car need to be online?

**Yes.** The portal only delivers what the vehicle uploads. If you only receive
`_no_content_found` ZIPs, wake the car (drive, ignition on, or open the mobile
app). Whether telemetry still flows after all manufacturer connectivity packages
(basic Connect, trial, Connect Plus) have expired is not fully documented; if you
get real data without Connect Plus, please share your model in the
[community thread](https://community.home-assistant.io/t/beta-vw-group-eu-data-act-vehicle-data-for-vw-audi-skoda-seat-cupra-bentley-official-portal/1013514)
— it helps other owners.

### Why do I only see ~7 entities?

**Normal right after setup.** Those are built-in diagnostic sensors (integration
status, last connected, dataset generated, uncurated fields, etc.). Vehicle
sensors (SoC, range, mileage, charging, …) are created automatically once the
integration downloads the first ZIP with real content — **no reload needed**.

Check the **Integration status** sensor on the device and **Settings → System →
Repairs** for portal hints. Once status shows `ok` and **Uncurated fields** is
greater than zero, many more entities should appear within one poll cycle.

### How long until the first real data?

Often **15–60 minutes** after activating the continuous request, sometimes
**several hours**. Community reports also mention **1–3 days** — especially if the
portal initially rejected the request, the car has not uploaded telemetry yet, or
you need one or two drives before the full **All Data** payload arrives.

Empty `_no_content_found` snapshots in the first 15-minute windows are normal.
**Persistent emptiness over days** is not — see the next section.

### Setup fails or no data yet?

**Complete portal setup before Home Assistant.** The integration only downloads
ZIP files from an **already active** continuous 15-minute subscription — it
cannot create or fix portal requests.

If setup shows *Could not connect to the EU Data Act portal* **after** login and
vehicle selection, your credentials are usually fine. The error often means the
portal has no **Identifier** yet for an active continuous request on that VIN
(onboarding not finished, or the portal backend is having problems).

On the portal, confirm:

1. The vehicle is linked under **Data clusters → Vehicle overview**.
2. A **continuous** (not one-time) **15-minute** request is active with the
   **All Data** dataset preset — not only **Charging**, and not a manual
   selection of every individual field (see [portal setup](#portal-setup-required)).
3. Real ZIP files appear for the VIN — first delivery can take **15–60 minutes,
   sometimes several hours, occasionally 1–3 days** after creating the request.
4. Only **one** customised data request can be active at a time ([portal
   FAQ](https://eu-data-act.drivesomethinggreater.com/pl/en/service/faq.html)).
   A pending **one-time export** blocks a new continuous request until it
   finishes (up to 24 hours). The portal often has no cancel button — wait or
   contact **portal support** via the Contact section.

Then add the integration again (or remove and re-add). If the portal UI itself
shows errors such as *We couldn't transmit your request*, that is a **portal-side
problem** — not something this integration can bypass.

After a portal outage, some fields may show stale values until the car uploads
fresh telemetry again (often after one drive). Data can also stay stale for
hours and then refresh in one burst — that is upstream portal behaviour, not
something Home Assistant controls.

### Portal keeps delivering only empty files for days?

If login works and the continuous 15-minute request is active, but **every**
portal ZIP is `_no_content_found` for **days** (not just the first hours), this
is a **portal or vehicle-side** issue — not a Home Assistant or credential
problem. The same model can work for other owners (e.g. one Golf 8 with 77
entities while another receives only empty files).

Things to try:

1. **Delete and recreate** the data request on the portal — select the **All
   Data** dataset preset, not a manual tick of every individual field.
2. **Wake the car** (drive, ignition on, or open the mobile app) and wait
   **24–48 hours**.
3. Contact **portal support** via the portal Contact section — responses can be
   slow or absent; the integration developer cannot influence the portal backend.

The integration cannot bypass an empty portal pipeline. If you are stuck here,
share your brand and model (no VIN) in the
[community thread](https://community.home-assistant.io/t/beta-vw-group-eu-data-act-vehicle-data-for-vw-audi-skoda-seat-cupra-bentley-official-portal/1013514).

### Disabled diagnostic sensors?

Some entities are **raw portal fields**, disabled by default. Ignore them unless
you are debugging — use the curated sensors (Battery, range, charge state, etc.)
instead.

## Portal setup (required)

**Do this first**, before adding the integration in Home Assistant.

The continuous **15-minute** request is created on the official Volkswagen Group
**EU Data Act portal** only. It is **not** in myAudi, the VW/Cupra/Škoda app, or
Home Assistant. Brand apps are only for signing in; the frequency setting lives
on the portal itself.

1. Open [eu-data-act.drivesomethinggreater.com](https://eu-data-act.drivesomethinggreater.com/)
   (same portal for Audi, VW, Cupra, Škoda, SEAT, Bentley)
2. Sign in with your brand account and connect the vehicle under
   **Data clusters → Vehicle overview**
3. Still on that portal, under **Data clusters**, create a **new data request**
   for the vehicle. Choose **continuous** (not a one-time export) and set the
   frequency to **15 minutes**. That option appears in the portal’s request
   dialog when you create or edit the request.
4. When choosing the dataset, select the **All Data** preset — not only
   **Charging**, and not a manual selection of every individual field. Pick the
   **All Data** cluster/preset in the portal UI; a charging-only request
   delivers far fewer fields, and manually ticking all fields can behave
   differently from the preset (community reports: empty ZIPs until the request
   was recreated with **All Data** only).
5. Wait until ZIP files with real content appear for your VIN — this can take
   from minutes up to **1–3 days** in some cases

Then install the integration and complete setup in Home Assistant.

## Installation

### HACS

1. HACS → **⋮** → **Custom repositories**
2. Add `https://github.com/TommiG1/HA_VAG-EU-Data-Act` as type **Integration**
3. Install **VW Group EU Data Act** → restart Home Assistant

### Manual

Copy `custom_components/cupra_eu_data_act` to `config/custom_components/` and restart.

### Add the integration

**Settings → Devices & Services → Add Integration → VW Group EU Data Act**

Select brand, enter credentials, choose vehicle. If setup fails at vehicle
selection, finish [portal setup](#portal-setup-required) first and retry once ZIPs
are arriving.

## Dataset formats

The portal uses two field naming layouts. The integration detects which one your
vehicle sends and creates the matching curated sensors:

| Format | Typical vehicles | Example fields |
|--------|------------------|----------------|
| **dotted** | ID.x, MEB (Born, ID.4, ID.7, …) | `battery_state_report.soc`, `mileage.value` |
| **flat** | Terramar PHEV, some hybrid/legacy layouts | `state_of_charge`, `boardnetBatteryVoltageIndication` |

Entity IDs and friendly names differ between formats and languages — pick entities
from the device page in Home Assistant rather than copying fixed names.

Sensors appear only when the portal delivers the field for your model (e.g.
**12V battery voltage** on Terramar PHEV).

## Data freshness

Each curated sensor exposes attributes so you can tell how old a reading is:

| Attribute | Meaning |
|-----------|---------|
| `data_captured_at` | Best-known capture time for the displayed value (ISO 8601) |
| `age_minutes` | Minutes between that capture time and now |
| `freshness_source` | `timestamp_utc`, `field_captured_time`, or `report_captured_time` |

These reflect **vehicle/portal data age**, not the same thing as the entity's
`last_updated` (when Home Assistant last polled). For overall snapshot age, see
the diagnostic sensor **Minutes since last snapshot**.

## Enum states (automations)

Curated enum sensors keep the **portal / VW value** as the Home Assistant state.
The UI may show a translated label (e.g. `Immediate (profile)`); automations and
templates must use the raw state (e.g. `CHARGE_MODE_IMMEDIATELY_PROFILE`).

Check **Developer tools → States** for the value your vehicle currently reports.
English labels below match `translations/en.json`; other languages use the same
keys with localized labels. Not every model reports every value.

### Dotted layout (ID.x / MEB)

**Charge state** (`charge_state`)

| State | UI label (en) |
|-------|---------------|
| `CHARGE_STATE_READY_FOR_CHARGING` | Ready for charging |
| `CHARGE_STATE_NOT_READY_FOR_CHARGING` | Not ready |
| `CHARGE_STATE_CHARGING_HV_BATTERY` | Charging HV battery |
| `CHARGE_STATE_CONSERVATION_CHARGING` | Conservation charging |
| `CHARGE_STATE_DISCHARGING` | Discharging |
| `CHARGE_STATE_CHARGING_ERROR` | Charging error |
| `CHARGE_STATE_CHARGE_PURPOSE_REACHED_AND_CONSERVATION` | Target reached (conservation) |
| `CHARGE_STATE_CHARGE_PURPOSE_REACHED_AND_NOT_CONSERVATION_CHARGING` | Target reached |

**Charge mode** (`charge_mode`)

| State | UI label (en) |
|-------|---------------|
| `CHARGE_MODE_IMMEDIATELY_DEFAULT` | Immediate (default) |
| `CHARGE_MODE_IMMEDIATELY_PROFILE` | Immediate (profile) |
| `CHARGE_MODE_IMMEDIATELY_STOPPED` | Immediate stopped |
| `CHARGE_MODE_EXTENDED_PROFILE` | Extended (profile) |
| `CHARGE_MODE_EXTENDED_STOPPED` | Extended stopped |
| `CHARGE_MODE_INVALID` | Invalid |

**Charge type** (`charge_type`)

| State | UI label (en) |
|-------|---------------|
| `CHARGE_TYPE_AC` | AC |
| `CHARGE_TYPE_DC` | DC |
| `CHARGE_TYPE_OFF` | Off |

**Charging scenario** (`charging_scenario`)

| State | UI label (en) |
|-------|---------------|
| `CHARGING_SCENARIO_OFF` | Off |
| `CHARGING_SCENARIO_IMMEDIATELY_CHARGING_ACTIVE` | Immediate charging |
| `CHARGING_SCENARIO_IMMEDIATELY_CHARGING_FINISHED` | Immediate charging done |
| `CHARGING_SCENARIO_CHARGING_TO_DEPARTURE_TIME_ACTIVE` | Charging to departure |
| `CHARGING_SCENARIO_CHARGING_TO_DEPARTURE_TIME_FINISHED` | Departure charging done |
| `CHARGING_SCENARIO_OPTIMISED_CHARGING_AC` | Optimised AC charging |
| `CHARGING_SCENARIO_OPTIMISED_CHARGING_FINISHED` | Optimised charging done |

**Charging action state** (`immediate_action_state`)

| State | UI label (en) |
|-------|---------------|
| `IMMEDIATE_ACTION_STATE_INVALID` | Invalid |
| `IMMEDIATE_ACTION_STATE_IMMEDIATE_CHARGING` | Immediate charging |
| `IMMEDIATE_ACTION_STATE_IMMEDIATE_ACTION_TIME` | Action: time |
| `IMMEDIATE_ACTION_STATE_IMMEDIATE_ACTION_STOPPED` | Action stopped |
| `IMMEDIATE_ACTION_STATE_IMMEDIATE_ACTION_RANGE` | Action: range |
| `IMMEDIATE_ACTION_STATE_IMMEDIATE_ACTION_SOC` | Action: SoC |
| `IMMEDIATE_ACTION_STATE_CHARGE_MODE_SELECTION` | Mode selection |

**Charge mode selection** (`charge_mode_selection`)

| State | UI label (en) |
|-------|---------------|
| `CHARGE_MODE_SELECTION_INVALID` | Invalid |
| `CHARGE_MODE_SELECTION_IMMEDIATECHARGING` | Immediate charging |
| `CHARGE_MODE_SELECTION_IMMEDIATE_DISCHARGING` | Immediate discharging |
| `CHARGE_MODE_SELECTION_TIMERCHARGING` | Timer charging |
| `CHARGE_MODE_SELECTION_TIMER_CHARGING_CLIMATIZATION` | Timer + climate |
| `CHARGE_MODE_SELECTION_PREFERRED_CHARGING_TIMES` | Preferred times |
| `CHARGE_MODE_SELECTION_ONLY_OWN_CURRENT` | Own current only |
| `CHARGE_MODE_SELECTION_HOME_STORAGE_CHARGING` | Home storage |

**Max AC charge current** (`max_ac_charge_current`)

| State | UI label (en) |
|-------|---------------|
| `MAX_CHARGE_CURRENT_INVALID` | Invalid |
| `MAX_CHARGE_CURRENT_MAXIMUM` | Maximum |
| `MAX_CHARGE_CURRENT_REDUCED` | Reduced |

**Auto unlock AC** (`auto_unlock_ac`)

| State | UI label (en) |
|-------|---------------|
| `AUTO_UNLOCK_AC_INVALID` | Invalid |
| `AUTO_UNLOCK_AC_OFF` | Off |
| `AUTO_UNLOCK_AC_ONCE` | Once |
| `AUTO_UNLOCK_AC_PERMANENT` | Permanent |

**BCAM activation** (`bcam_activation`)

| State | UI label (en) |
|-------|---------------|
| `BCAM_ACTIVATION_ACTIVATED` | Activated |
| `BCAM_ACTIVATION_DEACTIVATED` | Deactivated |

**Charging timer reachability** (`charging_timer_reachability`)

| State | UI label (en) |
|-------|---------------|
| `TARGET_REACHABILITY_CALCULATING` | Calculating |
| `TARGET_REACHABILITY_REACHABLE` | Reachable |
| `TARGET_REACHABILITY_NOT_REACHABLE` | Not reachable |

**Window heating** (`window_heating_state`)

| State | UI label (en) |
|-------|---------------|
| `WINDOW_HEATING_STATE_OFF` | Off |
| `WINDOW_HEATING_STATE_ON` | On |

### Flat layout

These sensors use shorter portal values (not the long `CHARGE_*` enums above).

**Charge state** (`charging_state`)

| State | UI label (en) |
|-------|---------------|
| `off` | Off |
| `charging` | Charging |
| `error` | Error |
| `conserving` | Conserving |

**Charge mode** (`charging_mode`)

| State | UI label (en) |
|-------|---------------|
| `off` | Off |
| `manual` | Manual |
| `timer1` | Timer 1 |
| `timer2` | Timer 2 |
| `invalid` | Invalid |

**Charging reason** (`charging_reason_trigger`)

| State | UI label (en) |
|-------|---------------|
| `timer1` | Timer 1 |
| `timer2` | Timer 2 |
| `immediate` | Immediate |

**Charger update trigger** (`last_battery_charger_update_trigger`)

| State | UI label (en) |
|-------|---------------|
| `clamp15Off` | Clamp 15 off |

**Window heating** (`window_heating_state`) — same keys as in the dotted layout
when that sensor is present.

### Integration status

Diagnostic sensor on every installation:

| State | UI label (en) |
|-------|---------------|
| `starting` | Starting |
| `ok` | OK |
| `waiting_for_portal_data` | Waiting for data |
| `empty_snapshots` | Empty snapshots only |
| `delivery_not_ready` | Delivery not ready |

## Verifying it works

```bash
python3 -m venv .venv && .venv/bin/pip install aiohttp
.venv/bin/python tests/test_offline.py
.venv/bin/python tests/test_brands.py
.venv/bin/python tools/test_login.py --brand cupra you@example.com 'secret'
```

| `test_login.py` exit | Meaning |
|----------------------|---------|
| `0` | End-to-end OK with real data |
| `2` | Login OK, waiting for portal ZIPs |
| `1` | Error — check brand and credentials |

Full tester guide: [TESTING.md](TESTING.md)

## Energy dashboard helpers

For Home Assistant Energy dashboard, use the cumulative charged-energy sensor
from this integration (it has `device_class: energy` and
`state_class: total_increasing`):

- ID.x / dotted datasets: `sensor.<vehicle>_charged_energy`
- Flat datasets (older portal layout): `sensor.<vehicle>_total_energy_charged`

The integration also auto-creates monthly `utility_meter` helpers (if missing)
for:

- monthly charged energy (kWh)
- monthly mileage (km/mi, based on your vehicle unit)

> **Note:** Earlier versions (≤ v0.6.22) could auto-create a *Monthly electric
> consumption* helper from average driving-efficiency sensors (`kWh/100km`).
> That unit is wrong for a monthly energy total — the portal does not expose
> cumulative driving energy in kWh. Use **monthly charged energy** for kWh
> totals. If you still have the old helper, delete it under **Settings →
> Devices & services → Helpers**.

Additionally, `sensor.<vehicle>_last_charge` exposes the last observed charging
delta in kWh, derived from cumulative charged-energy updates.

## Lovelace / Dashboard

Entity IDs vary by device nickname, HA language, and dataset format — this
integration does not ship copy-paste dashboard YAML. See
[`dashboards/README.md`](dashboards/README.md) for which entities are worth
adding to your own dashboard (UI entity picker or Mushroom Cards via HACS).

## Limitations

- Read-only, ~15 min latency, portal-dependent delivery
- `_no_content_found.zip` empty snapshots are skipped automatically
- Porsche is not on this portal
- Intended for persons living in the **EU(27)** with vehicles **registered in the EU(27)**. Users outside the EU (e.g. Switzerland) may register on the portal but often receive no actual data delivery

## Support

Questions, feedback, and beta testing: [Home Assistant Community thread](https://community.home-assistant.io/t/beta-vw-group-eu-data-act-vehicle-data-for-vw-audi-skoda-seat-cupra-bentley-official-portal/1013514)

If this integration saves you time, you can donate via PayPal:

[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://www.paypal.com/paypalme/tommigraf)

[paypal.com/paypalme/tommigraf](https://www.paypal.com/paypalme/tommigraf)

## License

MIT — see [LICENSE](LICENSE). Attributions: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
