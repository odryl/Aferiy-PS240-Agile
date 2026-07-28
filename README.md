# AFERIY PS240 Agile

![AFERIY PS240 local battery control for Home Assistant](docs/images/aferiy-ps240-readme-hero.jpeg)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://www.hacs.xyz/)
[![Version](https://img.shields.io/badge/version-v1.8.10-blue.svg)](CHANGELOG.md)

Private Home Assistant fork combining local AFERIY PS240 monitoring with a
safe, view-only Octopus Agile battery planner.

It is based on [MortUK/Aferiy-PS240-Local-](https://github.com/MortUK/Aferiy-PS240-Local-)
and retains the `aecc_battery` integration domain, so existing entity IDs remain
compatible. This fork appears in Home Assistant as **AFERIY PS240 Agile**.

> [!IMPORTANT]
> The Octopus Agile feature is currently **shadow mode only**. It proposes a
> schedule but never sends Agile-driven commands to the battery. Existing
> manual and Smart Overnight controls inherited from upstream can control the
> battery independently, so leave Smart Overnight Charging **Off** during the
> initial Agile trial unless you deliberately want to use it.

## Features

- Local TCP connection to the battery, usually on port `8080`
- Battery state of charge, power, PV, charge, discharge, and diagnostic sensors
- Manual charge, discharge, idle, and self-consumption controls
- Experimental Feed mode with a passive Base Feed Power target
- Local-first automatic overnight charging with smart or manual SOC targets
- Charge and discharge SOC limits
- Existing local manual controls inherited from the upstream integration
- PV surplus charge trigger for systems with unmanaged microinverters
- Physics-aware filtering for occasional invalid SOC/power readings
- Home Assistant diagnostics export support
- Custom AFERIY PS240 icon
- Bundled AFERIY Overnight Plan dashboard card
- View-only Octopus Agile Proposed Plans for today and tomorrow
- Strict 800 W total-system Agile discharge ceiling (0.4 kWh per half-hour)
- GBP/kWh profitability checks and malformed/stale tariff-data safeguards
- Household-demand-aware planning based on an anonymized half-hour profile
- Connection health and last-command result sensors
- Optional one-hour manual Self-Gen restore queue for PS240 Wi-Fi outages
- Grid meter agreement and charging reason diagnostics

## Before You Install

You need:

- Home Assistant 2024.8 or newer
- HACS, unless installing manually
- The static local IP address of the AFERIY master/coordinator
- An Octopus Agile import tariff
- [BottlecapDave's Octopus Energy integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy)
  configured in Home Assistant

Do not add executor/slave PS240 units separately. Add only the master unit.

## Install This Private Repository With HACS

1. Open HACS in Home Assistant.
2. Select **Integrations**, open the three-dot menu, and choose **Custom repositories**.
3. Add `https://github.com/odryl/Aferiy-PS240-Agile` with category **Integration**.
4. Search for **AFERIY PS240 Agile** and install it.
5. Restart Home Assistant.

Because this repository is private, the GitHub account used by HACS must be
able to access it. If the repository is not visible to HACS, use the manual
installation below.

## Manual Install

1. Download or clone this repository using a GitHub account with access.
2. Copy `custom_components/aecc_battery` into Home Assistant's
   `config/custom_components/` directory.
3. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **AFERIY PS240 Agile**.
3. Select the discovered master/coordinator or enter its static IP address.
4. Keep the TCP port at `8080` unless the battery uses a different port.
5. Complete setup and confirm that System Average Battery SOC updates.

Use a static IP address or DHCP reservation for the battery so Home Assistant can always find it.

### Multiple PS240 Units

If you have more than one PS240 in the same AFERIY/AEC Cloud system, add only the master unit to this integration.

The master controls the slave units. You do not need a separate local integration entry for each battery. In testing, one local connection to the master has been more reliable than trying to connect to every unit.

### Queue Self-Gen after a Wi-Fi outage

`Self-Gen Reconnect Queue` is a local configuration selector, under the device's
configuration entities. Set it to `On (60 minutes)` before relying on it. If the
PS240 Wi-Fi is down, selecting `Self-Gen/Zero Export` stores one request for up
to 60 minutes. Once the integration has reconnected and received stable battery
data, it sends the Self-Gen restore once and verifies the acknowledgement.

Selecting any other manual operating mode cancels the queued request. The queue
never replays Charge, Discharge or Feed, and it is completely separate from the
view-only Agile Proposed Plan.

System-level readings are reported through the master. System Average Battery SOC is the main multi-unit SOC source and matches the behaviour shown in the AEC Cloud app.

The integration creates generic `Battery 1 SOC`, `Battery 2 SOC`, and similar entities from the local `Storage_list` entries reported by the master. This avoids tying dashboards to a particular serial number when a unit is replaced.

After adding, removing, or replacing a battery/inverter, restart Home Assistant or reload the integration so the individual battery entity list is rebuilt from the master. The Battery Capacity preset does not control battery identification.

## Connect Octopus Agile

BottlecapDave's integration should provide event entities resembling:

```text
event.octopus_energy_electricity_<SERIAL>_<MPAN>_current_day_rates
event.octopus_energy_electricity_<SERIAL>_<MPAN>_next_day_rates
```

Then:

1. Open **Settings → Devices & services**.
2. Open the AFERIY integration and select **Configure**.
3. Enable **Octopus Agile Proposed Plan**.
4. Select the current-day and next-day **import** rate event entities. Explicit
   selection is recommended even though a single import meter can be detected
   automatically.
5. Set **Battery ready by** to `16:00`.
6. Set **Protect household demand until** to `22:00`.
7. Save. The integration reloads automatically.

Two sensors should appear:

- **Agile Proposed Plan Today**
- **Agile Proposed Plan Tomorrow**

`Proposed` means a complete advisory plan is available. `Limited` means the
battery cannot reach the target using the remaining periods. `Waiting for
Rates` means Octopus has not supplied the required entity data. `Invalid`
means the integration deliberately rejected stale, incomplete, non-Agile, or
mismatched meter data; the sensor's `reason` attribute explains why.

Before Octopus publishes tomorrow's prices, **Tomorrow** correctly stays at
`Waiting for Rates`; it does not invalidate an otherwise complete **Today**
plan. Once both rate events contain a published rate list, their MPAN, meter
serial, and Agile tariff are compared before either plan uses the data.

The plan aims for 100% SOC by 16:00, protects expected household demand until
22:00, and only proposes discharge when the avoided import price exceeds the
estimated delivered replacement cost by at least £0.03/kWh. The Agile ceiling
is always **800 W for the whole battery system**, never per battery module.

## Create an Agile Dashboard

After installing or updating the integration, restart Home Assistant before
adding the dashboard so the bundled card file is available.

### 1. Register the card resource

1. Go to **Settings → Dashboards**.
2. Open the top-right three-dot menu and select **Resources**.
3. Select **Add resource**.
4. Enter `/aecc_battery_static/aferiy-agile-plan-card.js?v=1.8.10`.
5. Select **JavaScript module** and save.
6. Hard-refresh the browser. In the mobile app, fully close and reopen it.

If an older version of the resource already exists, edit its URL instead of
adding a duplicate.

### 2. Create a dedicated dashboard

1. Go to **Settings → Dashboards** and select **Add dashboard**.
2. Choose **New dashboard from scratch**.
3. Suggested settings:
   - Title: `AFERIY Energy`
   - Icon: `mdi:battery-clock`
   - Show in sidebar: enabled
4. Open the new dashboard and select the edit/pencil button.
5. If prompted, open the three-dot menu and select **Take control**.

### 3. Add the Agile plan card

1. While editing the dashboard, select **Add card**.
2. Choose **By card** and search for **AFERIY Agile Battery Plan**.
3. Add the card and save the dashboard.
4. In a Sections dashboard, use the card's **Layout** tab to make it full
   width.

If the card is not listed, add a **Manual** card containing:

```yaml
type: custom:aferiy-agile-plan-card
title: Octopus Agile Battery Plan
```

The card automatically finds the plan sensors when there is only one AFERIY
system. If more than one integration entry exists, identify them explicitly:

```yaml
type: custom:aferiy-agile-plan-card
title: Octopus Agile Battery Plan
today_entity: sensor.your_battery_agile_proposed_plan_today
tomorrow_entity: sensor.your_battery_agile_proposed_plan_tomorrow
```

Find the exact entity IDs under **Developer Tools → States** by searching for
`agile_proposed_plan`.

### 4. Add live battery status (optional)

Add an **Entities** or **Tile** card above the plan and select useful entities
from the AFERIY device, such as:

- System Average Battery SOC
- Total Battery Output Power
- AC Charging Power
- Battery Discharging Power
- Grid Import/Export
- Connection Status

The separate **AFERIY Overnight Plan** card describes the inherited
fixed-window scheduler. Do not add it to the Agile dashboard unless you switch
away from Octopus Agile and deliberately use a fixed-window tariff.

The card provides separate Today and Tomorrow plans with:

- starting and projected ready-by SOC
- planned grid-charge and protected-window discharge energy
- estimated grid-charge cost, avoided peak import and net saving
- the replacement cost assumed for discharged energy
- half-hour action, price, energy, average power and partial-period duration
- a collapsible view of all half-hour Agile prices

The price grid follows the same useful conventions as the Octopus Energy Rates
card: the live period is outlined, the cheapest remaining period is highlighted,
negative prices are blue, and increasing price bands progress from green through
amber to red. The defaults are 5p, 20p and 30p/kWh; override them in the card
YAML if they do not suit your household:

```yaml
lowlimit: 5
mediumlimit: 20
highlimit: 30
```

The cost figures cover the planned battery actions and protected-window value;
they are not a forecast of the household's complete electricity bill. Sensor
attributes expose the complete validated timetable and an explicit
`control_enabled: false` marker.

## Export Agile Shadow Plans

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
trigger:
  - platform: time_pattern
    minutes: "/30"
action:
  - service: aecc_battery.export_agile_plan
    data:
      label: half_hour_trial_sample
```

After the trial, download the file using the File Editor, Samba share, or your
usual Home Assistant backup method. The **AECC Agile Plan Export** sensor shows
the most recent successful export time and file name.

If Home Assistant reports that the custom card does not exist, confirm the
resource URL, restart Home Assistant, and hard-refresh the browser. If the card
loads but shows `Waiting for Rates`, check the two Octopus rate event entities
in the AFERIY integration options.

## First-Day Verification

Before relying on the displayed recommendation, check:

- both plan sensors identify the expected MPAN and Agile tariff
- Tomorrow changes from `Waiting for Rates` after Octopus publishes its prices
- no proposed period exceeds 800 W or 0.4 kWh
- the plan is ready by 16:00 and covers the 18:00-22:00 household peak
- the battery itself remains unaffected when the Proposed Plan changes

Keep shadow mode running for at least one to two weeks and compare proposed
periods with actual SOC, import, solar and household demand before considering
any separately reviewed automatic-control phase.

## Troubleshooting Agile Setup

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

See [Octopus Agile implementation](docs/AGILE_IMPLEMENTATION.md) for the safety
invariants and the gates required before any later automatic-control phase.

## Other Integration Options

The fork retains upstream options for polling, advanced energy estimates,
fixed off-peak tariffs, Solcast, occupancy, manual controls, and Smart Overnight
Charging. Those controls are independent of the Agile Proposed Plan.

The device Configuration section also provides Overnight Charge mode, Manual SOC, Energy Tariff, Custom Off-Peak Start/End, Solar Availability, Overnight Status, and Recommended Overnight SOC. Battery Capacity is always available while the Agile planner is enabled (and is also available when Advanced Energy Estimate Sensors is enabled).

The advanced estimate sensors are disabled by default because they can depend on external Home Assistant entities such as grid meters, solar forecast data, or household demand history.

Battery Capacity is an estimate input selected in 1.958 kWh module steps. It is used by the Agile charge/discharge plan and overnight energy calculations only. It does not limit the Battery N SOC sensors reported by the master. Set it to the actual number of installed modules before relying on an Agile plan.

The Energy Tariff defaults to **Octopus Agile**. In Agile mode, the Proposed
Plan uses the selected current-day and next-day Octopus rate events and the
legacy fixed-window Smart Overnight scheduler is disabled. Custom Off-Peak
Start/End controls are unavailable because those times do not apply to Agile.

Fixed-window presets remain available for Snug Octopus, Intelligent Octopus Go,
Octopus Go, EDF GoElectric 35, British Gas EV Power+, E.ON Next Drive,
British Gas Standard E7, EDF E7 Fixed, OVO Simpler Energy E7, Octopus E7,
and E.ON Next Pumped Fixed. If your tariff uses different cheap-rate hours,
choose Custom and set the start and end times manually in 24-hour `HH:MM`
format. These times are used only by the inherited fixed-window overnight target
and Pre-Sunrise Need calculations.

The external helper checkboxes are reminders for installers. They do not install or validate integrations. Smart estimates look for standard Solcast forecast files and sensors and use `zone.home` for home occupancy. Battery control and the overnight target use the configured tariff window and AECC grid reading; Shelly comparison remains diagnostic only.

### Smart Overnight Charging

Automatic Overnight Charging is designed for homes with a cheap overnight
tariff. The aim is simple: charge enough overnight to avoid expensive daytime
import, but leave room for free solar the next day.

It runs locally through the PS240 TCP connection. No Octopus or cloud trigger is
required.

- **On** uses the calculated Recommended Overnight SOC.
- **Manual** uses the Manual SOC slider.
- **Off** leaves overnight charging disabled.
- Starts one minute after the configured off-peak start time.
- Watches System Average Battery SOC during the cheap-rate window.
- Starts charging if SOC falls to or below the target.
- Holds/pauses once the target is reached.
- Re-checks the SMART target during off-peak and may raise the locked target if
  the live recommendation has increased materially. It does not lower the locked
  target mid-window, so the system avoids twitchy behaviour and can still carry
  useful cheap-rate energy forward on low-solar days.
- Restores Self-Gen/Zero Export five minutes before off-peak ends, because the
  PS240 can take a few minutes to move cleanly from grid charging back to normal
  battery behaviour.

Recommended Overnight SOC is calculated from:

- **Battery capacity** and the configured minimum discharge SOC, so unusable
  reserve is not counted as available energy.
- **House demand history**, using a weighted 30-day time-of-day profile from
  Home Assistant Recorder. The latest 14 valid occupied days receive the
  strongest weighting, while older days provide lighter fallback coverage so a
  two-week holiday does not make the house appear permanently empty. Retain at
  least 35 days in Recorder so the complete 30-day profile remains available.
- **Normal occupied-house use**, with `zone.home` used to avoid treating
  empty-house days as normal demand.
- **Tomorrow's Solcast forecast**, preferably the timed forecast file rather
  than yesterday's clipped production.
- **Whole-day balance**, comparing expected house demand with expected solar
  before the next off-peak window.
- **Pre-Sunrise Need**, covering the period after off-peak ends and before solar
  is expected to be useful.
- **Post-Sunset Need**, keeping enough reserve after useful solar falls away to
  reach the next cheap-rate window.
- **AFERIY AC charging**, which is subtracted from demand history so overnight
  grid charging is not counted as normal house use.
- **A user-set overnight buffer**, defaulting to 3%, for expected extra demand
  such as air conditioning or unusual morning use.
- **Automatic safeguards on top of that buffer**, retaining the existing
  protection for weak demand history, missing timed forecast detail,
  time-of-day demand fallback, low solar and close-call forecast days.

The **Overnight Buffer** slider is available under Configuration from 0% to
20%. It sets the normal baseline only; the integration may add its automatic
safeguards when the available data or forecast calls for more caution. The
recommended SOC attributes and bundled card show both the selected baseline and
the added safeguard amount.

House Demand automatically includes additional live solar-power sources added
to Home Assistant's **Energy Dashboard**. This is useful when the AFERIY system
shares the property with another inverter, such as Hoymiles. Add that inverter's
solar power and cumulative solar energy entities to the Energy Dashboard. Live
power keeps House Demand responsive, while the cumulative energy total
automatically corrects slower inverter polling before it becomes SMART history.
Configure both under **Settings > Dashboards > Energy > Solar Panels**. The
integration excludes its own AFERIY PV entity, adds the other configured solar
power to the demand calculation, and requires no extra AECC setting.

On low-solar or close-call days, the planner may deliberately charge more
overnight so cheap-rate energy is carried forward, while still leaving enough
battery space for the solar that is forecast to arrive.

The integration also includes a **Solar Availability** dropdown. Set it to Solar
Unavailable when panels are covered, disconnected, or otherwise unable to
generate. The overnight calculation will then treat the solar forecast as 0 kWh
and show Batteries Only status.

#### Important Solcast Setup

When setting up Solcast, **do not set the AC inverter output to 800 W per unit**.

The batteries are capable of charging much faster than this and are rated to
**2.4 kW**.

If this is set too low, Solcast can under-estimate solar production. That can
make the overnight recommendation too high and charge the batteries more than
needed.

### Dashboard Card

The integration includes a bundled **AFERIY Overnight Plan** Lovelace card that
shows the smart overnight target, battery capacity, demand versus solar balance,
Pre-Sunrise Need, Post-Sunset Need, useful solar time, forecast confidence, and
SMART History completeness. It also shows expected reserve before the next
off-peak window and any SMART forecast/demand tuning that has been applied.

![AFERIY Overnight Plan dashboard card](docs/images/aferiy-overnight-plan-card.png)

To make it available in Home Assistant's card picker:

1. Restart Home Assistant after installing or updating the integration.
2. Add dashboard resource `/aecc_battery_static/aferiy-overnight-plan-card.js`
   as a JavaScript module.
3. Edit a dashboard, choose Add card, switch to By card, and search for
   `AFERIY Overnight Plan`.

See [Dashboard Card](docs/dashboard-card.md) for manual YAML and optional entity
overrides.

Local schedule-slot registers mirrored from the AEC Cloud app were tested and
behaved as immediate commands on the PS240, so they are not exposed as normal
controls. The integration-owned scheduler instead performs the timing in Home
Assistant and sends the same proven local Charge, Idle, and Self-Gen commands.

### Solar Clipping And Export

The PS240 can clip or hold back surplus PV when the battery is full or when the system is running in zero-feed behaviour.

Bypassing this PV clipping has been possible in testing, but the mode switching became unreliable. The current self-consumption switching is deliberately conservative because it reliably returns the battery to a safe local operating mode after charging or idling.

At the moment, bypassing clipping/export reliably is not supported by this integration. It may become possible in the future, but it may also need a firmware or app/API update from AFERIY before it can be made stable.

### PV Surplus Charge Trigger

This setting is useful when the AFERIY system shares the same electrical system
with an unmanaged micro-inverter or another PV source that it does not directly
control.

As soon as your Smart Meter (usually Shelly) sees that you are exporting more than your set value
between `0 W` and `50 W`, it tells your home batteries to ramp up and start
charging from the extra energy.

Having a small buffer gives the system a stable threshold to trigger clean,
sustained battery charging without constantly hunting or "chattering" around
zero.

### Experimental Feed Mode

Feed mode is experimental. It is intended for users who want the battery to
provide a base grid-connected output, especially where there is no smart
meter/CT feedback available for normal zero-feed control.

The **Base Feed Power** slider is passive. Moving the slider only stores the
target value in Home Assistant. Nothing is sent to the battery until you select
**Feed** from the Operating Mode dropdown.

When Feed is selected, the integration writes the local base feed/discharge
register discovered from the AEC Cloud app's **Battery base grid-connected
power** setting.

This is not the same as the normal Discharge mode:

- Discharge uses a manual schedule slot and takes over the battery.
- Feed stays closer to the EMS/grid-connected behaviour and applies a base
  feed target.
- Actual output may be higher or lower than the slider value.
- On systems with a smart meter or CT clamp, the EMS may adjust output while it
  continues managing grid flow.
- On systems without smart meter feedback, it may behave more like a fixed
  discharge target.

To stop Feed mode, select **Self-Gen/Zero Export**. The integration clears the
base feed value when returning to Self-Gen.

## Output Limit Notes

The PS240 has been observed to accept 800 W reliably over local TCP. The integration keeps register `3039` visible in diagnostics so higher output-limit behaviour can be investigated, but it does not write that register during normal commands.

## Documentation

- [Entities](docs/entities.md)
- [Dashboard Card](docs/dashboard-card.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Changelog](CHANGELOG.md)

## Attribution

This integration is based on the MIT-licensed `StekkerDeal/aecc-battery-local` project, which itself was forked from `slaapyhoofd/Lunergy-Local-TCP`.

## License

MIT. See `LICENSE`.
