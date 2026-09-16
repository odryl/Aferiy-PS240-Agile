# Octopus Agile implementation

## Current safety stage: guarded opt-in beta

The integration reads BottlecapDave Octopus Energy current-day and next-day
rate event entities, publishes a Proposed Plan, and exposes an operating-state
recommendation. It remains view-only until the user explicitly turns on the
matching **Agile Automated Control** or **Cosy Automated Control** switch. Both
toggles always start Off after an integration or Home Assistant restart.

The planner enforces these invariants:

- 1200 W confirmed AC grid-charge limit (0.6 kWh per 30-minute period)
- 1000 W maximum CT-controlled household supply used by discharge planning
  (0.5 kWh per 30-minute period)
- no fixed discharge command; peak supply always preserves Self-Gen/Zero Export
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

When Cosy is selected, the validated prices are presented with a fixed tariff
schedule: Charge-to-target at 04:00-07:00, 13:00-16:00, and 22:00-00:00, with
CT-controlled Self-Gen/Zero Export between them at 00:00-04:00, 07:00-13:00,
and 16:00-22:00. Live PV takes priority over grid charge, and reaching target SOC
changes the cheap-period recommendation to Idle.
An optional Available PV power entity can override curtailed PS240 PV readings
for that target-reached decision. A fresh W/kW estimate must exceed live house
demand by at least 50 W before Self-Gen is retained instead of Idle.
The target for each cheap period is sized from configured capacity and reserve,
assuming no more than 850 W (0.425 kWh per half-hour) can be supplied until the
next cheap window. The target is capped by the existing Charge Limit control,
and insufficient usable capacity is exposed as a cover shortfall rather than hidden.

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
feedback is the live demand-following and zero-export control; the Agile
executor preserves that loop rather than replacing it with a fixed discharge
command. Manual pre-peak charging is an external action, not proof that the
shadow plan executed. Schema-v3 exports therefore include operating mode,
connection freshness, local-command context, and the shadow decision so those
samples can be classified separately.

The Agile operating state machine locks upcoming charge/discharge actions before
their half-hour boundary. Cosy instead selects its exact current cheap, standard,
or peak period directly and may change its decision on any poll. It keeps
Self-Gen while useful PV is present, permits Idle only after PV has remained
negligible for 15 minutes and a later selected discharge remains, and recommends
Self-Gen on stale telemetry, invalid rates, or reserve protection. Planned grid
charging is also deferred when useful live PV is already present or the target
SOC has been reached.

When explicitly enabled, the guarded controller requires two distinct healthy
polls before starting Charge or Idle, caps AC Charge at 1200 W, constrains custom
commands to a maximum 30-minute recoverable window within the selected period,
and verifies every register write. Profitable discharge always selects
Self-Gen/Zero Export so the PS240 CT loop follows household load; fixed
Discharge and Feed are forbidden.

Each tariff has a separate controller toggle. The controller interlocks against
the legacy overnight scheduler, the wrong selected tariff, the other rate-plan
controller, incomplete storage topology, stale telemetry, and invalid decisions.
Turning it off or making a manual mode selection restores Self-Gen. A persisted
pending-restore marker survives restart without restoring the toggle itself,
allowing an interrupted custom command to be cleared after the next healthy
connection. The marker must be successfully persisted before any custom
command is sent; a storage failure inhibits the command.

## Data flow

1. The Octopus Energy integration updates its current-day or next-day rate event entity.
2. The AFERIY plan sensor notices the Home Assistant state update.
3. Rate periods are parsed and validated as timezone-aware 30-minute records.
4. When both days exist, tomorrow's refill prices and Today's projected ending
   SOC join the two daily views into one rolling horizon.
5. Cheapest periods before 16:00 are selected to reach the target SOC.
6. Highest-value periods between 16:00 and 22:00 are selected for household protection.
7. The operating-state sensor converts the plan and live telemetry into a
   recommendation, retaining actions locked before their boundary.
8. If explicitly enabled, the guarded controller applies the recommendation
   through its interlocks, confirmation debounce, and verified command path.
9. Home Assistant updates the Today/Tomorrow plan sensors and dashboard card.

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

## Remaining beta validation

The initial controller now provides:

- explicit user opt-in with a prominent off switch
- stale-rate and stale-SOC interlocks
- minimum price-spread and round-trip-efficiency checks
- command acknowledgement and post-command verification
- device-slot-bounded command end times plus restart recovery that returns safely
  to Self-Gen/Zero Export
- a complete controller audit context in schema-v3 exports

The following remain follow-up improvements rather than permission to weaken
the existing gates:

- provider-neutral timestamped solar forecast ingestion (live PV inhibition is
  already enforced)
- per-period Agile demand profiles learned directly from Home Assistant Recorder
- configurable daily cycle/cost ceilings
- longer live-command validation across sunny, cloudy, reconnect, midnight,
  restart, and newly expanded PV-array conditions

The conservative Agile power limit and bounded command window are asserted
immediately before every automated custom-mode write.
