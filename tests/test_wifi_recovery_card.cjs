const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(
  path.join(__dirname, '../custom_components/aecc_battery/frontend/aferiy-wifi-recovery-card.js'),
  'utf8',
);
const now = Date.parse('2026-09-16T13:10:00Z');
class Clock extends Date { static now() { return now; } }

// Minimal shadow-root stand-in: the card only ever sets innerHTML, queries it,
// and attaches listeners, so a regex-readable store is enough to assert on.
class Element {
  constructor() { this._html = ''; this.activeElement = null; }
  attachShadow() {
    const element = this;
    return {
      get innerHTML() { return element._html; },
      set innerHTML(value) { element._html = value; },
      querySelector: (selector) => element._query(selector),
      querySelectorAll: () => [],
      get activeElement() { return element.activeElement; },
    };
  }
  _query(selector) {
    const match = /data-action="([^"]+)"/.exec(selector);
    if (match && this._html.includes(`data-action="${match[1]}"`)) return { dataset: { action: match[1] }, addEventListener() {}, focus() {} };
    if (selector === '.wr-more') return this._html.includes('class="wr-more"') ? { open: true } : null;
    return { dataset: {}, addEventListener() {}, focus() {} };
  }
}

function fixture(config = {}) {
  let Card;
  const timers = new Map();
  let nextTimer = 1;
  vm.runInNewContext(source, {
    HTMLElement: Element,
    Date: Clock,
    Intl,
    console,
    customElements: { define: (_, klass) => { Card = klass; } },
    window: {
      setInterval: (fn) => { const id = nextTimer++; timers.set(id, fn); return id; },
      clearInterval: (id) => timers.delete(id),
    },
  });
  const card = new Card();
  const state = (entity_id, state, attributes) => ({ entity_id, state, attributes });
  const base = {
    configured: true, router_model: 'Linksys MX4200', allowed_channels: [6, 11],
    trigger_after_consecutive_failures: 6, current_consecutive_failures: 0,
    battery_available: true, cooldown_hours: 1, grace_period_minutes: 6,
    grace_period_ends_at: null, last_attempt_at: null, next_allowed_attempt_at: null,
    requested_channel: null, last_result: null, last_battery_recovery_at: null,
    current_2_4ghz_channel: 6, status: 'Monitoring',
    reason: 'Waiting for the PS240 to become unavailable after sustained poll failures.',
    policy: 'One 6/11 channel toggle per outage after the battery becomes unavailable.',
  };
  const recovery = state('switch.battery_wifi_loss_recovery', 'on', base);
  const grace = state('number.battery_wifi_recovery_grace_period', '6', { min: 0, max: 60 });
  const calls = [];
  const hass = {
    states: { [recovery.entity_id]: recovery, [grace.entity_id]: grace },
    config: { time_zone: 'Europe/London' },
    callService: async (...args) => calls.push(args),
  };
  card.setConfig(config);
  card.hass = hass;
  return {
    card, recovery, grace, hass, calls, timers,
    html: () => card._root.innerHTML,
    // Re-publish the same hass object, exactly as Home Assistant does when an
    // entity state or attribute changes.
    touch: () => { card.hass = hass; },
  };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

test('monitoring shows the armed hero, channel pair and failure pips', () => {
  const f = fixture();
  assert.match(f.html(), /ARMED · WATCHING/);
  assert.match(f.html(), /Watching the battery link/);
  assert.match(f.html(), /Battery <b>available<\/b>/);
  assert.match(f.html(), /Next channel <b>6 → 11<\/b>/);
  assert.match(f.html(), /Consecutive poll failures/);
  assert.match(f.html(), /0 of 6/);
  assert.match(f.html(), /data-state="now"/);
  // Six pips, none filled while no poll has failed.
  assert.equal((f.html().match(/<i class=""><\/i>/g) || []).length, 6);
  assert.equal(f.calls.length, 0);
});

test('grace period renders a live countdown with accessible minute text', () => {
  const f = fixture();
  f.recovery.attributes.status = 'Grace period';
  f.recovery.attributes.current_consecutive_failures = 6;
  f.recovery.attributes.battery_available = false;
  f.recovery.attributes.grace_period_ends_at = new Date(now + 5 * 60000 + 42000).toISOString();
  f.touch();
  assert.match(f.html(), /OUTAGE · GRACE PERIOD/);
  assert.match(f.html(), /data-countdown aria-hidden="true">5:42/);
  assert.match(f.html(), /under 6 minutes/);
  assert.match(f.html(), /data-state="now"/);
  assert.equal(f.timers.size, 1, 'a ticker runs while a deadline is pending');
  // The ticker rewrites only the countdown text.
  const html = f.html();
  [...f.timers.values()][0]();
  assert.equal(f.html(), html);
});

test('an expired grace deadline stops the ticker and drops the countdown', () => {
  const f = fixture();
  f.recovery.attributes.status = 'Grace period';
  f.recovery.attributes.grace_period_ends_at = new Date(now - 1000).toISOString();
  f.touch();
  assert.match(f.html(), /Channel change is due now/);
  assert.doesNotMatch(f.html(), /data-countdown/);
  assert.equal(f.timers.size, 0);
});

test('cooldown is a distinct blocked state with its own countdown', () => {
  const f = fixture();
  f.recovery.attributes.status = 'Cooldown';
  f.recovery.attributes.current_consecutive_failures = 6;
  f.recovery.attributes.battery_available = false;
  f.recovery.attributes.next_allowed_attempt_at = new Date(now + 41 * 60000).toISOString();
  f.touch();
  assert.match(f.html(), /OUTAGE · COOLDOWN/);
  assert.match(f.html(), /Next change allowed in </);
  assert.match(f.html(), /data-state="blocked"/);
  assert.match(f.html(), /Blocks another router change|still unavailable, but the 1-hour guard/);
  assert.equal(f.timers.size, 1);
});

test('each published status maps to its own tone and headline', () => {
  const cases = [
    ['Changing channel', 'warning', 'Switching channel 6 → 11'],
    ['Waiting for battery', 'success', 'verified · waiting for telemetry'],
    ['Recovered', 'success', 'Battery telemetry is back'],
    ['Authentication failed', 'error', 'The router rejected the credentials'],
    ['Failed', 'error', 'The channel change could not be verified'],
  ];
  for (const [status, tone, headline] of cases) {
    const f = fixture();
    f.recovery.attributes.status = status;
    f.recovery.attributes.requested_channel = 11;
    f.recovery.attributes.last_result = 'failed';
    f.touch();
    assert.match(f.html(), new RegExp(`data-tone="${tone}"`), status);
    assert.ok(f.html().includes(headline), `${status} should show ${headline}`);
  }
});

test('off, offline and unconfigured states stay explicit', () => {
  const off = fixture();
  off.recovery.state = 'off';
  off.recovery.attributes.status = 'Off';
  off.touch();
  assert.match(off.html(), /AUTOMATIC RECOVERY · OFF/);
  assert.match(off.html(), /Turn recovery on to allow one verified channel change/);
  assert.match(off.html(), /aria-checked="false"/);

  const offline = fixture();
  offline.recovery.state = 'off';
  offline.recovery.attributes.status = 'Off';
  offline.recovery.attributes.battery_available = false;
  offline.recovery.attributes.current_consecutive_failures = 6;
  offline.touch();
  assert.match(offline.html(), /Battery offline and recovery is off/);
  assert.match(offline.html(), /data-tone="warning"/);

  const bare = fixture();
  bare.recovery.attributes.configured = false;
  bare.recovery.attributes.status = 'Configuration required';
  bare.touch();
  assert.match(bare.html(), /Router not configured/);
  assert.match(bare.html(), /Settings → Devices &amp; Services/);
  assert.match(bare.html(), /disabled/);
});

test('an ambiguous or missing entity never drives another battery switch', () => {
  const f = fixture();
  f.hass.states['switch.other_wifi_loss_recovery'] = {
    entity_id: 'switch.other_wifi_loss_recovery', state: 'on', attributes: { status: 'Monitoring' },
  };
  f.card.setConfig({});
  f.touch();
  assert.match(f.html(), /Recovery entity not found/);
  assert.match(f.html(), /Multiple AFERIY entries need the entity option/);
  assert.doesNotMatch(f.html(), /Watching the battery link/);

  // An explicitly configured entity that disappears fails closed too.
  f.card.setConfig({ entity: 'switch.missing' });
  f.touch();
  assert.match(f.html(), /switch\.missing is not available/);
});

test('grace stepper is clamped, persists through the number entity and reports failures', async () => {
  const f = fixture();
  await f.card._setGrace(f.grace, 9);
  assert.deepEqual(JSON.parse(JSON.stringify(f.calls)), [['number', 'set_value', { entity_id: f.grace.entity_id, value: 9 }]]);
  await f.card._setGrace(f.grace, 999);
  assert.equal(f.calls.at(-1)[2].value, 60);
  await f.card._setGrace(f.grace, -4);
  assert.equal(f.calls.at(-1)[2].value, 0);

  f.hass.callService = async () => { throw new Error('Permission denied'); };
  await f.card._setGrace(f.grace, 5);
  assert.match(f.html(), /Grace period could not be saved: Permission denied/);
  assert.equal(f.card._graceBusy, false);
});

test('the switch only calls the service on request and surfaces errors', async () => {
  const f = fixture();
  assert.equal(f.calls.length, 0);
  await f.card._toggle(f.recovery);
  assert.deepEqual(JSON.parse(JSON.stringify(f.calls)), [['switch', 'turn_off', { entity_id: f.recovery.entity_id }]]);
  f.hass.callService = async () => { throw new Error('Router offline'); };
  await f.card._toggle(f.recovery);
  assert.match(f.html(), /Recovery could not be changed: Router offline/);
  assert.equal(f.card._busy, false);
  // A missing entity is never called.
  await f.card._toggle(undefined);
  assert.equal(f.calls.length, 1);
});

test('untrusted entity text is escaped everywhere it is rendered', () => {
  const f = fixture();
  f.recovery.attributes.reason = '<img src=x onerror=alert(1)>';
  f.recovery.attributes.router_model = '"><script>alert(2)</script>';
  f.recovery.attributes.status = 'Monitoring';
  f.touch();
  assert.match(f.html(), /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(f.html(), /<img/);
  assert.doesNotMatch(f.html(), /<script>/);
});

test('the details block carries the policy, router and history', () => {
  const f = fixture();
  f.recovery.attributes.last_attempt_at = new Date(now - 9 * 60000).toISOString();
  f.recovery.attributes.last_result = 'verified';
  f.recovery.attributes.last_battery_recovery_at = new Date(now - 60 * 60000).toISOString();
  f.touch();
  const html = f.html();
  assert.match(html, /Guardrails, router and history/);
  assert.match(html, /Linksys MX4200/);
  assert.match(html, /After 6 consecutive poll failures/);
  assert.match(html, /Channel re-read from the router within 45 seconds/);
  assert.match(html, /Channel change verified/);
  assert.match(html, /One 6\/11 channel toggle per outage/);
  assert.match(html, /Credentials never reach the card/);
});

test('re-rendering is skipped when nothing the card shows has changed', () => {
  const f = fixture();
  const first = f.html();
  f.touch();
  assert.equal(f.html(), first);
  f.recovery.attributes.current_consecutive_failures = 3;
  f.touch();
  assert.notEqual(f.html(), first);
  assert.match(f.html(), /3 of 6/);
  assert.equal((f.html().match(/<i class="on"><\/i>/g) || []).length, 3);
});

test('disconnecting clears a running ticker', () => {
  const f = fixture();
  f.recovery.attributes.status = 'Cooldown';
  f.recovery.attributes.next_allowed_attempt_at = new Date(now + 60000).toISOString();
  f.touch();
  assert.equal(f.timers.size, 1);
  f.card.disconnectedCallback();
  assert.equal(f.timers.size, 0);
});

test('grace discovery prefers the sibling number entity of the recovery switch', () => {
  const f = fixture();
  f.hass.states['number.other_wifi_recovery_grace_period'] = {
    entity_id: 'number.other_wifi_recovery_grace_period', state: '20', attributes: {},
  };
  f.card.setConfig({ entity: 'switch.battery_wifi_loss_recovery' });
  f.touch();
  assert.equal(f.card._findGraceNumber(f.recovery).entity_id, 'number.battery_wifi_recovery_grace_period');
  assert.match(f.html(), /6 min/);

  // Without a usable number entity the stepper is disabled, and the other
  // battery's grace period is never adopted.
  delete f.hass.states['number.battery_wifi_recovery_grace_period'];
  f.card.setConfig({ entity: 'switch.battery_wifi_loss_recovery' });
  f.touch();
  assert.equal(f.card._findGraceNumber(f.recovery), undefined);
  assert.match(f.html(), /Unavailable · the number entity was not found/);
  assert.equal((f.html().match(/data-action="grace-(up|down)"[^>]*disabled/g) || []).length, 2);
  // An explicit grace_entity still wins when it is available.
  f.card.setConfig({ entity: 'switch.battery_wifi_loss_recovery', grace_entity: 'number.other_wifi_recovery_grace_period' });
  f.touch();
  assert.equal(f.card._findGraceNumber(f.recovery).entity_id, 'number.other_wifi_recovery_grace_period');
  assert.match(f.html(), /20 min/);
});

test('service calls never run without a user action, even after state changes', () => {
  const f = fixture();
  for (const status of ['Grace period', 'Changing channel', 'Recovered', 'Failed', 'Cooldown']) {
    f.recovery.attributes.status = status;
    f.recovery.attributes.next_allowed_attempt_at = new Date(now + 60000).toISOString();
    f.touch();
  }
  assert.equal(f.calls.length, 0);
  assert.equal(f.card._busy, undefined);
  flush();
});
