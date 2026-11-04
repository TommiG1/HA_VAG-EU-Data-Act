# Energy dashboard

Use the cumulative charged-energy sensor from this integration. It has
`device_class: energy` and `state_class: total_increasing`:

- ID.x / dotted datasets: `sensor.<vehicle>_charged_energy`
- Flat datasets: `sensor.<vehicle>_total_energy_charged`

`sensor.<vehicle>_last_charge` exposes the last observed charging delta in kWh,
derived from cumulative charged-energy updates.

## Monthly utility meter helpers

Monthly `utility_meter` helpers (charged energy and mileage) are **opt-in**.
Enable **Create utility meters** under
**Settings → Devices & services → VW Group EU Data Act → Configure**.

Existing helpers from earlier versions keep working. New ones appear only after
you turn the option on. If you delete a helper, it is not recreated.

Use **monthly charged energy** for kWh totals in the Energy dashboard. The
portal does not expose cumulative driving energy in kWh, so average
efficiency sensors (`kWh/100km`) are the wrong source for a monthly energy
total.
