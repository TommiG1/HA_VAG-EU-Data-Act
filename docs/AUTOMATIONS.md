# Automations and sensor states

Curated enum sensors keep the **portal / VW value** as the Home Assistant state.
The UI may show a translated label (for example `Immediate (profile)`);
automations and templates must use the raw state (for example
`CHARGE_MODE_IMMEDIATELY_PROFILE`).

Check **Developer tools → States** for the value your vehicle currently reports.
English labels below match `translations/en.json`; other languages use the same
keys with localized labels. Not every model reports every value.

The portal uses two layouts (**dotted** for many ID.x / MEB cars, **flat** for
some PHEV and legacy payloads). Entity IDs differ; pick them from the device
page.

## Data freshness attributes

Each curated sensor exposes attributes for how old a reading is:

| Attribute | Meaning |
|-----------|---------|
| `data_captured_at` | Best-known capture time for the displayed value (ISO 8601) |
| `age_minutes` | Minutes between that capture time and now |
| `freshness_source` | `timestamp_utc`, `field_captured_time`, or `report_captured_time` |

These reflect **vehicle/portal data age**, not the entity’s `last_updated`
(when Home Assistant last polled). For overall snapshot age, see the diagnostic
sensor **Minutes since last snapshot**. The stale-snapshot threshold is
configurable under **Configure**.

## Dotted layout (ID.x / MEB)

### Charge state (`charge_state`)

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

### Charge mode (`charge_mode`)

| State | UI label (en) |
|-------|---------------|
| `CHARGE_MODE_IMMEDIATELY_DEFAULT` | Immediate (default) |
| `CHARGE_MODE_IMMEDIATELY_PROFILE` | Immediate (profile) |
| `CHARGE_MODE_IMMEDIATELY_STOPPED` | Immediate stopped |
| `CHARGE_MODE_EXTENDED_PROFILE` | Extended (profile) |
| `CHARGE_MODE_EXTENDED_STOPPED` | Extended stopped |
| `CHARGE_MODE_INVALID` | Invalid |

### Charge type (`charge_type`)

| State | UI label (en) |
|-------|---------------|
| `CHARGE_TYPE_AC` | AC |
| `CHARGE_TYPE_DC` | DC |
| `CHARGE_TYPE_OFF` | Off |

### Charging scenario (`charging_scenario`)

| State | UI label (en) |
|-------|---------------|
| `CHARGING_SCENARIO_OFF` | Off |
| `CHARGING_SCENARIO_IMMEDIATELY_CHARGING_ACTIVE` | Immediate charging |
| `CHARGING_SCENARIO_IMMEDIATELY_CHARGING_FINISHED` | Immediate charging done |
| `CHARGING_SCENARIO_CHARGING_TO_DEPARTURE_TIME_ACTIVE` | Charging to departure |
| `CHARGING_SCENARIO_CHARGING_TO_DEPARTURE_TIME_FINISHED` | Departure charging done |
| `CHARGING_SCENARIO_OPTIMISED_CHARGING_AC` | Optimised AC charging |
| `CHARGING_SCENARIO_OPTIMISED_CHARGING_FINISHED` | Optimised charging done |

### Charging action state (`immediate_action_state`)

| State | UI label (en) |
|-------|---------------|
| `IMMEDIATE_ACTION_STATE_INVALID` | Invalid |
| `IMMEDIATE_ACTION_STATE_IMMEDIATE_CHARGING` | Immediate charging |
| `IMMEDIATE_ACTION_STATE_IMMEDIATE_ACTION_TIME` | Action: time |
| `IMMEDIATE_ACTION_STATE_IMMEDIATE_ACTION_STOPPED` | Action stopped |
| `IMMEDIATE_ACTION_STATE_IMMEDIATE_ACTION_RANGE` | Action: range |
| `IMMEDIATE_ACTION_STATE_IMMEDIATE_ACTION_SOC` | Action: SoC |
| `IMMEDIATE_ACTION_STATE_CHARGE_MODE_SELECTION` | Mode selection |

### Charge mode selection (`charge_mode_selection`)

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

### Max AC charge current (`max_ac_charge_current`)

| State | UI label (en) |
|-------|---------------|
| `MAX_CHARGE_CURRENT_INVALID` | Invalid |
| `MAX_CHARGE_CURRENT_MAXIMUM` | Maximum |
| `MAX_CHARGE_CURRENT_REDUCED` | Reduced |

### Auto unlock AC (`auto_unlock_ac`)

| State | UI label (en) |
|-------|---------------|
| `AUTO_UNLOCK_AC_INVALID` | Invalid |
| `AUTO_UNLOCK_AC_OFF` | Off |
| `AUTO_UNLOCK_AC_ONCE` | Once |
| `AUTO_UNLOCK_AC_PERMANENT` | Permanent |

### BCAM activation (`bcam_activation`)

| State | UI label (en) |
|-------|---------------|
| `BCAM_ACTIVATION_ACTIVATED` | Activated |
| `BCAM_ACTIVATION_DEACTIVATED` | Deactivated |

### Charging timer reachability (`charging_timer_reachability`)

| State | UI label (en) |
|-------|---------------|
| `TARGET_REACHABILITY_CALCULATING` | Calculating |
| `TARGET_REACHABILITY_REACHABLE` | Reachable |
| `TARGET_REACHABILITY_NOT_REACHABLE` | Not reachable |

### Window heating (`window_heating_state`)

| State | UI label (en) |
|-------|---------------|
| `WINDOW_HEATING_STATE_OFF` | Off |
| `WINDOW_HEATING_STATE_ON` | On |

## Flat layout

These sensors use shorter portal values (not the long `CHARGE_*` enums above).

### Charge state (`charging_state`)

| State | UI label (en) |
|-------|---------------|
| `off` | Off |
| `charging` | Charging |
| `error` | Error |
| `conserving` | Conserving |

### Charge mode (`charging_mode`)

| State | UI label (en) |
|-------|---------------|
| `off` | Off |
| `manual` | Manual |
| `timer1` | Timer 1 |
| `timer2` | Timer 2 |
| `invalid` | Invalid |

### Charging reason (`charging_reason_trigger`)

| State | UI label (en) |
|-------|---------------|
| `timer1` | Timer 1 |
| `timer2` | Timer 2 |
| `immediate` | Immediate |

### Charger update trigger (`last_battery_charger_update_trigger`)

| State | UI label (en) |
|-------|---------------|
| `clamp15Off` | Clamp 15 off |

### Window heating (`window_heating_state`)

Same keys as in the dotted layout when that sensor is present.

## Integration status

Diagnostic sensor on every installation:

| State | UI label (en) |
|-------|---------------|
| `starting` | Starting |
| `ok` | OK |
| `waiting_for_portal_data` | Waiting for data |
| `empty_snapshots` | Empty snapshots only |
| `delivery_not_ready` | Delivery not ready |
