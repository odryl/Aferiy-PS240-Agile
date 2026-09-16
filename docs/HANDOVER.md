# AFERIY PS240 Agile handover

This document is the operational and maintainer handover for the Home Assistant
custom integration in this repository. It covers the live system assumptions,
the guarded Octopus Agile controller, data collection, development checks, and
the complete GitHub/HACS release process.

## Project ownership and locations

- Repository: `https://github.com/odryl/Aferiy-PS240-Agile`
- Upstream project: `https://github.com/MortUK/Aferiy-PS240-Local-`
- Home Assistant domain: `aecc_battery`
- Integration source: `custom_components/aecc_battery/`
- Minimum supported Home Assistant version: `2024.8.0`
- Default local TCP port: `8080`
- Release asset required by HACS: `aecc_battery.zip`
- Dashboard resource base path: `/aecc_battery_static/`

The repository is a private fork. The GitHub account used by HACS must be able
to access it. Existing entity IDs retain the `aecc_battery` domain for
compatibility with the upstream integration.

## Current operating assumptions

The installed system has a master/coordinator PS240 and may have subordinate
battery units. Add only the master to Home Assistant. The master reports and
controls the full system; adding slave units separately causes duplicate or
competing local connections.

The Agile planner currently assumes:

- AC grid charging can run at up to **1200 W**.
- CT-controlled battery supply to household demand is limited to **1000 W**.
- A full 30-minute period can therefore grid-charge up to 0.6 kWh or supply up
  to 0.5 kWh to the house.
- Peak-period supply uses **Self-Gen/Zero Export**. Agile automation never sends
  a fixed Discharge or Feed command.
- The default target is 100% SOC by 16:00, with household demand protected
  until 22:00 and the live device discharge reserve preserved.
- Tomorrow's published Agile rates are incorporated into Today's replacement
  cost and Tomorrow starts from Today's projected ending SOC.
- Useful live PV inhibits planned grid charging. Grid charging is also
  inhibited once the target SOC has been reached.
- The fallback demand profile is based on anonymised half-hour net-demand
  medians. Timestamped PV forecast energy is discovered but is not yet consumed
  by the Agile optimiser.

These values are safety and planning limits, not a claim that every manual
operating mode is safe at the same power. Other high-power/manual controls
remain experimental.

## Operating modes

### Self-Gen/Zero Export

This is the normal and fail-safe mode. The PS240 uses its CT clamp to follow
actual household demand and avoid export. Agile uses this mode for profitable
peak periods instead of requesting a fixed discharge power.

### Charge

Manual Charge is available through the Operating Mode control. Guarded Agile
control may also select Charge, but only for the current planned period, at no
more than 1200 W, after two healthy polls and all safety interlocks pass.

### Idle

Idle prevents intentional battery discharge. Agile may use a bounded Idle
period after solar has gone quiet when preserving stored energy for a later,
more valuable period. It is not used while useful PV is present.

### Discharge and Feed

These are manual/experimental modes retained from the local integration. Agile
Automated Control is prohibited from invoking either mode. Feed behaviour and
the passive base-feed value depend on the device EMS and CT feedback.

### Smart Overnight Charging

This is the inherited fixed-window scheduler for tariffs such as Octopus Go or
Economy 7. It is deliberately interlocked with Agile Automated Control. Keep
**Overnight Charge** set to **Off** while Octopus Agile is selected or while the
Agile controller is in use.

## Guarded Agile Automated Control

The `Agile Automated Control` switch is the only opt-in for plan execution.
When it is Off, the plan, shadow decision, card, and export logger continue to
operate without issuing Agile commands.

The switch intentionally starts Off after every integration or Home Assistant
restart. Enabling it requires:

- the Agile planner to be enabled;
- the Octopus Agile tariff preset;
- valid current-day rate data and a safe planner decision;
- the fixed-window Overnight Charge selector to be Off;
- complete battery topology;
- a fresh local connection with no current connection failures;
- stable telemetry across two distinct healthy polls; and
- Self-Gen/Zero Export to be the starting manual operating mode.

The controller permits only bounded Charge, bounded Idle, and device-managed
Self-Gen/Zero Export. A failed write, stale rate/SOC data, lost topology,
connection failure, reserve condition, tariff change, manual mode change, or
storage failure causes it to fail closed and restore Self-Gen where possible.

Before a custom Charge or Idle command is sent, a pending-restore marker is
written to Home Assistant storage. If Home Assistant stops during the command,
the next healthy connection restores Self-Gen. The enabled state itself is not
restored after restart.

Treat this controller as a guarded beta until it has accumulated longer live
validation across sunny and cloudy days, midnight rate rollover, connection
loss, Home Assistant restart, and the expanded PV array.

## Home Assistant installation and configuration

### Install or update with HACS

1. In HACS, add `https://github.com/odryl/Aferiy-PS240-Agile` as a custom
   **Integration** repository.
2. Install or update **AFERIY PS240 Agile**.
3. Restart Home Assistant.
4. Reload the integration or restart again after adding/removing battery units
   so its entity list is rebuilt from the master.

### Configure Octopus Agile

BottlecapDave's Octopus Energy integration must expose current-day and next-day
import-rate event entities. In the AFERIY integration options:

1. Enable Octopus Agile Proposed Plan.
2. Select the current-day and next-day **import** event entities.
3. Set the ready-by and protection-end times, normally 16:00 and 22:00.
4. Confirm the battery capacity preset matches the installed 1.958 kWh modules.
5. Keep Overnight Charge Off.

Do not use export-rate entities. Current-day and next-day entities must have
matching MPAN, serial-number, and Agile tariff metadata.

### Dashboard card

Register this JavaScript module under **Settings > Dashboards > Resources**:

```text
/aecc_battery_static/aferiy-agile-plan-card.js?v=<release-version>
```

For release 1.8.16 the full path is:

```text
/aecc_battery_static/aferiy-agile-plan-card.js?v=1.8.16
```

Update the query-string version for every release that changes the card. After
an update, restart Home Assistant and hard-refresh the browser or fully close
and reopen the mobile app.

The basic card configuration is:

```yaml
type: custom:aferiy-agile-plan-card
title: Octopus Agile Battery Plan
```

With more than one AFERIY entry, configure the Today, Tomorrow, shadow, and
control entity IDs explicitly as shown in the main README.

## Trial-data logger

The `aecc_battery.export_agile_plan` action appends a schema-v3 record to:

```text
/config/aecc_battery_agile_plan_export.jsonl
```

It is read-only with respect to the battery. Records include the plans, live
power/SOC data, local-command context, shadow decision, controller state, and
cumulative energy counters. The active file rotates at 8 MiB; completed
segments are preserved as timestamped `.jsonl.gz` files beside it.

A compatible 30-minute Home Assistant automation is:

```yaml
alias: Export Agile trial data every 30 minutes
description: Capture each plan and live outcome shortly after the tariff boundary.
trigger:
  - platform: time_pattern
    minutes: "/30"
    seconds: "10"
condition: []
action:
  - service: aecc_battery.export_agile_plan
    data:
      label: guarded_control_v3
mode: single
```

The label must be a string. Existing automations can remain in shadow or
guarded-control operation; the exported `control_enabled` and controller audit
fields identify which was active. Do not commit exported JSONL or gzip files.
They contain private household telemetry even though MPAN and rate-source
entity IDs are excluded.

The separate `Automatic Data Logger Restart` switch reboots the physical
Wi-Fi/BLE logger every three hours. It is unrelated to the JSONL export
automation.

## Code map

| Path | Responsibility |
| --- | --- |
| `custom_components/aecc_battery/__init__.py` | Config-entry setup, services, export assembly, and frontend registration |
| `custom_components/aecc_battery/agile.py` | Pure rate validation, planning, shadow decisions, bounded-window and command guards |
| `custom_components/aecc_battery/agile_export.py` | JSONL append and 8 MiB gzip rotation helpers |
| `custom_components/aecc_battery/coordinator.py` | TCP polling, verified writes, scheduler state, command/recovery state |
| `custom_components/aecc_battery/sensor.py` | Telemetry, plan, shadow, diagnostics, and estimate entities |
| `custom_components/aecc_battery/switch.py` | Guarded Agile controller and automatic physical data-logger restart |
| `custom_components/aecc_battery/select.py` | Manual operating modes, tariffs, and scheduler selectors/interlocks |
| `custom_components/aecc_battery/const.py` | Defaults, confirmed Agile limits, tariff presets, and demand profile |
| `custom_components/aecc_battery/frontend/` | Bundled Agile and overnight dashboard cards |
| `tests/test_agile_planner.py` | Pure planner, decision, window, and final-command safety tests |
| `tests/test_agile_home_assistant_wiring.py` | Static Home Assistant/controller wiring regression tests |
| `.github/workflows/release.yml` | Tag-triggered HACS ZIP and GitHub release publisher |

Keep policy and calculations in pure functions in `agile.py` where possible.
The final command path in the coordinator must independently validate direction,
power, and bounded slot immediately before writing registers. UI checks alone
are never sufficient safety controls.

## Local development and verification

Use Python 3.12 or newer. Before committing a release, run from the repository
root:

```bash
python3 -m pytest -q
python3 -m compileall -q custom_components/aecc_battery
python3 -m ruff check custom_components/aecc_battery/agile.py custom_components/aecc_battery/const.py custom_components/aecc_battery/switch.py tests/test_agile_planner.py tests/test_agile_home_assistant_wiring.py
node --check custom_components/aecc_battery/frontend/aferiy-agile-plan-card.js
python3 -m json.tool custom_components/aecc_battery/manifest.json >/dev/null
git diff --check
```

The repository GitHub checks also run the regression tests, Hassfest, and HACS
validation. Do not publish while a required check is failing.

For a local Home Assistant test, copy `custom_components/aecc_battery` into a
test instance's `config/custom_components/`, restart Home Assistant, and inspect
the integration and browser logs. Keep Agile Automated Control Off until the
plan sensors, live data, card, and Self-Gen restore have been verified.

## Release process

The release workflow is tag-driven. Pushing a tag matching `v*` runs
`.github/workflows/release.yml`, which:

1. archives the contents of `custom_components/aecc_battery/` at the ZIP root;
2. excludes bytecode and `__pycache__` files;
3. names the asset `aecc_battery.zip`; and
4. creates the GitHub release with autogenerated notes.

This layout matters because HACS extracts the archive directly into
`config/custom_components/aecc_battery`. `hacs.json` has `zip_release: true`
and requires the exact asset name `aecc_battery.zip`.

### 1. Prepare the release branch

Work on a `codex/<topic>` or other short-lived feature branch. Preserve
unrelated local changes and begin by synchronising remote state:

```bash
git fetch origin --tags --prune
git status --short --branch
git log --oneline --left-right main...origin/main
```

Do not fast-forward `main` until tests pass and `origin/main` is confirmed not
to contain unexpected work.

### 2. Choose and apply the version

Use semantic patch releases for normal fixes/features unless a deliberate
minor or major release has been agreed. Update all of these locations:

- `custom_components/aecc_battery/manifest.json`
- `pyproject.toml`
- the version badge in `README.md`
- the Agile card resource cache query in `README.md`
- the top `CHANGELOG.md` heading from `Unreleased` to the new version

Search for stale references before committing:

```bash
rg -n "1\.8\.16|v=1\.8\.16" README.md CHANGELOG.md pyproject.toml custom_components docs
```

Do not rewrite historical changelog entries that correctly describe older
releases.

### 3. Verify and commit

Run the complete local verification commands above. Then commit all intended
release files on the feature branch:

```bash
aferiy_release_version=v1.8.17
git add CHANGELOG.md README.md custom_components/aecc_battery docs pyproject.toml tests
git commit -m "Release ${aferiy_release_version}"
```

Review `git show --stat HEAD` and confirm the working tree is clean.

### 4. Fast-forward main

Fetch once more, switch to main, and use a fast-forward-only merge:

```bash
git fetch origin --tags --prune
git switch main
git merge --ff-only codex/<topic>
```

If the merge cannot fast-forward, stop and inspect the branch history. Do not
force, reset, or silently create a merge commit for a release.

### 5. Tag and push

Create an annotated tag on the release commit, then push main and the tag:

```bash
aferiy_release_version=v1.8.17
git tag -a "$aferiy_release_version" -m "Release ${aferiy_release_version}"
git push origin main
git push origin "$aferiy_release_version"
```

The tag push starts the release workflow automatically. Do not immediately run
`gh release create`; doing so can race the workflow and create a duplicate or
partial release.

### 6. Verify GitHub Actions and the release

Always target the fork explicitly with GitHub CLI commands. Without `--repo`,
`gh` may select the upstream parent repository.

```bash
aferiy_release_version=v1.8.17
gh run list --repo odryl/Aferiy-PS240-Agile --limit 10
gh release view "$aferiy_release_version" --repo odryl/Aferiy-PS240-Agile
```

Wait for the Release, Lint, Hassfest validation, and HACS validation jobs to
finish. A run can be followed with:

```bash
gh run watch 123456789 --repo odryl/Aferiy-PS240-Agile --exit-status
```

The published release must be non-draft, non-prerelease, and contain one
uploaded asset named `aecc_battery.zip`.

### 7. Download and test the published asset

Verify what users will actually receive rather than relying only on the local
tree:

```bash
aferiy_release_version=v1.8.17
release_verify_dir=$(mktemp -d /tmp/aferiy-release-verify.XXXXXX)
gh release download "$aferiy_release_version" \
  --repo odryl/Aferiy-PS240-Agile \
  --pattern aecc_battery.zip \
  --dir "$release_verify_dir"
unzip -t "$release_verify_dir/aecc_battery.zip"
unzip -p "$release_verify_dir/aecc_battery.zip" manifest.json | python3 -m json.tool
```

Confirm that `manifest.json` is at the ZIP root and contains the release
version. The archive must not add an `aecc_battery/` or repository-name parent
directory.

### 8. Final Home Assistant check

1. Confirm HACS offers the new release.
2. Install/update it on the test Home Assistant instance.
3. Restart Home Assistant.
4. Update the card resource query string to the new release version.
5. Hard-refresh the dashboard.
6. Confirm Today, Tomorrow, shadow state, and controller entities load.
7. Confirm Agile Automated Control starts Off.
8. Supervise the first enabled Charge, Self-Gen, and restore transitions.

## Release-workflow recovery

If the tag workflow fails, inspect the tag, release, asset, and workflow before
taking action:

```bash
aferiy_release_version=v1.8.17
gh run list --repo odryl/Aferiy-PS240-Agile --limit 10
gh release view "$aferiy_release_version" --repo odryl/Aferiy-PS240-Agile
git ls-remote --tags origin "$aferiy_release_version"
```

If a release exists but its notes are incomplete, edit it rather than creating
a second release:

```bash
aferiy_release_version=v1.8.17
gh release edit "$aferiy_release_version" \
  --repo odryl/Aferiy-PS240-Agile \
  --title "$aferiy_release_version" \
  --notes-file release-notes.md
```

Only if the workflow has definitively failed and no release exists, build the
same root-layout package and publish it manually:

```bash
aferiy_release_version=v1.8.17
release_build_dir=$(mktemp -d /tmp/aferiy-release-build.XXXXXX)
git archive --format=zip \
  --output="$release_build_dir/aecc_battery.zip" \
  "${aferiy_release_version}:custom_components/aecc_battery"
unzip -t "$release_build_dir/aecc_battery.zip"
gh release create "$aferiy_release_version" "$release_build_dir/aecc_battery.zip" \
  --repo odryl/Aferiy-PS240-Agile \
  --verify-tag \
  --title "$aferiy_release_version" \
  --notes-file release-notes.md
```

Never move or force-update a published release tag. If released code needs a
fix, create a new patch release. If only `main` documentation needs correction,
commit it normally and include it in the next release.

## Rollback and incident response

For an unsafe operating result:

1. Turn **Agile Automated Control** Off.
2. Select **Self-Gen/Zero Export** and confirm the command succeeds.
3. Preserve the active JSONL and rotated gzip logs.
4. Download Home Assistant diagnostics and record the exact local time, rate,
   SOC, PV, grid flow, and controller reason.
5. Reinstall the previous known-good release through HACS if necessary.
6. Restart Home Assistant and confirm the controller remains Off.

Do not delete or rewrite the faulty release or its tag. Mark it as a
prerelease only if there is a clear distribution reason, and publish a new
patch release for the fix so installed versions remain traceable.

## Known follow-up work

- Consume provider-neutral, timestamped solar forecasts selected in the Home
  Assistant Energy Dashboard.
- Learn per-period demand directly from Home Assistant Recorder while retaining
  privacy and conservative fallback behaviour.
- Add configurable daily cycle and cost ceilings.
- Continue supervised validation after adding the two 515 W PV panels.
- Periodically review planner/profile revisions against exported schema-v3
  results before changing demand assumptions.

For deeper planner and safety details, see `docs/AGILE_IMPLEMENTATION.md`. For
entity descriptions and user troubleshooting, see `docs/entities.md` and
`docs/troubleshooting.md`.
