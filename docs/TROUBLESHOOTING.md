# Troubleshooting

Common questions after installing **VW Group EU Data Act**. Portal setup steps
live in the [README](../README.md#portal-setup-required).

## Do I need VW Connect Plus?

**No.** VW Connect Plus is a paid package for remote app features (climate,
charge control, and similar). It is not required for the EU Data Act portal.
The [official portal FAQ](https://eu-data-act.drivesomethinggreater.com/pl/en/service/faq.html)
states that access to your vehicle data is free under the EU Data Act. You only
need a Volkswagen Group brand account linked to the vehicle.

Do not confuse that with the portal’s own **continuous data request** (the
15-minute subscription under **Data clusters** on
[eu-data-act.drivesomethinggreater.com](https://eu-data-act.drivesomethinggreater.com/),
not in the brand app). That request is free and is what this integration
downloads. It is unrelated to Connect Plus.

Whether telemetry still flows after all manufacturer connectivity packages
(basic Connect, trial, Connect Plus) have expired is not fully documented. If
you get real data without Connect Plus, please share your model in the
[community thread](https://community.home-assistant.io/t/beta-vw-group-eu-data-act-vehicle-data-for-vw-audi-skoda-seat-cupra-bentley-official-portal/1013514).

## Does the car need to be online?

**Yes.** The portal only delivers what the vehicle uploads. If you only receive
`_no_content_found` ZIPs, wake the car (drive, ignition on, or open the mobile
app).

## Why do I only see about 7 entities?

**Normal right after setup.** Those are built-in diagnostic sensors (integration
status, last connected, dataset generated, uncurated fields, and similar).
Vehicle sensors (SoC, range, mileage, charging, …) appear automatically once the
integration downloads the first ZIP with real content. No reload needed.

Check the **Integration status** sensor on the device and
**Settings → System → Repairs** for portal hints. Once status shows `ok` and
**Uncurated fields** is greater than zero, many more entities should appear
within one poll cycle.

## How long until the first real data?

Often **15–60 minutes** after activating the continuous request, sometimes
several hours. Community reports also mention **1–3 days**, especially if the
portal initially rejected the request, the car has not uploaded telemetry yet,
or you need one or two drives before the full **All Data** payload arrives.

Empty `_no_content_found` snapshots in the first 15-minute windows are normal.
Persistent emptiness over days is not. See the section below.

## Setup fails or no data yet?

Complete portal setup before Home Assistant. The integration only downloads ZIP
files from an **already active** continuous 15-minute subscription. It cannot
create or fix portal requests.

If setup shows *Could not connect to the EU Data Act portal* after login and
vehicle selection, your credentials are usually fine. The error often means the
portal has no Identifier yet for an active continuous request on that VIN
(onboarding not finished, or the portal backend is having problems).

On the portal, confirm:

1. The vehicle is linked under **Data clusters → Vehicle overview**.
2. A **continuous** (not one-time) **15-minute** request is active with the
   **All Data** dataset preset, not only **Charging**, and not a manual
   selection of every individual field.
3. Real ZIP files appear for the VIN. First delivery can take 15–60 minutes,
   sometimes several hours, occasionally 1–3 days after creating the request.
4. Only **one** customised data request can be active at a time
   ([portal FAQ](https://eu-data-act.drivesomethinggreater.com/pl/en/service/faq.html)).
   A pending one-time export blocks a new continuous request until it finishes
   (up to 24 hours). The portal often has no cancel button. Wait or contact
   portal support via the Contact section.

Then add the integration again (or remove and re-add). If the portal UI itself
shows errors such as *We couldn't transmit your request*, that is a portal-side
problem. This integration cannot bypass it.

After a portal outage, some fields may show stale values until the car uploads
fresh telemetry again (often after one drive). Data can also stay stale for
hours and then refresh in one burst. That is upstream portal behaviour, not
something Home Assistant controls.

## Portal keeps delivering only empty files for days?

If login works and the continuous 15-minute request is active, but every portal
ZIP is `_no_content_found` for **days** (not just the first hours), this is a
portal or vehicle-side issue, not a Home Assistant or credential problem. The
same model can work for other owners (for example one Golf 8 with many entities
while another receives only empty files).

Things to try:

1. Delete and recreate the data request on the portal. Select the **All Data**
   dataset preset, not a manual tick of every individual field.
2. Wake the car (drive, ignition on, or open the mobile app) and wait
   24–48 hours.
3. Contact portal support via the portal Contact section. Responses can be slow
   or absent; the integration developer cannot influence the portal backend.

If you are stuck here, share your brand and model (no VIN) in the
[community thread](https://community.home-assistant.io/t/beta-vw-group-eu-data-act-vehicle-data-for-vw-audi-skoda-seat-cupra-bentley-official-portal/1013514).

## Disabled diagnostic sensors?

Some entities are raw portal fields, disabled by default. Ignore them unless you
are debugging. Prefer the curated sensors (battery, range, charge state, and
similar).

## Dataset formats

The portal uses two field naming layouts. The integration detects which one your
vehicle sends:

| Format | Typical vehicles | Example fields |
|--------|------------------|----------------|
| **dotted** | ID.x, MEB (Born, ID.4, ID.7, …) | `battery_state_report.soc`, `mileage.value` |
| **flat** | Terramar PHEV, some hybrid/legacy layouts | `state_of_charge`, `boardnetBatteryVoltageIndication` |

Entity IDs and friendly names differ between formats and languages. Pick
entities from the device page rather than copying fixed names. Sensors appear
only when the portal delivers the field for your model.
