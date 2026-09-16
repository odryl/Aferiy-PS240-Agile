# Advanced configuration and device operation

Everything on this page is optional. The Cosy and Agile planners work without
any of it. These are the inherited local-device controls, recovery options, and
estimate features that come with the AFERIY PS240 integration.

## Device configuration options

The device Configuration section also provides Overnight Charge mode, Manual SOC, Energy Tariff, Custom Off-Peak Start/End, Solar Availability, Overnight Status, and Recommended Overnight SOC. Battery Capacity is always available while the Agile planner is enabled (and is also available when Advanced Energy Estimate Sensors is enabled).

The advanced estimate sensors are disabled by default because they can depend on external Home Assistant entities such as grid meters, solar forecast data, or household demand history.

Battery Capacity is an estimate input selected in 1.958 kWh module steps. It is used by the Agile charge/discharge plan and overnight energy calculations only. It does not limit the Battery N SOC sensors reported by the master. Set it to the actual number of installed modules before relying on an Agile plan.

The Energy Tariff defaults to **Octopus Agile**. In Agile or Cosy mode, the
Proposed Plan uses the selected current-day and next-day Octopus rate events.
Both tariffs disable the legacy fixed-window Smart Overnight scheduler to avoid
conflicting commands. The plan remains advisory until **Agile Automated
Control** or **Cosy Automated Control** is explicitly enabled for the selected
tariff. Custom Off-Peak Start/End controls are
available only with the Custom tariff preset.

Fixed-window presets remain available for Snug Octopus, Intelligent Octopus Go,
Octopus Go, EDF GoElectric 35, British Gas EV Power+, E.ON Next Drive,
British Gas Standard E7, EDF E7 Fixed, OVO Simpler Energy E7, Octopus E7,
and E.ON Next Pumped Fixed. If your tariff uses different cheap-rate hours,
choose Custom and set the start and end times manually in 24-hour `HH:MM`
format. These times are used only by the inherited fixed-window overnight target
and Pre-Sunrise Need calculations.

## Multiple PS240 units

If you have more than one PS240 in the same AFERIY/AEC Cloud system, add only the master unit to this integration.

The master controls the slave units. You do not need a separate local integration entry for each battery. In testing, one local connection to the master has been more reliable than trying to connect to every unit.

## Queue Self-Gen after a Wi-Fi outage

`Self-Gen Reconnect Queue` is a local configuration selector, under the device's
configuration entities. Set it to `On (60 minutes)` before relying on it. If the
PS240 Wi-Fi is down, selecting `Self-Gen/Zero Export` stores one request for up
to 60 minutes. Once the integration has reconnected and received stable battery
data, it sends the Self-Gen restore once and verifies the acknowledgement.

Selecting any other manual operating mode cancels the queued request. The queue
never replays Charge, Discharge or Feed, and it is completely separate from the
view-only Agile Proposed Plan.

### Restart the data logger locally

The device's configuration entities include `Restart Data Logger` and
`Automatic Data Logger Restart`. The button sends one restart immediately over
the existing local TCP connection. The switch is off by default; when enabled,
it persists the choice and repeats the restart every three hours while Home
Assistant is running. Turning the switch off cancels the pending restart.

The restart applies to the Wi-Fi/BLE data logger, not the PS240 battery power
electronics. Its local connection should disappear briefly after each command
and polling will reconnect automatically. Do not use the control during a
firmware update or while changing the logger's network settings.

### Recover from sustained PS240 Wi-Fi loss

<img src="images/card.png" alt="Wi-Fi loss recovery card showing battery availability, current and next recovery channel, poll failures, grace period, and last attempt result" width="560">

*The Wi-Fi loss recovery card, shown here under the Cosy plan card: battery
availability, current and next recovery channel, poll failures against the
6-poll trigger, the grace period, and the last attempt result.*

The optional **Wi-Fi Loss Recovery** controller is intended for the tested
Linksys SPNMX56TB/Velop JNAP interface. Configure the Linksys router address and
local administrator password under **Settings → Devices & services → AFERIY
PS240 Agile → Configure**, then enable the device's **Wi-Fi Loss Recovery**
switch. The password is used only for local HTTPS requests from Home Assistant;
it is never exposed as an entity attribute or included in diagnostics.

The controller does nothing during the integration's five-poll last-known-data
hold. If the sixth consecutive poll fails and the battery becomes unavailable,
its **Wi-Fi Recovery Grace Period** begins. Set this number entity from 0 to 60
minutes; 0 changes the channel immediately. If valid battery telemetry returns
during the grace period, the pending router change is cancelled. Otherwise it
reads the current 2.4 GHz radio configuration and makes one verified change:
channel 6 becomes 11, or channel 11 becomes 6. SSID, password, security, channel
width, 5 GHz settings, and split-SSID/band-steering state are preserved.

Recovery is off by default and fails closed if the router is not Linksys, does
not advertise the required WirelessAP4 service, rejects authentication, or is
using a channel other than 6 or 11. Only one change is attempted per outage and
a one-hour cooldown survives Home Assistant restarts. A wired Home Assistant
connection is recommended so changing the 2.4 GHz radio cannot interrupt the
controller itself.

For a dedicated dashboard area, register this JavaScript module under
**Settings → Dashboards → Resources**:

```text
/aecc_battery_static/aferiy-wifi-recovery-card.js?v=1.8.32
```

Then add **AFERIY Wi-Fi Loss Recovery** from the card picker, or use:

```yaml
type: custom:aferiy-wifi-recovery-card
title: Wi-Fi loss recovery
```

With multiple AFERIY entries, add the matching switch explicitly:

```yaml
type: custom:aferiy-wifi-recovery-card
entity: switch.your_battery_wifi_loss_recovery
grace_entity: number.your_battery_wifi_recovery_grace_period
```

System-level readings are reported through the master. System Average Battery SOC is the main multi-unit SOC source and matches the behaviour shown in the AEC Cloud app.

The integration creates generic `Battery 1 SOC`, `Battery 2 SOC`, and similar entities from the local `Storage_list` entries reported by the master. This avoids tying dashboards to a particular serial number when a unit is replaced.

After adding, removing, or replacing a battery/inverter, restart Home Assistant or reload the integration so the individual battery entity list is rebuilt from the master. The Battery Capacity preset does not control battery identification.

## Smart Overnight Charging

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

## Dashboard card

The integration includes a bundled **AFERIY Overnight Plan** Lovelace card that
shows the smart overnight target, battery capacity, demand versus solar balance,
Pre-Sunrise Need, Post-Sunset Need, useful solar time, forecast confidence, and
SMART History completeness. It also shows expected reserve before the next
off-peak window and any SMART forecast/demand tuning that has been applied.

![AFERIY Overnight Plan dashboard card](images/aferiy-overnight-plan-card.png)

To make it available in Home Assistant's card picker:

1. Restart Home Assistant after installing or updating the integration.
2. Add dashboard resource `/aecc_battery_static/aferiy-overnight-plan-card.js?v=1.8.32`
   as a JavaScript module.
3. Edit a dashboard, choose Add card, switch to By card, and search for
   `AFERIY Overnight Plan`.

See [Dashboard Card](dashboard-card.md) for manual YAML and optional entity
overrides.

Local schedule-slot registers mirrored from the AEC Cloud app were tested and
behaved as immediate commands on the PS240, so they are not exposed as normal
controls. The integration-owned scheduler instead performs the timing in Home
Assistant and sends the same proven local Charge, Idle, and Self-Gen commands.

## Solar clipping and export

The PS240 can clip or hold back surplus PV when the battery is full or when the system is running in zero-feed behaviour.

Bypassing this PV clipping has been possible in testing, but the mode switching became unreliable. The current self-consumption switching is deliberately conservative because it reliably returns the battery to a safe local operating mode after charging or idling.

At the moment, bypassing clipping/export reliably is not supported by this integration. It may become possible in the future, but it may also need a firmware or app/API update from AFERIY before it can be made stable.

## PV surplus charge trigger

This setting is useful when the AFERIY system shares the same electrical system
with an unmanaged micro-inverter or another PV source that it does not directly
control.

As soon as your Smart Meter (usually Shelly) sees that you are exporting more than your set value
between `0 W` and `50 W`, it tells your home batteries to ramp up and start
charging from the extra energy.

Having a small buffer gives the system a stable threshold to trigger clean,
sustained battery charging without constantly hunting or "chattering" around
zero.

## Experimental Feed mode

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

## Output limit notes

For Agile operation, AC charging is confirmed at up to 1200 W and CT-controlled
output to the house is confirmed at up to 1000 W. Agile peak operation remains
Self-Gen/Zero Export, so the battery follows actual household demand rather than
receiving a fixed 1000 W discharge command. Other higher-power manual modes and
output-register behaviour remain experimental.
