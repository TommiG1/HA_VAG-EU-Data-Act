# Examples and blueprints

Ready-made automations live in
[`blueprints/automation/cupra_eu_data_act/`](../blueprints/automation/cupra_eu_data_act/).
They use entity selectors filtered to this integration, so you pick your own
sensors after import.

## Import a blueprint

1. Copy the YAML file into your Home Assistant config, for example
   `config/blueprints/automation/cupra_eu_data_act/`
2. Or open the raw GitHub URL and use **Settings → Automations & scenes →
   Blueprints → Import blueprint**
3. Create an automation from the blueprint and select entities from your vehicle
   device

Notify fields accept `notify.mobile_app_…` with or without the `notify.` prefix.

## Shipped blueprints

| Blueprint | What it does |
|-----------|--------------|
| `low_battery_notify.yaml` | Phone alert when SoC is low and the car is not charging |
| `charge_complete_notify.yaml` | Alert when charging stops or SoC reaches a target |
| `stale_snapshot_notify.yaml` | Alert when portal telemetry is older than your stale threshold |
| `subscription_expiring_notify.yaml` | Alert when estimated portal subscription days run low |
| `vehicle_unlocked_notify.yaml` | Alert when the curated “vehicle locked” binary turns off |

## Minimal YAML example (no blueprint)

Notify when charging ends:

```yaml
automation:
  - alias: "Car charge finished"
    trigger:
      - platform: state
        entity_id: binary_sensor.my_car_charging
        to: "off"
        from: "on"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Charging finished"
          message: "SoC is {{ states('sensor.my_car_battery') }}%."
```

Replace entity IDs with those from your device page. Prefer portal **raw**
states in conditions (see [AUTOMATIONS.md](AUTOMATIONS.md)).

## More reading

- Use cases: [USE_CASES.md](USE_CASES.md)
- Entity catalogue: [SUPPORTED_FUNCTIONS.md](SUPPORTED_FUNCTIONS.md)
- Freshness attributes: [AUTOMATIONS.md](AUTOMATIONS.md)
