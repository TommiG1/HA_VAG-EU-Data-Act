# Supported devices

This integration talks to the official
[VW Group EU Data Act portal](https://eu-data-act.vwgroup-datahub.com/).
Support means: you can sign in with that brand’s account, select a VIN, and
receive portal ZIP datasets when a continuous 15-minute **All Data** request is
active.

Remote control (lock, climate, charge start/stop) is **not** supported for any
brand. Coverage of individual sensors depends on what the portal delivers for
your vehicle.

## Brands on the portal

| Brand in setup | Account | Portal status |
|----------------|---------|---------------|
| Volkswagen | VW ID | Supported |
| Volkswagen Commercial Vehicles | VW ID (commercial) | Supported |
| Audi | myAudi | Supported |
| Škoda | Škoda ID | Supported |
| SEAT | SEAT / Cupra ID family | Supported |
| Cupra | Cupra ID | Supported |
| Bentley | Bentley account on the Audi/IDK tenant | Offered; little community confirmation |

## Not on this portal

| Brand / region | Status |
|----------------|--------|
| Porsche | Not available on the EU Data Act portal used here |
| VW / Audi North America (US/CA) | Different backends; out of scope for this integration |
| Vehicles without Primary User rights | Portal will not deliver owner datasets |
| Non-EU registration / residence | Often can register but receive empty or no delivery |

## Dataset layouts

The portal uses two payload shapes. The integration auto-detects them:

| Layout | Typical vehicles | Notes |
|--------|------------------|-------|
| **Dotted** (MEB / ID.x style) | VW ID.3/4/5/7, Cupra Born, Škoda Enyaq, related BEVs | Rich charging and battery fields |
| **Flat** (PHEV / legacy style) | e.g. Cupra Terramar PHEV, Cupra Formentor Hybrid | Different field names; 12V voltage when present |

The same VIN always stays on one layout after the first real dataset.

## Community-confirmed examples

These are examples from development and community reports, not an exhaustive
approval list. Other models on the same brands usually work if the portal
delivers data.

| Example | Notes |
|---------|-------|
| Cupra Born | Dotted / MEB charging and range sensors |
| VW ID.3 / ID.4 / ID.7 | Dotted layout; UK miles units handled |
| Škoda Enyaq | Dotted layout |
| Cupra Terramar PHEV | Flat aliases (climate time, plug, charging power, 12V) |
| Cupra Formentor Hybrid | Flat / PHEV coverage |

If your model logs in but stays on empty snapshots, see
[TROUBLESHOOTING.md](TROUBLESHOOTING.md). That is usually a portal subscription
or vehicle-online issue, not a missing model mapping.

## Prerequisites per vehicle

1. You are the **Primary User** on the brand account
2. Continuous **15-minute** request with **All Data** on the portal
3. Vehicle registered / used in a way the portal actually delivers for (EU focus)
4. Car goes online often enough to upload telemetry
