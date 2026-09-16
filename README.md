# AFERIY PS240 Agile

![AFERIY PS240 local battery control for Home Assistant](docs/images/aferiy-ps240-readme-hero.jpeg)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://www.hacs.xyz/)
[![Version](https://img.shields.io/badge/version-v1.8.32-blue.svg)](CHANGELOG.md)

Local Home Assistant control for the **AFERIY PS240** battery, plus two
tariff-aware planners for Octopus Energy customers in the UK:

- **[Cosy Octopus planner](#cosy-octopus-planner)** — a fixed, auditable daily
  schedule around Cosy's three cheap windows.
- **[Agile Octopus planner](#agile-octopus-planner)** — a shadow-mode economic
  plan for the day-ahead half-hourly market.

A fork of [MortUK/Aferiy-PS240-Local-](https://github.com/MortUK/Aferiy-PS240-Local-)
with the `aecc_battery` domain and entity IDs preserved, so it drops in as an
upgrade over an existing install. See [attribution](#attribution).

> [!IMPORTANT]
> Both planners are **advisory by default**. Nothing is sent to the battery until
> you turn on the matching **Agile Automated Control** or **Cosy Automated
> Control** switch. Those switches are beta, start Off after every restart, and
> never send a fixed Discharge or Feed command.

## Cosy Octopus planner

<img src="docs/images/card.png" alt="Cosy Octopus battery plan card showing the live action, battery SOC against target, the seven consolidated tariff periods, and the Wi-Fi loss recovery card" width="820">

*The Cosy Octopus plan card: current action and price, live SOC against its
target, the seven consolidated tariff periods, and the Wi-Fi loss recovery card
alongside live battery telemetry.*

Cosy's cheap windows are the same every day, so the planner does not search —
it publishes a deterministic schedule you can read at a glance. The day is
condensed into its **seven meaningful cheap, standard, and peak periods** instead
of 48 repeated half-hour rows, with each period showing its validated price,
target, purpose, duration, and any capacity shortfall.

- **Charge to target, not to full.** Each cheap period charges only the SOC
  needed to cover the next non-cheap block, budgeting 850 W of CT-controlled
  household supply (0.425 kWh per half-hour). At target, the period holds Idle.
- **Self-Gen in between.** Between cheap windows the battery follows real
  household demand through the CT clamp, with zero export.
- **Cosy Daylight Flex.** During the afternoon cheap period the battery can wait
  in Idle for live PV while enough target catch-up time remains, then start
  1,200 W AC charging from the latest safe moment.
- **Regional pricing respected.** Cosy unit prices are read from the validated
  plan, never hard-coded.
- **Weekend Happy Hours.** Booked Octopus free-power windows are planned as
  zero-cost grid charging, even when they land in the peak band.

Full detail: **[Cosy Octopus planner](docs/COSY_PLANNER.md)**

## Agile Octopus planner

A view-only economic plan for today and tomorrow, published as two sensors —
**Agile Proposed Plan Today** and **Agile Proposed Plan Tomorrow**.

- **Rolling horizon.** Once tomorrow's prices are published, today's evening
  discharge is valued against the cheapest sufficient set of real pre-16:00
  refill periods tomorrow, rather than an elapsed or assumed price. Tomorrow
  starts from today's projected SOC.
- **Profitability gate.** Discharge is proposed only when avoided import exceeds
  the estimated delivered replacement cost by at least £0.03/kWh.
- **PV-adjusted demand.** The fallback profile subtracts historically measured
  PV, so the plan is not fooled by solar it already counted.
- **Fail-closed validation.** Stale, incomplete, wrong-tariff, or mismatched
  meter data is rejected as `Invalid` with the reason in the `reason` attribute,
  rather than producing a plausible-looking wrong plan.
- **Confirmed local limits.** 1,200 W AC charging (0.6 kWh per half-hour) and
  1,000 W CT-controlled household supply (0.5 kWh per half-hour). Peak operation
  is Self-Gen/Zero Export; the planner never proposes a fixed discharge command.
- **Shadow-plan export.** A service and ready-made automation record each plan
  next to its live outcome, so control can be justified with data first.

Full detail: **[Agile Octopus planner](docs/AGILE_PLANNER.md)**

## Guarded automated control

Two separate switches, **Agile Automated Control** and **Cosy Automated
Control**. Each is accepted only for its matching tariff, with the legacy
fixed-window Overnight Charge selector Off, the complete battery bank present,
and connection, SOC, and rate data all fresh. The controller requires two
healthy polls before acting, verifies acknowledgements, returns to
Self-Gen/Zero Export on failure, and stays Off after every restart.

## Quick start

You need Home Assistant 2024.8 or newer, the static IP address of the AFERIY
**master/coordinator** unit, and — for either planner —
[BottlecapDave's Octopus Energy integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy).

Do not add executor/slave PS240 units separately: the master reports and controls
the whole bank, and adding slaves causes duplicate or competing connections.

### Install with HACS

1. HACS → **Integrations** → three-dot menu → **Custom repositories**.
2. Add `https://github.com/odryl/Aferiy-PS240-Agile` as an **Integration**.
3. Install **AFERIY PS240 Agile** and restart Home Assistant.

This repository is private, so the GitHub account used by HACS needs access to
it. Otherwise copy `custom_components/aecc_battery` from a clone into
`config/custom_components/` and restart.

### Configure

1. **Settings → Devices & services → Add integration → AFERIY PS240 Agile**.
2. Select the discovered master/coordinator, or enter its static IP. Keep port
   `8080` unless the battery uses another port.
3. Confirm **System Average Battery SOC** updates.
4. For a planner, open the integration's **Configure** dialog, enable **Octopus
   Rate Proposed Plan**, select the current-day and next-day import rate events,
   set the **Energy Tariff** to Cosy or Agile, then save.

Then add the dashboard card: register
`/aecc_battery_static/aferiy-agile-plan-card.js?v=1.8.32` as a JavaScript module
under **Settings → Dashboards → Resources** and add
`type: custom:aferiy-agile-plan-card`. See
[Dashboard card](docs/dashboard-card.md).

## Documentation

| Guide | Covers |
| --- | --- |
| [Cosy Octopus planner](docs/COSY_PLANNER.md) | Fixed daily schedule, targets, Daylight Flex, Weekend Happy Hours |
| [Agile Octopus planner](docs/AGILE_PLANNER.md) | Rolling horizon, profitability gate, shadow export |
| [Advanced configuration](docs/ADVANCED_CONFIGURATION.md) | Device options, fixed-window tariffs, Wi-Fi recovery, overnight charging, Feed mode, output limits |
| [Dashboard card](docs/dashboard-card.md) | Card resources, entities and YAML |
| [Entities](docs/entities.md) | Sensors, numbers, selects, switches, buttons |
| [Troubleshooting](docs/troubleshooting.md) | Common failures and first checks |
| [Agile implementation](docs/AGILE_IMPLEMENTATION.md) | Planner safety invariants |
| [Maintainer handover](docs/HANDOVER.md) | Live-system assumptions, development checks, release process |
| [Changelog](CHANGELOG.md) | Release history |

## Attribution

This fork builds directly on [MortUK/Aferiy-PS240-Local-](https://github.com/MortUK/Aferiy-PS240-Local-),
which provides the local AFERIY/AEC TCP protocol implementation, the device
entities, and the manual controls that everything here depends on. The
`aecc_battery` domain, upstream entity IDs, and the upstream configuration flow
are deliberately retained for compatibility.

Upstream itself is based on the MIT-licensed `StekkerDeal/aecc-battery-local`
project, which in turn was forked from `slaapyhoofd/Lunergy-Local-TCP`. Thanks
to all three.

## License

MIT. See [LICENSE](LICENSE).
