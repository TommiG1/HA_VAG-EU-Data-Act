# Use cases

Practical things you can do with this read-only integration. All examples assume
portal data is flowing (roughly every 15 minutes).

## 1. Show the car on a dashboard

Open the vehicle device under **Settings → Devices & services** and pin:

- Battery / SoC
- Electric range
- Charging binary or charge state
- Mileage
- Vehicle locked
- Minutes since last snapshot (data freshness)

Dashboard tips: [dashboards/README.md](../dashboards/README.md).

## 2. Track charging in the Energy dashboard

Use the cumulative charged-energy sensor (`total_increasing`). Optionally enable
**Create monthly utility meter helpers** in the integration options.

Details: [ENERGY.md](ENERGY.md).

## 3. Notify when charging finishes

Import the **Charge complete — notify** blueprint and pick your charging binary
sensor, battery sensor, and phone notify service.

See [EXAMPLES.md](EXAMPLES.md).

## 4. Warn on low battery while not charging

Import the **Low battery — notify** blueprint. It stays quiet while the car is
already charging.

## 5. Notice stale portal data

When the car sleeps, telemetry can freeze. The `snapshot_stale` binary sensor
and the repair issue use your **Stale after (hours)** option. Automate on that
binary, or import the **Stale snapshot — notify** blueprint.

## 6. Automate on lock / door state

Use curated binary sensors such as `locked` or door/window entities when the
portal provides them. Remember: states can lag by up to about 15 minutes, so
this is not a real-time alarm system.

## 7. Remind yourself before the portal subscription lapses

Watch `days_until_subscription_expires` or import the **Subscription expiring —
notify** blueprint. Renew the continuous request on the portal (not in Home
Assistant).

## 8. Feed evcc or other chargers (read path)

Expose SoC, range, and charging state from Home Assistant to tools that only
need to **read** the car. Write/control paths still need a wallbox or another
integration that can command charging; this one cannot.

## What not to expect

- Instant updates while driving
- Remote climate or charge control
- Guaranteed GPS / device tracker from the portal alone
- Identical entity sets on every model
