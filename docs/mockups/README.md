# Wi-Fi loss recovery card — redesign mockup

`wifi-recovery-card.html` is a self-contained mockup of the rebuilt
`aferiy-wifi-recovery-card` custom card. It uses the same design language as the
overhauled Cosy Octopus plan card: a state-coloured hero, one progress rail,
reachable controls, and every diagnostic demoted to a collapsible details block.

Nothing in this folder is loaded by Home Assistant. It exists to agree the design
before the card is rewritten.

| File | Purpose |
| --- | --- |
| `wifi-recovery-card.html` | The mockup. Open it in a browser; no build step, no dependencies. |
| `card-preview.html` | Dev preview of the **shipped** card: loads the real `aferiy-wifi-recovery-card.js` and stubs `ha-card` / `ha-icon`. Add `?width=498` for a fixed card width. |
| `wifi-recovery-card-dark.png` | Full gallery in the dark theme, 4-column sheet. |
| `wifi-recovery-card-light.png` | The same gallery in the light theme. |
| `wifi-recovery-card-states.png` | Four key states at 2× for close review. |

`docs/images/wifi-recovery-card.png` and the Wi-Fi card area of
`docs/images/card.png` were rendered from `card-preview.html` — that is, from the
shipped card file with stub Home Assistant elements — rather than captured from a
live dashboard. Everything else in `docs/images/card.png` is the original
capture.

## Viewing

Open the file directly, or serve it:

```bash
open docs/mockups/wifi-recovery-card.html
```

Query parameters:

| Parameter | Effect |
| --- | --- |
| `?theme=light` | Start in the light theme (the toggle in the header also works). |
| `?only=monitoring,grace` | Render only the named states as a tight sheet, for screenshots. |

The grace-period and cooldown cards tick once a second, exactly as the card will:
the countdown is the only element on the card that changes between Home Assistant
updates.

The screenshots were captured from this file with headless Chrome over the
DevTools protocol (full-page capture with `captureBeyondViewport`), once in each
theme plus a 2× sheet of four states. Chrome's plain `--screenshot` mode does not
work here because the live countdown keeps a timer pending, so use a CDP-based
capture or the browser itself; the HTML remains the source of truth.

## States covered

Every state the integration can publish is rendered from the real attribute set
in `wifi_recovery.py` (`status`, `reason`, `configured`, `router_model`,
`current_2_4ghz_channel`, `requested_channel`, `trigger_after_consecutive_failures`,
`current_consecutive_failures`, `battery_available`, `last_attempt_at`,
`next_allowed_attempt_at`, `cooldown_hours`, `grace_period_minutes`,
`grace_period_ends_at`, `last_result`, `last_battery_recovery_at`).

| State | Tone | Headline |
| --- | --- | --- |
| Monitoring | success | Watching the battery link |
| Off (armed off) | idle | Recovery is off |
| Configuration required | error | Router not configured |
| Checking router | info | Checking local router access |
| Grace period | warning | Channel change in *m:ss* (live) |
| Changing channel | warning | Switching channel 6 → 11 |
| Waiting for battery | success | Channel 11 verified · waiting for telemetry |
| Recovered | success | Battery telemetry is back |
| Cooldown | warning | Next change allowed in *m:ss* (live) |
| Off while the battery is offline | warning | Battery offline and recovery is off |
| Authentication failed | error | The router rejected the password |
| Failed | error | The channel change could not be verified |

## Design notes

- **One hero.** The old header pill and eight equal tiles are replaced by a
  kicker, a 23 px headline and one sentence of reason, tinted with the colour of
  the current state (`--wr-tone`). Green armed, amber waiting, red failed, blue
  in progress, grey off.
- **One rail.** Watch → Wait → Switch → Verify. Completed steps are filled, the
  current step is ringed (and pulses only while a change is genuinely in flight),
  a blocked step is dashed. The rail is hidden when recovery is off, so the card
  stays short until it has something to say.
- **Two facts, not eight tiles.** Channel and battery state stay in the hero
  foot; consecutive failures become a pip meter that fills as an outage develops.
- **No ISO timestamps.** The integration's reason strings embed raw ISO times.
  The card reformats them into a clock time plus a live countdown, and screen
  readers hear "under 6 minutes" instead of a number changing every second.
- **Controls match Cosy.** A pill switch for the opt-in and a stepped 0–60 minute
  grace value, replacing the full-width button and the bare number input. The
  switch keeps the theme accent colour so it always reads as a control; state
  colour is never used on it.
- **Details, not clutter.** Router, allowed channels, trigger, cooldown,
  verification window, grace policy, last attempt, last result and last recovery
  move into one `<details>` block; credentials and the Wi-Fi passphrase are never
  requested or displayed.
- **Accessibility.** `role="switch"` with `aria-checked`, `aria-current="step"`
  on the rail, visually hidden step states, `aria-live` on the hero, focus-visible
  outlines, container queries at 420 px and 44 px targets on coarse pointers.
- **Isolation.** The card moves into a shadow root. The shipped card writes bare
  `h2`, `p` and `button` rules into the whole dashboard.

## Implementation status

The card was implemented in v1.8.34 from this mockup:

1. `aferiy-wifi-recovery-card.js` now renders in a shadow root, maps attributes
   through the `view()` logic shown here, and runs a one-second ticker only while
   a grace or cooldown deadline is pending (cleared in `disconnectedCallback`).
2. The contract is unchanged: `entity`, `grace_entity` and `title` config keys,
   entity discovery, `switch.turn_on` / `switch.turn_off` and
   `number.set_value` service calls, and no call without a user click.
3. `tests/test_wifi_recovery_card.cjs` covers the state mapping, countdowns,
   guarded calls, escaping, entity discovery and ticker cleanup; the lint
   workflow checks the file's syntax and runs the test.
4. `docs/dashboard-card.md`, `docs/ADVANCED_CONFIGURATION.md` and the doc images
   were updated, with a CHANGELOG entry and a version bump.

One deliberate divergence from the mockup: the card adds a **recovery entity not
found** screen. With more than one AFERIY entry the mockup's discovery cannot
know which battery the card watches, so the card asks for the `entity` option
instead of selecting one at random, and it never adopts another battery's grace
period.
