# Octopus Agile implementation

## Current safety stage: shadow planning

The integration reads BottlecapDave Octopus Energy current-day and next-day
rate event entities and publishes a Proposed Plan. It does not send any control
command to the battery. The `control_enabled` plan attribute is always `false`.

The planner enforces these invariants:

- 800 W maximum system discharge, never per module
- 0.4 kWh maximum discharge in any 30-minute Agile period
- 800 W conservative grid-charge planning limit
- 10% device reserve by default, taken from the live discharge-limit register
- 100% target before 16:00 by default
- price-aware protection from 16:00 to 22:00, capped by the anonymized half-hour household demand profile
- discharge only when the avoided import rate exceeds delivered replacement cost by at least £0.03/kWh
- exact expected-date and DST-aware consecutive rate coverage
- no selection of elapsed charging or discharging periods
- malformed, overlapping, incomplete, or missing rate data cannot cause control
- the source must be an entity owned by the Octopus Energy integration with
  MPAN, meter serial, and an Agile tariff code matching its counterpart entity
- non-finite battery, efficiency, price, or demand inputs invalidate the plan
- missing periods in a supplied demand profile contribute zero planned demand

Tomorrow's plan assumes the battery begins at its reserve SOC. This is
deliberately conservative. Today's plan uses live System Average Battery SOC
when available. Both plans use the configured battery capacity.

BottlecapDave rate values are treated as GBP/kWh. The supplied raw consumption
records are not stored in the repository; only twelve anonymized 16:00-22:00
half-hour averages are retained as the initial demand model.

## Data flow

1. The Octopus Energy integration updates its current-day or next-day rate event entity.
2. The AFERIY plan sensor notices the Home Assistant state update.
3. Rate periods are parsed and validated as timezone-aware 30-minute records.
4. Cheapest periods before 16:00 are selected to reach the target SOC.
5. Highest-value periods between 16:00 and 22:00 are selected for household protection.
6. Home Assistant updates the Today/Tomorrow Proposed Plan sensors and dashboard card.

If there is exactly one Octopus import meter, rate entities are discovered
automatically. Multi-meter installations must select the two import event
entities in the AFERIY integration options. Export rate entities are never
auto-selected.

## Before control can be enabled

Automatic control should remain a later, separately reviewed stage. It needs:

- at least two weeks of saved shadow plans and actual outcomes
- explicit user opt-in with a prominent off switch
- stale-rate and stale-SOC interlocks
- minimum price-spread and round-trip-efficiency checks
- command acknowledgement and post-command verification
- restart recovery that returns safely to Self-Consumption
- per-period demand forecasts learned from Home Assistant Recorder
- solar forecasts and a user-selectable reserve policy
- a daily cycle/cost ceiling and a complete audit log

No control stage should be merged until the 800 W system-wide limit is also
asserted immediately before every hardware write.
