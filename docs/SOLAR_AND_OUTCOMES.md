# Solar timing and daily outcomes

These additions apply to the Agile and Cosy plan card. They are included in
version 1.8.33 and require an integration update before their entities appear.

## Forecasts change timing, not targets

Choose your solar forecast provider under Home Assistant **Settings → Dashboards
→ Energy**, in the solar source configuration. The **Planning Solar Forecast**
sensor reads only those providers, deduplicating repeated config entries. It uses
the same `async_get_solar_forecast` Energy platform hook as Home Assistant and
normalizes `wh_hours` values from Wh to kWh. Supported providers are those that
implement that hook, such as Forecast.Solar and compatible Solcast versions.

The integration reads the provider cache every 15 minutes. Missing providers,
invalid values, gaps before the deadline, or a retrieval older than 45 minutes
cannot initiate a forecast wait. The card distinguishes retrieval time from the
provider's forecast issue time, which this common API does not expose.

A usable forecast can select a bounded **Forecast Solar Wait** in Idle during a
paid charging opportunity. The latest safe grid start is calculated from the
**entire live SOC deficit with zero future solar assumed**, charging efficiency,
and the permitted charging power. It reserves an extra five minutes or ten
percent of charging time, whichever is larger, for controller confirmation and
charging variability. Targets, reserves, and charge limits remain unchanged.

- **Cosy:** the deadline is the end of the current cheap operating period, before
  the following expensive block. Forecast waits work whenever a usable provider
  is configured. Daylight Flex remains an additional afternoon option when no
  usable forecast is available.
- **Agile:** only time inside the current reserved charge command is available;
  the wait cannot move charging into another price slot or rely on unpublished
  future rates. A short command's early end is respected.
- **Already charging:** AC charging continues towards target, rather than
  alternating between charge and wait as SOC rises.
- **Below reserve:** recovery charging takes priority over solar waiting.
- **Booked Happy Hours:** forecasts do not defer free-power charging.

Live solar can reduce the measured deficit and leave more waiting time. It is
never credited to the target before it arrives. If the deficit no longer fits,
the controller requests charging immediately and reports that the target is
not reachable in the remaining time. Device limits, outages and unexpectedly
slow charging can still prevent a target; this is a conservative scheduling
calculation, not a hardware guarantee. All existing controller opt-in, connection,
mode, command bounds, confirmation and restore protections remain in force.

Cost and energy projections retain the zero-forecast schedule baseline. They do
not claim to predict actual solar capture or measured savings. The card explains
this alongside the current forecast and grid-backup deadline.

## What happened

The **Daily Plan Outcomes** sensor starts tracking after installation and retains
14 local days. The card displays the latest seven, with detail for:

- observed AC charging energy;
- estimated purchased charging, priced energy and charging cost;
- the first valid remaining-day charging plan, frozen at capture time, alongside
  AC energy observed since that capture;
- target SOC, observed deadline SOC and achieved/missed/unknown outcomes;
- solar-wait minutes while the controller is actively executing a wait;
- controller interruptions, rejected activation and recent state changes;
- observation coverage and storage failures.

Energy is integrated from live power samples only across fresh consecutive polls
at most 90 seconds apart. Duplicate polls, outages and restarts never contribute
invented energy. Midnight and tariff boundaries split the observations; local
23- and 25-hour days use their actual duration. A target with no continuous
observation across its deadline is **unknown**, not missed or achieved. Deadline
SOC may be observed up to 90 seconds after the deadline; its timestamp is retained.
Targets are observed even with automation Off, and that state is disclosed.

AC charging can use another inverter's solar. Without a dedicated battery import
meter, purchased charging is an **upper-bound allocation**:
`min(AC charging power, positive site grid import)`. Other household loads can
consume some of that import. This estimate is labelled separately from measured
AC energy. Missing grid telemetry and unknown prices are exposed rather than
silently assigned zero. Charging cost uses known slot prices, with booked Happy
Hour credit disclosed separately. It is not a reconciled electricity bill.

Coverage is measured against the local day so far (the full local day for past
days). The frozen plan may have been captured part-way through a day, and the
card names that time. Later replans do not rewrite it. **No realised savings are
calculated**: there is no agreed counterfactual electricity-use baseline.

History is local, separated per battery configuration entry and saved to Home
Assistant storage every five minutes and on orderly shutdown/unload. An abrupt
power loss can lose the most recent unsaved observations. History is not copied
from old JSONL exports; those remain an independent detailed trial record.

## Card setup

The existing `custom:aferiy-agile-plan-card` discovers both new sensors for the
same battery. For renamed entities or multiple installations, set them explicitly:

```yaml
type: custom:aferiy-agile-plan-card
today_entity: sensor.your_battery_agile_proposed_plan_today
forecast_entity: sensor.your_battery_planning_solar_forecast
outcomes_entity: sensor.your_battery_daily_plan_outcomes
```

Refresh the card resource after updating. **Solar outlook · targets come first**
explains the policy; **What happened · daily history** opens the observations.

## Validation

Automated scenarios cover provider failure, malformed/missing forecast periods,
fixed targets, latest-safe-start transitions, shortened Agile command windows,
cloudy/sunny simulations, reserve recovery, restart gaps, midnight price changes,
clock-change days, storage errors and per-battery card discovery. Supervised
Home Assistant and hardware validation remains outstanding; supervise the first
enabled runs after updating.

API references: [Home Assistant Energy platform discovery](https://github.com/home-assistant/core/blob/2024.8.0/homeassistant/components/energy/websocket_api.py),
[Forecast.Solar's Energy adapter](https://github.com/home-assistant/core/blob/dev/homeassistant/components/forecast_solar/energy.py),
and [Home Assistant's forecast bucket rendering](https://github.com/home-assistant/frontend/blob/dev/src/panels/lovelace/cards/energy/energy-solar-graph-data.ts).
