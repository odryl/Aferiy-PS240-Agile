# Cosy Octopus planner

For forecast timing, grid-backup deadlines and daily history, see
[Solar timing and daily outcomes](SOLAR_AND_OUTCOMES.md).

The Cosy planner turns a Cosy Octopus import tariff and an AFERIY PS240 into a
fixed, predictable daily routine. It is the flagship feature of this fork: the
whole day is published as seven meaningful tariff and operating periods, and the
battery charges only as much as the next non-cheap block needs.

## Why it is a fixed schedule, not an optimiser

Cosy's cheap windows are the same every day, so there is nothing to search for.
The plan is therefore deterministic and auditable: every half-hour belongs to a
named period, and the charge target for each cheap period is derived from the
household demand it has to cover.

Cosy Octopus uses Charge-to-target during its three local-time cheap periods:
`04:00-07:00`, `13:00-16:00`, and `22:00-00:00`. It uses CT-controlled
Self-Gen/Zero Export between those windows: `00:00-04:00`, `07:00-13:00`, and
`16:00-22:00`. At target SOC, a cheap period holds Idle. During the
afternoon cheap period, **Cosy Daylight Flex** can wait in Idle for PV while
enough target catch-up time remains, then use 1,200 W AC Charge only from the
latest safe start. The dashboard consolidates the day into its seven meaningful
cheap, standard, and peak periods, showing the validated price and current
catch-up margin without 48 repeated rows. Regional Cosy unit prices are not
hard-coded.

The Cosy target is calculated separately for each cheap period using the
configured battery capacity and discharge reserve. It budgets a maximum 850 W
of battery supply—0.425 kWh per half-hour—through the non-cheap period before
the next cheap window. If live SOC already meets that target, the controller
uses Idle rather than purchasing unnecessary energy. Targets are capped at
the configured Charge Limit, and the plan reports any energy the installed
battery capacity and permitted SOC range cannot cover.

## Schedule estimates

Costs, energy, and SOC are projected through the displayed fixed schedule from
its planning time to midnight. Elapsed periods contribute no estimated energy;
past SOC values are unavailable. A partial current period uses only its remaining
time, and charging stops at that period's target. Tomorrow starts from today's
projected midnight SOC when today's valid plan is available.

The projected household supply uses the existing demand profile and is bounded
by the battery output limit and reserve. Targets still use the conservative
maximum-output assumption described above. These are schedule estimates: live
solar, Daylight Flex, household demand, and controller interruptions can change
the result.

Estimated net value means avoided household import minus the cost of replacing
that supplied energy, using the mean remaining paid cheap rate and charge/discharge
losses. Charging cost is shown separately. Happy Hour credit is disclosed
separately and is not added again to net value. These figures are neither measured
savings nor a household bill.

## Set it up

1. Install [BottlecapDave's Octopus Energy integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy)
   and confirm it provides event entities resembling:

   ```text
   event.octopus_energy_electricity_<SERIAL>_<MPAN>_current_day_rates
   event.octopus_energy_electricity_<SERIAL>_<MPAN>_next_day_rates
   ```

2. Open **Settings → Devices & services → AFERIY PS240 Agile → Configure**.
3. Enable **Octopus Rate Proposed Plan (Agile or Cosy)**.
4. Select the current-day and next-day **import** rate event entities. Explicit
   selection is recommended even though a single import meter can be detected
   automatically.
5. Select **Cosy Octopus** in the device's **Energy Tariff** entity so the
   source tariff code is validated correctly.
6. Optionally select **Octopus Weekend Happy Hours power-up event** (see below).
7. Save. The integration reloads automatically.

The **Agile Proposed Plan Today** and **Agile Proposed Plan Tomorrow** sensors
then publish the Cosy schedule. They keep their Agile names for backward
compatibility, but their attributes follow the selected tariff. Cosy disables
the legacy fixed-window Smart Overnight scheduler, so the two cannot fight over
the same battery.

## Weekend Happy Hours

Octopus [Weekend Happy Hours](https://octopus.energy/saving-sessions/weekend-happy-hours/)
are the one Cosy period the tariff rates cannot describe. The free hour is not a
unit-rate change: you are billed normally and Octopus credits the energy back
afterwards, so it never appears in the published Cosy prices. Eligibility is not
tariff-based either — you need a smart meter, Direct Debit or prepay, Octoplus
membership, and Saving Sessions enrolment.

To plan them, the integration reads the booked window from
[BottlecapDave's Octopus Energy integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy).
That integration exposes joined and available sessions on its power-up session
events entity, which is **disabled by default**, so:

1. Open **Settings → Devices & services → Octopus Energy**.
2. Enable the **Octopus Power Up Events** entity for your account. Its entity ID
   ends in `_octoplus_power_up_events`.
3. In the AFERIY integration options, either leave **Octopus Weekend Happy
   Hours power-up event** empty for automatic discovery when exactly one exists,
   or select the entity explicitly.

Octopus publishes the coming weekend's slots on Thursdays, and you book one in
your Octopus dashboard. The plan then:

- treats every half-hour the booked window touches as **free energy** and charges
  towards the configured Charge Limit, even inside the peak or standard bands;
- publishes `happy_hour_windows`, `scheduled_free_energy_periods`,
  `happy_hour_grid_charge_kwh`, and `estimated_happy_hour_credit_gbp` on the
  Proposed Plan sensors;
- counts the import as grid energy but keeps it out of the billed charge cost and
  the replacement rate, so it cannot inflate the estimated net saving;
- shows the window on the Cosy card as *Free power · charge to N%* with the
  credited-back amount instead of a cost.

Notes and limits:

- Without the power-up events entity the plan is unchanged: no free windows and
  no guessed ones. The `happy_hour_source` attribute reads `unavailable`.
- The Octopus credit is capped at 16 kWh per hour, and the offer as published
  runs to 1 November 2026.
- A Happy Hour is worth less when it lands inside the `13:00-16:00` cheap period,
  because that energy was already cheap and the battery may already be at target.
  The clearest gain is a slot in the `16:00-22:00` block, where the plan
  otherwise self-generates.
- Only Happy Hour sessions are planned. Regular Power Up sessions are skipped
  rather than treated as free windows.

The external helper checkboxes are reminders for installers. They do not install or validate integrations. Smart estimates look for standard Solcast forecast files and sensors and use `zone.home` for home occupancy. Battery control and the overnight target use the configured tariff window and AECC grid reading; Shelly comparison remains diagnostic only.

## Automated control

The **Cosy Automated Control** switch is a separate explicit opt-in. While it is
Off the planner is advisory only. If activation is rejected, the card shows
**Couldn’t enable automatic control** and the controller's reason, even though
the switch remains Off. For example, select **Self-Gen/Zero Export** first when
the controller reports an incompatible manual operating mode, then retry.

See
[Guarded automated control](../README.md#guarded-automated-control) for the
gating, verification, and fail-safe behaviour shared with Agile.

