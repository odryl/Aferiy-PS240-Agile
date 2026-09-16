# Agile Octopus planner

Two sensors should appear:

- **Agile Proposed Plan Today**
- **Agile Proposed Plan Tomorrow**

`Proposed` means a complete advisory plan is available. `Limited` means the
battery cannot reach the target using the remaining periods. `Waiting for
Rates` means Octopus has not supplied the required entity data. `Invalid`
means the integration deliberately rejected stale, incomplete, wrong-tariff, or
mismatched meter data; the sensor's `reason` attribute explains why.

Before Octopus publishes tomorrow's prices, **Tomorrow** correctly stays at
`Waiting for Rates`; it does not invalidate an otherwise complete **Today**
plan. Once both rate events contain a published rate list, their MPAN, meter
serial, and Agile tariff are compared before either plan uses the data.

After tomorrow's rates are published (normally during the afternoon), the two
sensors form a rolling horizon. **Today** values evening discharge against the
cheapest sufficient set of real pre-16:00 refill periods tomorrow, rather than
an elapsed or assumed price. **Tomorrow** starts from Today's projected SOC at
the end of the protection window. The attributes `next_day_rates_used`,
`replacement_rate_source`, `projected_soc_at_protection_end`, and
`starting_soc_source` show when this coupling is active. If tomorrow's data is
missing or unusable, Today safely retains its existing same-day calculation.

The plan aims for 100% SOC by 16:00, protects expected household demand until
22:00, and only proposes discharge when the avoided import price exceeds the
estimated delivered replacement cost by at least £0.03/kWh. Proposed Agile
AC grid charging is capped at **1200 W** (0.6 kWh per half-hour). Peak supply
uses Self-Gen/Zero Export, whose CT follows household demand, with a **1000 W**
maximum household output used by the plan (0.5 kWh per half-hour). The Agile
controller does not send fixed discharge commands.

The fallback Agile profile subtracts historical measured PV from household
demand. Forecast PV is not deducted from Agile savings figures. For live
control, however, an optional **Available PV power entity** can provide a
current inverter reading or solar "power now" estimate when the PS240's own
reading is curtailed at its Charge Limit.

## Set it up

1. Open **Settings → Devices & services**.
2. Open the AFERIY integration and select **Configure**.
3. Enable **Octopus Rate Proposed Plan (Agile or Cosy)**.
4. Select the current-day and next-day **import** rate event entities. Explicit
   selection is recommended even though a single import meter can be detected
   automatically.
5. For Agile, set **Battery ready by** to `16:00` and **Protect household
   demand until** to `22:00`. Cosy uses its fixed daily schedule instead.
6. Select **Octopus Agile** or **Cosy Octopus** in the device's **Energy
   Tariff** entity so the source tariff code is validated correctly.
7. For Cosy, optionally select **Octopus Weekend Happy Hours power-up event** to
   plan booked free-power windows. Enable that entity in the Octopus Energy
   integration first, or leave this empty for automatic discovery.
8. Save. The integration reloads automatically.

## Live control

The Agile plan is view-only until **Agile Automated Control** is switched on for
the Agile tariff. The same guarded controller, gates, and fail-safes cover both
tariffs: see [Guarded automated control](../README.md#guarded-automated-control).

## Export a shadow-plan history

Use the `aecc_battery.export_agile_plan` service to append the current Today
and Tomorrow read-only plans to `/config/aecc_battery_agile_plan_export.jsonl`.
The JSON Lines file is intended for comparing a week or two of proposed plans
with actual SOC, import and household demand. Each record also includes battery
SOC/capacity, charge and discharge power, grid and PV power, and the
integration's household-demand power plus cumulative energy readings. It
excludes the MPAN and Octopus source entity ID, and never sends a battery
command.

For a useful plan-versus-outcome history, create this 30-minute automation:

```yaml
alias: Export Agile trial data every 30 minutes
description: Capture each plan and its live outcome shortly after the tariff boundary.
trigger:
  - platform: time_pattern
    minutes: "/30"
    seconds: "10"
action:
  - service: aecc_battery.export_agile_plan
    data:
      label: shadow_decision_v3
mode: single
```

Schema-v3 records include `planner_revisions` and
`demand_profile_revisions`, plus cumulative PV generation, battery charge, and
battery discharge energy. They also record the active operating mode, last
local command, commanded direction, connection freshness, overnight scheduler
state, the shadow operating decision, and guarded-controller status. This
allows Self-Gen/Zero Export discharge and manual charging to be separated from
the Agile recommendation and any commands the guarded controller actually sent.

The active JSONL rotates automatically at 8 MiB. The completed segment is
preserved beside it as a timestamped `.jsonl.gz` archive and the next sample
starts a fresh active file. Download the archives for long-term retention; send
only the current segment for routine analysis. Existing schema-v1/v2 history
does not need to be deleted.

After the trial, download the file using the File Editor, Samba share, or your
usual Home Assistant backup method. The **AECC Agile Plan Export** sensor shows
the most recent successful export time and file name.

If Home Assistant reports that the custom card does not exist, confirm the
resource URL, restart Home Assistant, and hard-refresh the browser. If the card
loads but shows `Waiting for Rates`, check the two Octopus rate event entities
in the AFERIY integration options.

## Safety invariants

See [Octopus Agile implementation](AGILE_IMPLEMENTATION.md) for the invariants
and the gates required before any later automatic-control phase.

## First-day verification

Before relying on the displayed recommendation or opting into control, check:

- both plan sensors identify the expected MPAN and Agile tariff
- Tomorrow changes from `Waiting for Rates` after Octopus publishes its prices
- no proposed charge period exceeds 1200 W or 0.6 kWh, and no planned
  household-supply period exceeds 1000 W or 0.5 kWh
- the plan is ready by 16:00 and covers the 18:00-22:00 household peak
- the battery itself remains unaffected while Agile Automated Control is Off

Keep shadow mode running long enough to compare proposed periods with actual
SOC, import, solar, and household demand. When first enabling control, supervise
several transitions and confirm the switch reports verified commands and a
successful return to Self-Gen.

## Troubleshooting

- **Waiting for Rates:** verify BottlecapDave's current/next-day event entities
  exist and are selected in the AFERIY options.
- **Invalid – not owned by Octopus Energy:** select the original
  `octopus_energy` event entity, not a template or copied sensor.
- **Invalid – tariff is not Agile:** confirm the selected entities belong to
  the Agile import agreement rather than export or a fixed tariff.
- **Invalid – different MPAN/serial/tariff:** the current and next entities are
  from different meters or agreements.
- **Card not found:** restart Home Assistant, confirm the dashboard resource is
  a JavaScript module, then hard-refresh the browser.
- **More than one AFERIY system:** configure the card's two entity IDs explicitly.

See [Octopus Agile implementation](AGILE_IMPLEMENTATION.md) for the safety
invariants and the gates required before any later automatic-control phase.
