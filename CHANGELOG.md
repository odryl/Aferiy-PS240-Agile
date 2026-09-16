# Changelog

## 1.8.32

- Remove the inherited Buy Me a Coffee funding link so the repository no longer
  solicits donations for the upstream fork's maintainer.
- Point the Home Assistant device page link and the Overnight Plan card's
  documentation link at this fork instead of the upstream project, so in-product
  links reach the documentation that matches the installed version.
- Show the device Manufacturer as **odryl**, making it clear that this is a fork
  rather than vendor or upstream support. Attribution for the local protocol
  implementation remains in the README, the LICENSE, and the code comments.

## 1.8.31

- Plan Octopus **Weekend Happy Hours** inside the Cosy Octopus schedule. Booked
  free-power windows are treated as zero-cost grid charging, so the battery
  charges towards the configured target even when the window falls in a peak or
  standard band.
- Read the booked windows from BottlecapDave's Octopus power-up session events
  entity, with automatic discovery when exactly one exists and a new optional
  **Octopus Weekend Happy Hours power-up event** setting to choose it explicitly.
- Publish `happy_hour_windows`, `scheduled_free_energy_periods`,
  `happy_hour_grid_charge_kwh`, and `estimated_happy_hour_credit_gbp` on the
  Proposed Plan, and show the free window as credited-back import on the Cosy
  card instead of a billed cost.
- Keep free import out of the billed charge cost and the replacement rate, so
  Happy Hour energy never inflates the estimated net saving or average charge
  price.
- Report skipped Octopus sessions and ambiguous multi-account discovery through
  `happy_hour_warnings` and `happy_hour_source` instead of failing silently, and
  show the Happy Hour credit and any warnings in the card's plan details.
- Restructure the README as a concise project landing page led by the Cosy and
  Agile planners, with the deep device, tariff, and operational detail moved to
  `docs/COSY_PLANNER.md`, `docs/AGILE_PLANNER.md`, and
  `docs/ADVANCED_CONFIGURATION.md`.
- Add a dashboard screenshot to the README and the card guides, showing the
  Cosy plan card next to live battery telemetry and the Wi-Fi loss recovery
  card.

## 1.8.30

- Redesign the Cosy Octopus Battery Plan around the current action, live battery SOC, next charge target, and next tariff period.
- Add Today/Tomorrow tabs, a compact seven-period schedule with earlier periods folded away, and expandable cost and planning details.
- Add explicit Automatic Control and Daylight Flex controls through the existing guarded switches, with unavailable, pending, and error handling.
- Highlight advisory mode, controller inhibition, stale telemetry, missing rates, and battery capacity shortfalls. Never display missing numeric data as zero.
- Preserve open sections and keyboard focus during live updates; scope styling to the card and support narrow dashboard columns and Home Assistant themes.
- Keep Agile’s existing half-hour view and add automated frontend behavior checks.

## 1.8.29

- Replace Cosy's 48-row half-hour card schedule with seven meaningful cheap,
  standard, and peak tariff/operating periods. Highlight the live period and
  show its price, target, purpose, duration, and any capacity shortfall.
- Publish validated `cosy_periods` plan data and select the active Cosy action
  directly from its exact local-time period. Half-hour records remain internal
  for Octopus validation and short, recoverable device-command renewal only.
- Normalize UTC Octopus slot timestamps into Home Assistant local time before
  constructing device schedules, while retaining Agile's detailed half-hour
  price and action display.

## 1.8.28

- Fix false **Solar Charge Deferred** decisions when PV is 0 W. The planner
  no longer assumes that a difference between asynchronous total-charge and
  AC-charge registers must be solar power.
- Require at least 50 W of measured live PV, including valid Energy Dashboard
  solar power sources, before solar can defer a planned grid charge.

## 1.8.27

- Change **Cosy Daylight Flex** to remain Idle while the live Charge Limit
  deficit can still be recovered before 16:00, allowing any available PV to
  charge the battery instead of requiring a solar threshold or using Self-Gen.
- Recalculate the latest safe 1,200 W AC-charge start from live SOC, capacity,
  and charge efficiency on every update. Use only a two-minute command margin
  instead of reserving an entire 30-minute cheap-rate slot.
- Expose the calculated latest grid-charge start and add a regression case for
  a 400 Wh deficit: at 90% efficiency it waits until approximately 15:36 before
  AC charging, unless intervening PV delays or removes the remaining need.

## 1.8.26

- Add an optional **Available PV power entity** setting for a live inverter
  reading or solar "power now" estimate that remains visible when a full
  battery causes the PS240 to curtail its own PV input.
- Publish the combined **Available PV Power** sensor with measured, configured,
  freshness, unit-validation, and source attributes. Estimates older than 45
  minutes, invalid values, and accidental self-references are ignored.
- At a reached Cosy charge target, keep Self-Gen/Zero Export active when the
  valid available-PV estimate exceeds live household demand by at least 50 W;
  otherwise retain Idle. Show the effective available PV and source on the card.

## 1.8.25

- Correct the Cosy 00:00-04:00 phase to CT-controlled Self-Gen/Zero Export so
  energy charged from 22:00-00:00 supplies the house until the 04:00 cheap
  window, down to the configured Discharge Limit.
- Keep Idle only as the live cheap-period hold after a calculated target has
  been reached. The fixed Cosy plan now contains 16 charge and 32 Self-Gen
  half-hours, with no scheduled Idle periods.

## 1.8.24

- Add a persistent, opt-in **Cosy Daylight Flex** control for the 13:00-16:00
  cheap period. It can use CT-controlled Self-Gen while at least 100 W of live
  or inferred solar is present.
- Continuously calculate whether the configured Charge Limit remains reachable
  by 16:00 from live SOC, battery capacity, 90% charge efficiency, and the
  guarded 1,200 W system charge ceiling. Preserve one full 30-minute cheap-rate
  safety slot and start charging immediately when the margin is exhausted.
- Show the toggle state and current catch-up margin on the Agile/Cosy dashboard.
  Grid charging remains bounded to validated Cosy cheap slots and can never be
  extended into the peak-price period by Daylight Flex.

## 1.8.23

- Use the existing **Charge Limit** control as the upper SOC boundary for both
  Today and Tomorrow Agile/Cosy plans, including rolling-horizon calculations.
- Replan when the Charge Limit changes and expose the effective limit and its
  source in plan attributes.
- Clamp every automated charge command to the configured Charge Limit as a
  final safety check. A 20%-90% operating range now produces Cosy targets of
  90%, 90%, and 78% for the three cheap periods on a 5.874 kWh battery.

## 1.8.22

- Add a separate opt-in **Cosy Automated Control** switch, leaving the Agile
  toggle restricted to Agile and preventing the two controllers from running
  together.
- Size each Cosy cheap-period SOC target from the configured battery capacity,
  reserve, and a conservative maximum battery supply of 850 W (0.425 kWh per
  half-hour) until the next cheap period. Charge only below that target;
  otherwise hold Idle.
- Show the calculated Charge/Idle target, maximum-output assumption, required
  cover, and any physical capacity shortfall on the Cosy plan while preserving
  the existing live-PV, topology, bounded-command, and restart safeguards.

## 1.8.21

- Replace Cosy's generic Agile optimisation with a fixed daily operating plan:
  Charge-to-target at 04:00-07:00, 13:00-16:00, and 22:00-00:00; Idle at
  00:00-04:00; and CT-controlled Self-Gen/Zero Export at 07:00-13:00 and
  16:00-22:00.
- Let the existing opt-in guarded controller execute the Cosy schedule while
  retaining target-SOC, live-PV, stale-data, topology, command-window, and
  restart-recovery protections. Fixed-window Overnight Charge must remain Off.
- Show Cosy Charge, Idle, and Self-Gen phases directly on the bundled Agile
  card alongside the tariff's validated half-hour prices.

## 1.8.20

- Extend the Octopus rate-source validator and Proposed Plan sensors to accept
  matching Cosy current-day and next-day import-rate events when Cosy is the
  selected Energy Tariff.
- Reuse the validated half-hour optimizer to show Cosy prices and proposed
  charge/discharge periods, costs, avoided import, and savings in the bundled
  Agile card.
- Make the card tariff-aware and clearly retain guarded automated control as
  Agile-only; Cosy plans remain advisory, with the separate 04:00-07:00 fixed
  scheduler available through Overnight Charge.

## 1.8.19

- Add Cosy Octopus as an Energy Tariff option using the official 04:00-07:00
  morning dip for the overnight charge-to-target scheduler.
- Expose all three Cosy cheap periods and the 16:00-19:00 peak period as tariff
  attributes, and show the current Cosy Cheap, Peak, or Day band on the bundled
  Overnight Plan dashboard card without hard-coding regional unit prices.

## 1.8.18

- Keep the Wi-Fi recovery regression tests independent of Home Assistant's
  runtime `aiohttp` dependency so the repository's minimal CI test job passes.

## 1.8.17

- Add opt-in **Wi-Fi Loss Recovery** for compatible Linksys routers. After the
  PS240 crosses the existing five-poll hold into actual unavailability, it
  alternates the 2.4 GHz radio between channel 6 and 11 once per outage,
  verifies the router-reported result, and waits for battery telemetry.
- Preserve all existing radio/security and split-SSID settings, validate local
  Linksys WirelessAP4 access before enabling, persist a one-hour cooldown, and
  keep router credentials and Wi-Fi passphrases out of entities, logs, and
  diagnostics.
- Add a dedicated AFERIY Wi-Fi Loss Recovery dashboard card with opt-in control,
  channel, poll-failure, cooldown, and recovery status.
- Add a persisted 0–60 minute Wi-Fi recovery grace period. Valid battery
  telemetry during the wait cancels the pending router channel change, while a
  value of 0 preserves immediate recovery.

## 1.8.16

- Add an opt-in **Agile Automated Control** switch for a guarded beta control
  stage. It starts Off after every integration/Home Assistant restart and only
  executes Charge, bounded Idle, or CT-controlled Self-Gen decisions; it never
  sends fixed Discharge or Feed commands.
- Require two fresh telemetry polls before custom commands, interlock against
  the fixed-window overnight scheduler and non-Agile tariffs, verify writes,
  and persist a recovery marker so an interrupted custom command is restored
  to Self-Gen after reconnect.
- Defer planned grid charging while useful live PV is present or the target SOC
  has already been reached. Record the controller state and audit context in
  schema-v3 exports and show it on the Agile plan card.
- Model the confirmed asymmetric system limits: up to 1200 W for AC charging
  and up to 1000 W of CT-controlled Self-Gen supply to household demand. Bump
  the planner revision so new exports can be separated from earlier 800 W plans.

## 1.8.15

- Add a view-only Agile Shadow Operating State sensor that locks upcoming
  half-hour actions before their boundary and recommends Solar Self-Gen,
  Planned Charge, Post-solar Hold, Peak Self-Gen, reserve protection, or a
  fail-safe state without sending battery commands.
- Replace the total-demand profile with schema-v2 net-demand medians that
  subtract measured PV, while exposing configured Energy Dashboard solar
  forecast providers for the next forecast-ingestion stage.
- Treat the brief midnight Octopus entity rollover as Waiting rather than
  Invalid, and clarify that 800 W is an Agile command limit rather than a
  device-wide Self-Gen ceiling.
- Add connection freshness and shadow decisions to schema-v3 exports. Rotate
  the active JSONL at 8 MiB into timestamped gzip archives so long-running
  logging remains manageable without deleting trial history.

## 1.8.14

- Treat live SOC below the configured reserve as a recoverable planning state:
  plan sufficient recharge, expose the reserve deficit, and prohibit discharge
  unless the projected SOC first clears the reserve.
- Recalibrate the advisory 16:00-22:00 demand profile to robust medians from
  the first 11-12 days of half-hour shadow exports, reducing optimistic
  discharge and savings estimates.
- Add planner/profile revision metadata and cumulative PV, charge, and
  discharge energy counters to schema-v2 shadow exports for cleaner outcome
  comparisons across upgrades.
- Record operating mode, last local command, commanded direction, and overnight
  scheduler state so Self-Gen/Zero Export operation and manual charging can be
  separated from Agile shadow recommendations.

## 1.8.13

- Persist expanded Agile price tables across equivalent Lovelace configuration
  calls, meaningful plan refreshes, and card-element recreation within the same
  browser session. Ignore timestamp-only plan entity updates.

## 1.8.12

- Exclude the 23:30-midnight period from pre-16:00 charging and next-day
  replacement pricing; its `00:00` end clock previously crossed a date boundary
  and could be mistaken for a pre-deadline slot.
- Keep opened half-hour price tables expanded across Agile plan refreshes and
  avoid rebuilding the card for unrelated Home Assistant state updates.
- Couple Today and Tomorrow into a rolling Agile planning horizon as soon as
  tomorrow's complete rates are published. Tonight's discharge is valued
  against the cheapest sufficient set of tomorrow refill periods, and
  Tomorrow starts from Today's projected protection-end SOC.
- Keep the current independent-day fallback when tomorrow's rates are absent,
  stale, malformed, incomplete, or not for the immediately following date.

## 1.8.11

- Added a local `Restart Data Logger` button that sends datalogger parameter
  `32 = 1` over the existing Wi-Fi TCP connection. A disconnect immediately
  after dispatch is expected while the logger reboots.
- Added an opt-in, persisted `Automatic Data Logger Restart` switch. When on,
  it repeats the same local restart every three hours; it is off by default and
  exposes its next/last dispatch details as entity attributes.
- Cancel the integration's background tasks cleanly when an entry is unloaded.

## 1.8.10

- Added an opt-in, persisted Self-Gen reconnect queue for manual use when the
  PS240 Wi-Fi is unavailable. It holds one `Self-Gen/Zero Export` request for
  60 minutes, waits for healthy/stable local polling after reconnect, sends it
  once, and records the verified result.
- New manual requests, queue disablement, and expiry cancel the pending action.
  Charge, Discharge, Feed, and all Agile Proposed Plan actions are never queued.

## 1.8.9

- Expanded Agile trial exports with battery SOC/capacity, charge/discharge,
  grid/PV and household-demand measurements, supporting a complete historic
  plan-versus-outcome analysis after a week or two of half-hour samples.

## 1.8.8

- Added `export_agile_plan`, a manual or automation-friendly service that
  appends redacted, read-only shadow-plan snapshots to a local JSON Lines file
  for trial analysis.

## 1.8.7

- Expose the Battery Capacity selector whenever the Agile planner is enabled,
  instead of hiding this essential planning input behind Advanced Energy Estimate
  Sensors.

## 1.8.6

- Corrected actionable-rate validation for BottlecapDave's current-day Agile
  events, which can validly end at 23:00. The plan now requires continuous
  source data only through its configured protection end, rather than through
  an unused midnight-to-protection-end tail.

## 1.8.5

- Added validated current and cheapest-remaining Agile price attributes to each
  Proposed Plan, sourced from the same GBP/kWh rate list used by the planner.
- Made the bundled Agile card visually actionable: it highlights the live,
  cheapest and negative-price periods and uses configurable green/amber/red
  price bands compatible with the familiar Octopus Energy Rates Card defaults.
- Treat unpublished or empty Octopus day-rate events as `Waiting for Rates` and
  avoid invalidating today's complete plan solely because tomorrow is not yet
  published; meter/tariff matching still applies as soon as both lists exist.
- Accept a partial current-day rate list when it omits only elapsed periods and
  still covers every future actionable half-hour through midnight; gaps in
  future coverage and incomplete next-day data remain invalid.
- Only require rate coverage through the configured protection end. This accepts
  BottlecapDave's valid 46-slot current-day payloads that end at 23:00 while
  retaining strict validation of every period the plan can charge or discharge.

## 1.8.4

- Added an end-to-end README walkthrough for registering the Agile card,
  creating a dedicated dashboard, adding the card visually or with YAML, and
  selecting useful live battery entities.
- Clarified browser caching, multiple-system entity selection and why the
  fixed-window Overnight Plan card should not be used in Agile mode.

## 1.8.3

- Expanded the Agile dashboard into a user-friendly Today/Tomorrow plan with
  projected SOC, charge and discharge energy, estimated charge cost, avoided
  peak import, replacement cost and net saving.
- Added per-period cost, avoided import and saving attributes plus a collapsible
  view of all half-hour Agile prices.
- Kept every dashboard and planner output explicitly view-only.

## 1.8.2

- Switched HACS downloads to a versioned `aecc_battery.zip` release asset so
  installations do not depend on default-branch archive discovery.
- Added an automated tagged-release workflow that packages the integration
  contents in the directory layout expected by HACS.

## 1.8.1

- Added Octopus Agile as an explicit tariff option and made it the default for
  new or previously unset configurations.
- Moved Agile rate inputs ahead of the legacy fixed-window tariff settings and
  clarified which controls apply to each mode.
- Disabled and safely interlocked fixed-window Smart Overnight Charging while
  Octopus Agile is selected; the Agile Proposed Plan remains view-only.
- Made Custom Off-Peak Start/End entities available only for the Custom tariff.

## 1.8.0

- Added view-only Octopus Agile Proposed Plan sensors for today and tomorrow.
- Added strict Octopus source, Agile tariff, meter, freshness, date, completeness,
  DST and numeric validation.
- Added household-demand-aware price optimization with a hard 800 W total-system
  discharge ceiling and £0.03/kWh minimum estimated saving.
- Added a bundled Agile Proposed Plan dashboard card with explicit partial-period
  energy, average power, command ceiling and duration.
- Added shadow-mode documentation and adversarial regression coverage. Agile
  planning cannot write battery registers in this release.

## 1.7.8

- Preserved the last confirmed complete battery topology when a local poll
  temporarily omits one unit, instead of shrinking the bank and removing its
  Home Assistant entity after only a few polls.
- Restored known Battery SOC entities during setup from DeviceManagement and
  the entity registry, so restarting Home Assistant during a reporting gap
  does not silently rebuild a three-battery installation as two batteries.
- Added diagnostics for incomplete topology, missing-unit count, first-missing
  time, recovery time and outage duration without exposing battery serials.
- Prevented SMART overnight charging from starting a new automatic charge while
  local battery topology is incomplete. Existing locked BMS targets remain
  active and normal end-of-window restoration is retained.
- Expanded regression coverage for temporary omissions, recovery, restart
  handling, entity preservation and the SMART charging interlock.

## 1.7.7

- Hardened multi-unit SOC handling against empty, partial and sudden `0%`
  `Storage_list` snapshots while keeping the last trustworthy readings visible.
- Added confirmed-topology tracking so obsolete higher-numbered Battery SOC
  entities are removed only after a smaller battery list remains stable across
  several successful polls.
- Made Self-Gen/Zero Export explicitly clear the experimental base-feed target
  so Feed mode cannot linger after normal operation is restored.
- Simplified power-flow snapshots to discover the active integration entities
  from Home Assistant instead of relying on installation-specific entity IDs.
- Defined the overnight buffer as protected SOC headroom at useful-solar
  handover, so learned morning demand and negative adaptive corrections cannot
  consume the configured margin above reserve.
- Extended the Charge Power slider down to `200 W` per unit while retaining
  `800 W` as the default for new installations.
- Reused the suspect-frame confirmation period for genuine battery removals and
  expanded public diagnostics with topology progress and acceptance outcomes.
- Removed retired entity implementations and other unused control code, aligned
  package metadata, and expanded regression coverage for topology and register
  safety.

## 1.7.6

- Fixed startup SOC filtering for FOSSiBOT/PS240-compatible units that can briefly
  report an online battery as `0%` while the app and LCD still show the real SOC.
  The integration now rejects that first bad zero instead of writing it into Home
  Assistant history.
- Refreshed Wi-Fi strength and safe device metadata every 30 minutes after a
  successful poll, rather than only at setup/reload.
- Moved Solcast detailed forecast file reads off the event loop and cached them
  for short intervals to reduce dashboard/update load.

## 1.7.5

- Added adaptive SMART Overnight Charging learning for recent heavy mornings,
  so heatwave/AC or other short-term morning demand changes can lift the
  pre-sunrise reserve without adding more dashboard sensors.
- Reduced recorder/status churn from repeated SMART status updates and duplicate
  local control writes.
- Backported the upstream stuck-unavailable recovery fix so a sensor can become
  available again as soon as the device reports a fresh valid value after a
  cleaner hold window expires.

## 1.7.4

- Fixed SMART Overnight Charging so the local charge command uses the locked
  recommended/manual overnight SOC target instead of the normal Charge Limit
  slider. This prevents overnight charging continuing to 100% when Charge Limit
  is set to 100%.
- Improved individual Battery N SOC resilience when the master still reports a
  battery slot but a poll omits that slot's SOC value; the sensor now holds the
  last known value instead of briefly becoming unavailable.
- Added regression tests for the overnight target handoff and individual
  battery SOC hold behaviour.

## 1.7.3

- Added cumulative Energy Dashboard solar reconciliation for additional
  inverters such as Hoymiles. Live power remains responsive while exact energy
  totals correct slower power polling in House Demand history.
- Replaced the separate SMART solar and house-demand scaling sliders with one
  Overnight Buffer slider from 0-20%, defaulting to 3%.
- Kept the existing automatic SMART safeguards on top of the user-set baseline,
  including weak history, incomplete timed data, low solar and close-call days.
- Reduced early-morning solar credit slightly so the pre-sunrise recommendation
  retains a little more battery above the configured minimum SOC.

## 1.7.2

- Added automatic support for additional solar inverters configured in the
  Home Assistant Energy Dashboard. Their live solar power is included in House
  Demand and SMART overnight history without double-counting AFERIY PV.
- Extended SMART History from 14 to 30 days, prioritising the latest 14 accepted occupied days while retaining older days as lighter holiday-resistant fallback history.
- Added visible 35-day Recorder-retention guidance and updated the local Home Assistant configuration to preserve the complete 30-day profile.
- Reduced SMART Recorder-history refresh frequency to hourly to offset the larger history window.
- Fixed SMART History completeness lagging by one day by including the latest complete rolling 24-hour history period.
- Updated the off-peak tariff presets with revised UK tariff windows and added EDF GoElectric 35, EDF E7 Fixed, OVO Simpler Energy E7, Octopus E7, and E.ON Next Pumped Fixed.

## 1.7.1

- Added a user-friendly Wi-Fi Signal sensor showing percentage, quality and raw dBm.
- Removed the unused SMART Overnight Accuracy and SMART Morning Accuracy sensors.
- Corrected SMART History completeness so known away or filtered days count as observed history without affecting the demand average.
- Added SMART Solar Forecast and SMART House Demand configuration sliders so users can gently tune the overnight calculation when local behaviour differs from the forecast/history.
- Added expected end-of-peak reserve and SMART tuning visibility to the bundled Overnight Plan card.
- Added rolling SMART overnight re-checks that can raise, but not lower, the locked target during off-peak when the live recommendation materially increases.
- Replaced the simplistic expected reserve calculation with a timed battery simulation that accounts for the battery reaching 100%, clipped solar surplus, and later evening demand.
- Documented the low-solar behaviour: use cheap-rate energy when useful, while leaving room for forecast solar.

## 1.7.0

- Added experimental Feed mode to Operating Mode using the locally discovered base grid-connected feed/discharge register `3026`.
- Added a passive Base Feed Power slider from `0-800 W`; moving the slider only stores the target until Operating Mode is set to Feed.
- Made Self-Gen/Zero Export clear the base feed value so Feed mode does not linger after returning to the normal safe mode.
- Documented that Feed mode is experimental and actual output may differ from the target, especially on systems with smart meter/CT feedback.

## 1.6.4

- Persisted SMART runtime settings across Home Assistant restarts and power cuts, including Overnight Charge mode, Battery Capacity, tariff preset, custom off-peak times, Manual SOC, and Solar Availability.
- Improved local TCP recovery by forcing a reconnect after empty or invalid poll responses while preserving last known good sensor data during short outages.
- Kept SMART configuration controls visible during temporary TCP failures so local settings do not appear to reset when the battery poll is unavailable.
- Improved SMART overnight planning for close-call and low-solar days by allowing cheap-rate top-up while leaving forecast solar headroom.
- Added extra transparency on the bundled Overnight Plan card for cheap-rate top-up decisions and forecast solar headroom.
- Reduced low-value diagnostic noise and recorder-heavy attributes to keep long-term history leaner.

## 1.6.3

- Added SMART Overnight Accuracy as a diagnostic sensor to review the last completed SMART overnight cycle against the configured minimum SOC plus planned buffer.
- Improved AC Charging Power cleanup so stale AC charge readings are suppressed when PV already explains the observed battery charging.
- Changed SMART history projections to exclude the current in-progress day from the 14-day demand profile.
- Improved the bundled Overnight Plan card so Overnight Status and Tariff update from the local integration entities instead of stale dashboard helpers.
- Rewrote the SMART Overnight Charging README section in plainer language and added an important Solcast setup note.
- Documented the PV Surplus Charge Trigger for unmanaged microinverters or other PV sources sharing the same smart meter.

## 1.6.2

- Added a bundled AFERIY Overnight Plan Lovelace card with card-picker registration and README setup instructions.
- Added PV Surplus Charge Trigger as a local `0-50 W` control for systems with unmanaged microinverters or other PV sources on the same electrical system.
- Improved Recommended Overnight SOC so whole-day demand versus solar shortfall is considered before using the morning-bridge-only target path.
- Removed the extra overnight discharge-efficiency uplift so SMART targets follow measured house demand, solar shortfall, reserve, and buffer more closely.
- Added Post-Sunset Need and whole-day net shortfall attributes to explain the battery reserve needed between useful solar ending and the next off-peak window.
- Added SMART History visibility for the 14-day household usage picture used by overnight recommendations.
- Locked the automatic overnight SMART target at the start of the active off-peak window so recalculations after midnight do not move the charging target mid-window.
- Rounded Battery Capacity preset labels to two decimal places and renamed Local Operating Mode to Operating Mode.
- Clarified the Overnight Plan card battery need and timing-check wording.
- Updated the README hero graphic and documented the local PV surplus trigger behaviour.

## 1.6.1

- Returned individual Battery N SOC identification to the master-reported local `Storage_list`.
- Battery Capacity no longer limits or removes individual Battery N SOC entities; it is only an advanced energy-estimate input.
- On startup or integration reload, stale Battery N SOC entities are removed when the master reports a changed battery list.
- Automatic Overnight Charging now reports an unconfirmed charge command as retrying rather than as a final failure.

## 1.6.0

- Added integration-owned Automatic Overnight Charging with Off, On, and Manual modes.
- Added local SMART configuration controls for tariff preset, custom off-peak start/end times, and manual overnight SOC.
- Starts automatic charging one minute after off-peak begins, monitors System Average Battery SOC throughout the window, and restores Self-Gen/Zero Export five minutes before off-peak ends.
- Added Overnight Status and integration-owned House Demand Energy and House Demand Daily sensors.
- Made Recommended Overnight SOC and the Battery Capacity preset available as standard configuration features.
- Replaced the Solar Unavailable switch with a Solar Availability dropdown offering Solar Available and Solar Unavailable.
- Removed redundant Battery SOC, Local Unit Battery SOC, Runtime Left, manual Battery Capacity, and old Solar Unavailable entities.
- Made individual Battery N SOC entities follow the installed module count selected through Battery Capacity and remove stale higher-numbered slots after restart.
- Documented that changing the installed battery module count may require a full Home Assistant restart to rebuild individual battery SOC entities.

## 1.5.6

- Made AC Charging Power prefer the system-total cloud/local summary field before falling back to the local unit field.
- Stabilised individual per-battery SOC sensors by holding the last valid reading through short bad-value bursts.
- Changed Energy Charged to use Total Charge Power and prevent negative source power from reducing the total-increasing counter.
- Renamed Operating Mode to Local Operating Mode and clarified that cloud/app-originated changes may not update the selector.
- Added diagnostic labelling for control time slot 2 and documented AEC Cloud app schedule/export findings from Proxyman captures.
- Documented the recommended local-first overnight charging approach using Home Assistant as the scheduler.

## 1.5.5

- Fixed Hassfest validation for zeroconf discovery by using the required lowercase manifest matcher.
- Made zeroconf service-name handling case-insensitive.

## 1.5.4

- Added Home Assistant zeroconf/mDNS discovery for local AECC/SXD devices.
- Added a Master Device selector during setup and reconfiguration while keeping manual IP entry available.
- De-duplicated discovered devices by IP/port and prefers serial-number labels when available.
- Clearly warns multi-unit users to add only the master/coordinator, not executor units.
- Optimised setup discovery with shorter scans, parallel mDNS fallback, and a short cache so settings load faster.

## 1.5.3

- Added dynamic per-battery SOC sensors based on the units reported by local TCP, avoiding unused fixed Array sensors.
- Kept System Average Battery SOC as the main multi-unit SOC source for estimates and overnight automation logic.
- Made House Demand available without enabling advanced energy estimate sensors.
- Hid the manual Battery Capacity number by default because the capacity preset is the preferred control.
- Removed unreliable per-battery PV/output sensors after local testing showed they do not provide useful per-unit values.
- Updated the Home Assistant device manufacturer display to Richard Owen to avoid implying manufacturer support.

## 1.5.2

- Changed the PS240 Self-Gen restore path to the tested schedule-3 pattern with AI smart discharge enabled and AI smart charge disabled.
- Improved smart overnight charging so strong solar days credit more of the early pre-useful-solar ramp, reducing overcharging on clear summer mornings.
- Added regression tests to protect the PS240 Self-Gen register pattern and diagnostics redaction.
- Updated the GitHub lint workflow to run the regression tests.

## 1.5.1

- Extended the smart overnight demand-history lookback from 7 to 14 days.
- Weighted recent house-demand history more strongly while keeping older valid days as smoothing data.
- Added a small same-weekday boost so matching weekday patterns have more influence.
- Exposed demand-history weighting details on the Recommended Overnight SOC sensor attributes.
- Resolved the Solar Unavailable switch entity ID from the entity registry instead of relying on a hardcoded dashboard-style name.

## 1.5.0

- Added Recommended Overnight SOC target breakdown attributes for dashboards.
- Added Solcast/data-history freshness checks and a safer stale-data minimum target.
- Added forecast confidence adjustments for uncertain or very low solar forecasts.
- Changed Pre-Sunrise Need to run until sustained forecast solar should cover house demand when timed Solcast data is available.
- Added a conservative pre-useful-solar guard so weak early forecast solar only gets partial credit before it affects the SOC target.
- Added a low-solar-day credit so forecast solar can reduce the battery-size-aware SOC target even if it never fully covers house load.
- Added a Solar Unavailable integration switch that treats forecast solar as 0 kWh and reports Batteries Only.
- Made the options helper checklist labels render directly in the form if Home Assistant translation caching falls back to raw keys.

## 1.4.22

- Simplified the installer helper checklist again to Solcast installed and Home Occupancy enabled.
- Removed Shelly Smart Meter from the checklist because AECC grid readings are used for control and estimates; Shelly comparison remains diagnostic only.

## 1.4.21

- Simplified the installer helper checklist to Solcast installed, Shelly Smart Meter installed, and Home Occupancy enabled.
- Removed Octopus Energy and Recorder from the options checklist to avoid implying they are integration requirements.
- Clarified that helper checkboxes are reminders, while the integration currently looks for known Solcast, Shelly, and `zone.home` entities rather than auto-discovering every installation.

## 1.4.20

- Clarified that Octopus Energy sensors are optional helpers for automations and diagnostics, not required by the core local battery integration.
- Renamed installer-facing dependency wording to external helper wording.

## 1.4.19

- Added off-peak tariff presets for Snug Octopus, Octopus Go, Octopus Intelligent Go, E.ON Next Drive, British Gas Electric Driver, and British Gas Economy 7.
- Changed the default off-peak preset to Octopus Intelligent Go, 23:30-05:30.
- Made named tariff presets store their listed hours automatically; custom mode keeps manual start and end times.
- Added installer-facing external dependency confirmation checkboxes for Solcast, whole-home grid metering, Recorder history, Octopus Energy sensors, and home occupancy.

## 1.4.18

- Improved the Recommended Overnight SOC calculation with a dynamic buffer that grows when demand history, timed solar forecast data, or pre-sunrise coverage is weaker.
- Split occupied-house and empty-house demand floors, using `zone.home` occupancy while keeping the previous away-mode attributes as compatibility aliases.
- Added specific Pre-Sunrise Need attributes for the period after cheap-rate charging ends and before useful solar starts.
- Added battery discharge and grid charge efficiency allowances so the target better reflects real usable energy.
- Added a plain-English recommendation reason attribute for dashboard cards.
- Added a warning-only target jump guard for unusually large target changes.

## 1.4.17

- Replaced the personal away-mode check with household occupancy from `zone.home`, so demand estimates work for any Home Assistant household rather than one named person.
- Skipped historic demand profile days where the home was empty for most of the forecast window.
- Removed the personal default brand profile alias and kept the public default on the generic AFERIY profile.
- Added Grid Meter Agreement and Charging Reason diagnostic sensors.
- Included the new diagnostic fields in power-flow snapshots.
- Always create the Firmware Version diagnostic sensor, even when the battery has not exposed a value yet.

## 1.4.16

- Added configurable off-peak tariff start and end times, defaulting to Octopus Go 23:30-05:30.
- Updated the recommended overnight SOC and morning shortfall calculations to use the configured off-peak window.
- Added a diagnostic schedule-3 self-consumption restore service for export/clipping testing without changing the stable Self mode.
- Cleaned up duplicate or unused dashboard entities while keeping internal raw values available for calculations.
- Renamed the main PS240 controls and estimates for a cleaner Home Assistant UI.

## 1.4.15

- Synced local PS240 control fixes from the live Home Assistant install.
- Updated estimated house demand to use AECC grid meter flow, including signed grid history.
- Restored extended-power compatibility for existing local entries.

## 1.4.14

- Added backwards-compatible power option constants for mixed local upgrades.
- Kept the PS240 self-consumption restore path aligned with the live local fix.

## 1.4.13

- Simplified the setup and reconfigure forms for the AFERIY PS240.
- Removed the extended 2400 W power option from the UI and normal control writes.
- Read register 3039 for diagnostics so PS240 output-limit behaviour can be investigated safely.

## 1.4.12

- Removed unsupported `domains` key from `hacs.json` for HACS validation.
- Re-ran validation after adding repository topics required by HACS.

## 1.4.11

- Sorted manifest keys for Hassfest validation.

## 1.4.10

- Declared the optional recorder integration relationship for Hassfest validation.

## 1.4.9

- Added connection health, last successful update, consecutive poll failure, and last command result sensors.
- Added options for polling interval and advanced energy estimate sensors.
- Disabled advanced estimate sensors by default for a cleaner public install.
- Added HACS, hassfest, and Python syntax GitHub Actions.
- Added issue templates, entity documentation, and troubleshooting notes.
- Added HACS/Home Assistant badges to the README.

## 1.4.8

- Initial AFERIY PS240 (Local) public package.
