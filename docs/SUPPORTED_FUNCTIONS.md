# Supported functions

This integration is **read-only**. It exposes sensors, binary sensors,
one refresh button, one service, diagnostics download, and repair issues.
It does **not** lock, unlock, start climate, or control charging.

Entity IDs follow your device name in Home Assistant. The **translation key**
column is stable across languages and matches `strings.json`.

Not every vehicle gets every entity. Fields appear when the EU Data Act
portal delivers a usable value for that VIN (dotted ID.x/MEB vs flat PHEV
layouts differ). Raw diagnostic sensors are disabled by default.

## Always present (after setup)

| Kind | Translation key | Role |
|------|-----------------|------|
| sensor | `integration_status` | Portal/integration health |
| sensor | `days_until_subscription_expires` | Estimated portal subscription remaining |
| sensor | `minutes_since_last_snapshot` | Age of last vehicle telemetry |
| sensor | `last_vehicle_update` | Timestamp of last vehicle capture |
| sensor | `last_connected` | Last connected / capture time |
| sensor | `dataset_generated` | When the current ZIP was generated |
| sensor | `uncurated_fields_count` | Portal fields without a curated entity |
| binary_sensor | `snapshot_stale` | Telemetry older than the configured threshold |
| button | `refresh` | Fetch the latest portal dataset now |

## Service

| Service | Description |
|---------|-------------|
| `cupra_eu_data_act.refresh_now` | Query the portal immediately (optional config entry target) |

## Sensors (curated catalogue)

English names below. Your UI language may differ.

### Battery and charging

| Translation key | English name |
|-----------------|--------------|
| `boardnet_battery_voltage_indication` | 12V battery voltage |
| `battery_state_report_soc` | Battery |
| `state_of_charge` | Battery |
| `energy_contents_maximal_energy_content_physical_value` | Battery capacity |
| `energy_contents_current_energy_content_physical_value` | Battery energy |
| `bcam_activation` | BCAM activation |
| `battery_care_mode_charge_bcam_threshold` | BCAM charge threshold |
| `bem_level` | BEM level |
| `battery_state_report_charge_bulk_threshold` | Charge bulk threshold |
| `charge_mode` | Charge mode |
| `charge_mode_selection` | Charge mode selection |
| `battery_state_report_charge_power` | Charge power |
| `charging_power` | Charge power |
| `battery_state_report_charge_rate` | Charge rate |
| `actual_charge_rate` | Charge rate |
| `charge_state` | Charge state |
| `charge_type` | Charge type |
| `battery_state_report_charge_energy` | Charged energy |
| `last_battery_charger_update_trigger` | Charger update trigger |
| `fuel_level_current_level` | Fuel level |
| `hv_battery_level` | HV battery level |
| `last_charge_kwh` | Last charge |
| `max_ac_charge_current` | Max AC charge current |
| `battery_state_report_remaining_charging_time_complete` | Remaining charging time |
| `battery_state_report_remaining_charging_time_bulk` | Remaining time to bulk |
| `residual_energy_in_percent` | Residual energy |
| `settings_target_soc` | Target charge level |
| `charged_energy` | Total energy charged |

### Range and mileage

| Translation key | English name |
|-----------------|--------------|
| `range_value` | Electric range |
| `value_of_the_primary_range` | Electric range |
| `range` | Electric range |
| `inspection_distance` | Inspection distance |
| `maintenance_interval_distance_until_inspection` | Inspection distance |
| `mileage_value_timestamp` | Last connected |
| `mileage_timestamp` | Last connected |
| `mileage_value` | Mileage |
| `mileage` | Mileage |
| `maintenance_interval_distance_until_oil_change` | Oil change distance |
| `cruising_range_combined` | Range (combined) |
| `cruising_range_primary_engine` | Range (primary) |
| `cruising_range_secondary_engine` | Range (secondary) |
| `long_term_data_range_gain_distance` | Range gain distance (long) |
| `short_term_data_range_gain_distance` | Range gain distance (short) |
| `scr_range` | SCR range |
| `long_term_data_mileage` | Trip distance (long) |
| `short_term_data_mileage` | Trip distance (short) |
| `long_term_data_start_mileage` | Trip start mileage (long) |
| `short_term_data_start_mileage` | Trip start mileage (short) |
| `long_term_data_zero_emission_distance` | Zero-emission distance (long) |
| `short_term_data_zero_emission_distance` | Zero-emission distance (short) |

### Climate and temperatures

| Translation key | English name |
|-----------------|--------------|
| `max_temperature` | Battery max temperature |
| `min_temperature` | Battery min temperature |
| `additional_consumptions_interior_climatization_consumption` | Climate consumption |
| `outdoor_temperature` | Outside temperature |
| `outside_temperature_indication` | Outside temperature |
| `outside_temperature` | Outside temperature |
| `remaining_climate_time` | Remaining climate time |
| `window_heating_state` | Window heating |

### Service and maintenance

| Translation key | English name |
|-----------------|--------------|
| `oil_level_additional_oil_level` | Additional oil level |
| `inspection_distance` | Inspection distance |
| `maintenance_interval_distance_until_inspection` | Inspection distance |
| `inspection_due_date` | Inspection due |
| `maintenance_interval_time_until_inspection` | Inspection interval |
| `oil_level_total_max` | Max oil level |
| `maintenance_interval_distance_until_oil_change` | Oil change distance |
| `oil_change_due_date` | Oil change due |
| `maintenance_interval_time_until_oil_change` | Oil change interval |
| `oil_level_dipstick_indicator_function` | Oil dipstick indicator |
| `oil_level_actual_level` | Oil level |

### Tyres

| Translation key | English name |
|-----------------|--------------|
| `tyre_pressure_required_front_left` | Required tire pressure FL |
| `tyre_pressure_required_front_right` | Required tire pressure FR |
| `tyre_pressure_required_rear_left` | Required tire pressure RL |
| `tyre_pressure_required_rear_right` | Required tire pressure RR |
| `tyre_pressure_required_spare_tyre` | Required tire pressure spare |
| `tyre_pressure_differential_front_left` | Tire pressure diff FL |
| `tyre_pressure_differential_front_right` | Tire pressure diff FR |
| `tyre_pressure_differential_rear_left` | Tire pressure diff RL |
| `tyre_pressure_differential_rear_right` | Tire pressure diff RR |
| `tyre_pressure_differential_spare_tyre` | Tire pressure diff spare |
| `tyre_pressure_actual_front_left` | Tire pressure FL |
| `tyre_pressure_actual_front_right` | Tire pressure FR |
| `tyre_pressure_actual_rear_left` | Tire pressure RL |
| `tyre_pressure_actual_rear_right` | Tire pressure RR |
| `tyre_pressure_actual_spare_tyre` | Tire pressure spare |

### Consumption and efficiency

| Translation key | English name |
|-----------------|--------------|
| `long_term_data_average_electr_engine_consumption` | Avg electric consumption (long) |
| `short_term_data_average_electr_engine_consumption` | Avg electric consumption (short) |
| `long_term_data_average_fuel_consumption` | Avg fuel consumption (long) |
| `short_term_data_average_fuel_consumption` | Avg fuel consumption (short) |
| `additional_consumptions_interior_climatization_consumption` | Climate consumption |
| `cng_gas_level` | CNG gas level |
| `slope_consumption_values_descent_slope_consumption_physical_value` | Downhill consumption |
| `fuel_level_current_level` | Fuel level |
| `fuel_level_accuracy` | Fuel level accuracy |
| `additional_consumptions_residual_consumption` | Residual consumption |
| `slope_consumption_values_ascent_slope_consumption_physical_value` | Uphill consumption |

### Diagnostics and status

| Translation key | English name |
|-----------------|--------------|
| `dataset_generated` | Dataset generated |
| `days_until_subscription_expires` | Days until subscription expires |
| `integration_status` | Integration status |
| `last_connected` | Last connected |
| `last_vehicle_update` | Last vehicle update |
| `minutes_since_last_snapshot` | Minutes since last snapshot |
| `uncurated_fields_count` | Uncurated fields |
| `instrument_cluster_time` | Vehicle clock |

### Other sensors

| Translation key | English name |
|-----------------|--------------|
| `auto_unlock_ac` | Auto unlock AC |
| `long_term_data_average_speed` | Avg speed (long) |
| `charging_mode` | Charge mode |
| `charging_state` | Charge state |
| `immediate_action_state` | Charging action state |
| `charging_state_report_error_code` | Charging error code |
| `charging_reason_trigger` | Charging reason |
| `charging_scenario` | Charging scenario |
| `charging_timer_reachability` | Charging timer reachability |
| `position_front_left_door_window_lifter` | Front left window position |
| `position_front_right_door_window_lifter` | Front right window position |
| `car_captured_time` | Last telemetry |
| `position_rear_left_door_window_lifter` | Rear left window position |
| `position_rear_right_door_window_lifter` | Rear right window position |
| `remaining_charging_time` | Remaining charging time |
| `position_sunroof_motor_hood_1` | Sunroof position |
| `long_term_data_travel_time` | Travel time (long) |
| `short_term_data_travel_time` | Travel time (short) |

## Binary sensors

### Lock, doors, and openings

| Translation key | English name |
|-----------------|--------------|
| `lock_state` | Central lock |
| `open_state_front_left_door` | Front left door |
| `locked_state_front_left_door` | Front left door lock |
| `state_front_left_door_window_lifter` | Front left window |
| `open_state_front_right_door` | Front right door |
| `locked_state_front_right_door` | Front right door lock |
| `safe_state_front_right_door` | Front right door safe |
| `state_front_right_door_window_lifter` | Front right window |
| `open_state_front_engine_bonnet` | Hood |
| `locked_state_front_engine_bonnet` | Hood lock |
| `safe_state_front_engine_bonnet` | Hood safe |
| `state_of_hood` | Hood state |
| `open_state_rear_left_door` | Rear left door |
| `locked_state_rear_left_door` | Rear left door lock |
| `safe_state_rear_left_door` | Rear left door safe |
| `state_rear_left_door_window_lifter` | Rear left window |
| `open_state_rear_right_door` | Rear right door |
| `locked_state_rear_right_door` | Rear right door lock |
| `safe_state_rear_right_door` | Rear right door safe |
| `state_rear_right_door_window_lifter` | Rear right window |
| `state_service_hatch` | Service hatch |
| `state_spoiler` | Spoiler |
| `state_sunroof_motor_hood_1` | Sunroof |
| `state_sunroof_motor_hood_3` | Sunroof motor 3 |
| `open_state_tailgate` | Tailgate |
| `locked_state_tailgate` | Tailgate lock |
| `safe_state_tailgate` | Tailgate safe |
| `locked` | Vehicle locked |
| `open` | Vehicle open |
| `window_heating_state_front` | Window heating front |
| `window_heating_state_rear` | Window heating rear |

### Charging signals

| Translation key | English name |
|-----------------|--------------|
| `charging` | Charging |
| `plug_state` | Charging plug |
| `charge_mode_selection_options_home_storage_charging` | Home storage charging |
| `charge_mode_selection_options_immediate_charging` | Immediate charging |
| `charge_mode_selection_options_immediate_discharging` | Immediate discharging |
| `charge_mode_selection_options_only_own_current` | Only own current |
| `charge_mode_selection_options_preferred_charging_times` | Preferred charging times |
| `charge_mode_selection_options_timer_charging` | Timer charging |
| `charge_mode_selection_options_timer_charging_climatization` | Timer charging climatization |

### Lights and parking

| Translation key | English name |
|-----------------|--------------|
| `parking_brake` | Parking brake |
| `parking_light_left` | Parking light left |
| `parking_light_right` | Parking light right |
| `parking_lights` | Parking lights |

### Health and warnings

| Translation key | English name |
|-----------------|--------------|
| `state_service_hatch` | Service hatch |
| `snapshot_stale` | Snapshot stale |

### Other binary sensors

| Translation key | English name |
|-----------------|--------------|
| `led_state` | Charging LED |
| `energy_flow` | Energy flow |

## Related docs

- Automation state values: [AUTOMATIONS.md](AUTOMATIONS.md)
- Energy dashboard: [ENERGY.md](ENERGY.md)
- Use cases: [USE_CASES.md](USE_CASES.md)
- Examples and blueprints: [EXAMPLES.md](EXAMPLES.md)

