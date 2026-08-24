# Octopus Agile implementation

## Current safety stage: shadow planning

The integration reads BottlecapDave Octopus Energy current-day and next-day
rate event entities, publishes a Proposed Plan, and exposes a shadow operating
state for a future supervised controller. It does not send any Agile control
command to the battery. The `control_enabled` attribute is always `false`.

The planner enforces these invariants:

- 800 W conservative Agile charge/discharge command limit
- 0.4 kWh maximum discharge in any 30-minute Agile period
- 800 W conservative grid-charge planning limit
- 10% device reserve by default, taken from the live discharge-limit register
- 100% target before 16:00 by default
- price-aware protection from 16:00 to 22:00, capped by the anonymized
  half-hour household net-demand profile after measured PV
- discharge only when the avoided import rate exceeds delivered replacement cost by at least £0.03/kWh
- exact expected-date and DST-aware consecutive coverage for every actionable
  future period through the configured protection end (elapsed and post-window
  current-day periods may be omitted by the source)
- no selection of elapsed charging or discharging periods
- malformed, overlapping, incomplete, or missing rate data cannot cause control
- the source must be an entity owned by the Octopus Energy integration with
  MPAN, meter serial, and an Agile tariff code matching its counterpart entity
- non-finite battery, efficiency, price, or demand inputs invalidate the plan
- missing periods in a supplied demand profile contribute zero planned demand
- live SOC below reserve is recoverable: recharge includes the reserve deficit,
  while projected discharge remains zero until reserve is restored

Before next-day rates are published, Tomorrow's plan assumes the battery begins
at its reserve SOC. Once both valid days are available, Today values discharge
against enough of tomorrow's cheapest pre-deadline periods to refill the
maximum feasible discharged energy. Tomorrow then begins at Today's projected
SOC at the protection end. Today's plan uses live System Average Battery SOC
when available. Both plans use the configured battery capacity.

BottlecapDave rate values are treated as GBP/kWh. Raw consumption records are
not stored in the repository. The twelve retained 16:00-22:00 values are
anonymized net-demand medians recalibrated from schema-v2 shadow exports. They
subtract measured PV and remain an advisory demand and value model. When
Self-Gen/Zero Export is active, its CT
feedback is the live demand-following and zero-export control; any future Agile
executor must preserve that loop rather than replace it with a fixed discharge
command. Manual pre-peak charging is an external action, not proof that the
shadow plan executed. Schema-v3 exports therefore include operating mode,
connection freshness, local-command context, and the shadow decision so those
samples can be classified separately.

The shadow state machine locks upcoming charge/discharge actions before their
half-hour boundary. It keeps Self-Gen while useful PV is present, permits Idle
only after PV has remained negligible for 15 minutes and a later selected
discharge remains, and recommends Self-Gen on stale telemetry, invalid rates,
or reserve protection. Those are recommendations only.

## Data flow

1. The Octopus Energy integration updates its current-day or next-day rate event entity.
2. The AFERIY plan sensor notices the Home Assistant state update.
3. Rate periods are parsed and validated as timezone-aware 30-minute records.
4. When both days exist, tomorrow's refill prices and Today's projected ending
   SOC join the two daily views into one rolling horizon.
5. Cheapest periods before 16:00 are selected to reach the target SOC.
6. Highest-value periods between 16:00 and 22:00 are selected for household protection.
7. The shadow sensor converts the plan and live telemetry into a view-only
   proposed operating state, retaining actions locked before their boundary.
8. Home Assistant updates the Today/Tomorrow plan sensors and dashboard card.

## Solar forecast follow-up

The Agile fallback now subtracts historical measured PV from its half-hour
demand profile, and the shadow sensor discovers solar forecast config entries
selected in the Home Assistant Energy Dashboard. It does not yet consume their
timestamped forecast values. The next provider-neutral stage should consume
the solar forecast selected in Home Assistant's Energy Dashboard (including
Forecast.Solar or compatible providers), convert its timestamped Wh forecast to
the same local half-hour buckets, and fail back to the current demand-only plan
when the forecast is missing or stale. Forecast energy must be capped by
expected demand unless an export-price model is added; otherwise surplus PV
would incorrectly increase the value of battery discharge.

If there is exactly one Octopus import meter, rate entities are discovered
automatically. Multi-meter installations must select the two import event
entities in the AFERIY integration options. Export rate entities are never
auto-selected.

## Before control can be enabled

Automatic control should remain a later, separately reviewed stage. It needs:

- a successful review of the shadow operating-state decisions
- explicit user opt-in with a prominent off switch
- stale-rate and stale-SOC interlocks
- minimum price-spread and round-trip-efficiency checks
- command acknowledgement and post-command verification
- hardware-bounded command end times plus restart recovery that returns safely
  to Self-Gen/Zero Export
- per-period demand forecasts learned from Home Assistant Recorder
- solar forecasts and a user-selectable reserve policy
- a daily cycle/cost ceiling and a complete audit log

No control stage should be merged until the conservative Agile power limit and
hardware-bounded command end time are asserted immediately before every write.
