/**
 * AFERIY Wi-Fi loss recovery card.
 *
 * Renders the guarded Linksys channel-recovery switch from the integration's
 * published attributes. The card is a view only: it never changes a channel
 * itself and only ever calls the existing switch and number entities after a
 * user click. Design parity with the Cosy plan card is deliberate — one
 * state-coloured hero, one progress rail, reachable controls, and diagnostics
 * behind a single details block. The approved mockup lives at
 * docs/mockups/wifi-recovery-card.html and uses the same markup and classes.
 *
 * The copy never names the router credential fields; the integration's own
 * reason strings are escaped and shown as published.
 */
const VERIFY_SECONDS = 45; // mirrors WIFI_LOSS_RECOVERY_VERIFY_SECONDS
const GRACE_MAX_MINUTES = 60; // mirrors WIFI_LOSS_RECOVERY_MAX_GRACE_MINUTES
const MINUTE_MS = 60000;
const ICONS = {
  monitoring: "mdi:wifi",
  grace: "mdi:clock-outline",
  changing: "mdi:swap-horizontal",
  waiting: "mdi:wifi",
  recovered: "mdi:check-circle-outline",
  cooldown: "mdi:clock-outline",
  checking: "mdi:router-wireless",
  authFailed: "mdi:shield-alert-outline",
  failed: "mdi:alert-outline",
  unconfigured: "mdi:router-wireless",
  off: "mdi:wifi-off",
};
const RESULT_LABELS = {
  verified: "Channel change verified",
  failed: "Channel change not verified",
  authentication_failed: "Router rejected the credentials",
};

class AferiyWifiRecoveryCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    this._renderIfNeeded(true);
  }

  /* A one-second ticker runs only while a grace or cooldown deadline is
     pending, and only rewrites the countdown text. Everything else on the card
     changes when Home Assistant publishes a new state. */
  disconnectedCallback() {
    this._stopTicker();
  }

  setConfig(config) {
    const nextConfig = config || {};
    const changed = JSON.stringify(nextConfig) !== this._configSignature;
    this.config = nextConfig;
    this._configSignature = JSON.stringify(nextConfig);
    if (changed) {
      this._renderSignature = null;
      this._renderIfNeeded(true);
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._renderIfNeeded();
  }

  getCardSize() {
    return 6;
  }

  _findEntity(configured, domain, entitySuffix, friendlyName) {
    if (!this._hass) return undefined;
    if (configured) return this._hass.states[configured];
    const candidates = Object.values(this._hass.states).filter(
      (state) => state.entity_id.startsWith(`${domain}.`) && (
        state.entity_id.endsWith(entitySuffix)
        || state.attributes?.friendly_name?.endsWith(friendlyName)
      ),
    );
    // With several AFERIY entries the card cannot know which battery it is
    // watching, so the entity must be named explicitly instead of guessing.
    return candidates.length === 1 ? candidates[0] : undefined;
  }

  _findRecoverySwitch() {
    return this._findEntity(this.config?.entity, "switch", "_wifi_loss_recovery", "Wi-Fi Loss Recovery");
  }

  _findGraceNumber(recovery) {
    const configured = this.config?.grace_entity;
    if (configured && this._hass?.states[configured]) return this._hass.states[configured];
    // The grace number is always derived from the recovery switch, so a second
    // AFERIY entry's grace period can never be changed by this card.
    const sibling = recovery?.entity_id
      ?.replace(/^switch\./, "number.")
      .replace(/_wifi_loss_recovery$/, "_wifi_recovery_grace_period");
    if (sibling) return this._hass?.states[sibling];
    return this._findEntity(null, "number", "_wifi_recovery_grace_period", "Wi-Fi Recovery Grace Period");
  }

  _renderIfNeeded(force = false) {
    if (!this.config || !this._hass) return;
    const recovery = this._findRecoverySwitch();
    const grace = this._findGraceNumber(recovery);
    const signature = JSON.stringify([
      this.config.title, recovery?.entity_id, recovery?.state, recovery?.attributes,
      grace?.entity_id, grace?.state, this._busy, this._graceBusy, this._error,
    ]);
    if (!force && signature === this._renderSignature) return;
    this._renderSignature = signature;
    this.render(recovery, grace);
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
    })[character]);
  }

  _time(value) {
    const parsed = value ? new Date(value) : null;
    if (!parsed || Number.isNaN(parsed.getTime())) return "—";
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: this._hass?.config?.time_zone,
      hour: "2-digit", minute: "2-digit",
    }).format(parsed);
  }

  _ago(value) {
    const parsed = value ? Date.parse(value) : NaN;
    if (!Number.isFinite(parsed)) return "";
    const minutes = Math.max(0, Math.round((Date.now() - parsed) / MINUTE_MS));
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    return hours < 36 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`;
  }

  _countdown(remainingMs) {
    const total = Math.max(0, Math.round(remainingMs / 1000));
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
  }

  /* ---------------------------------------------------------------- view -- */

  _view(recovery, grace) {
    const configured = Boolean(recovery);
    const attributes = recovery?.attributes || {};
    const on = recovery?.state === "on";
    const status = configured ? (attributes.status || (on ? "Monitoring" : "Off")) : "Unavailable";
    const failures = Number(attributes.current_consecutive_failures) || 0;
    const threshold = Number(attributes.trigger_after_consecutive_failures) || 6;
    const cooldownHours = Number(attributes.cooldown_hours) || 1;
    const graceMinutes = Number.isFinite(Number(grace?.state))
      ? Number(grace.state) : Number(attributes.grace_period_minutes) || 0;
    const channel = attributes.current_2_4ghz_channel;
    const requested = attributes.requested_channel;
    const target = requested ?? (channel === 6 ? 11 : channel === 11 ? 6 : null);
    const graceEnds = attributes.grace_period_ends_at ? Date.parse(attributes.grace_period_ends_at) : 0;
    const cooldownEnds = attributes.next_allowed_attempt_at ? Date.parse(attributes.next_allowed_attempt_at) : 0;
    const lastAttempt = attributes.last_attempt_at ? Date.parse(attributes.last_attempt_at) : NaN;
    const lastRecovery = attributes.last_battery_recovery_at ? Date.parse(attributes.last_battery_recovery_at) : NaN;
    const router = configured ? attributes.router_model || "Linksys router" : "Not configured";
    const facts = (...pairs) => pairs.map(([label, value]) => ({ label, value }));
    const meter = {
      label: "Consecutive poll failures",
      value: `${failures} of ${threshold}`,
      pips: Math.min(threshold, 12),
      filled: Math.min(failures, threshold, 12),
      pct: Math.min(100, (failures / Math.max(threshold, 1)) * 100),
      bar: threshold > 12,
    };

    const view = {
      title: this.config.title || "Wi-Fi loss recovery",
      subtitle: "Guarded Linksys 2.4 GHz · AFERIY",
      tone: "idle", icon: ICONS.off, badge: "○ Off",
      kicker: "AUTOMATIC RECOVERY · OFF", headline: "Recovery is off",
      reason: "Nothing will change your router channel while this is off.",
      hint: "", facts: [], rail: null, railNote: "", meter: null, tick: null, busy: false,
      switchState: on ? "on" : "off", switchDisabled: false,
      switchHelp: "Opt in to one guarded channel change during a Wi-Fi outage.",
      graceHelp: "0 changes the channel immediately. Valid telemetry during the wait cancels it.",
      grace: graceMinutes,
      details: [], note: "", footer: ["", ""], deadline: 0,
    };
    if (!configured) {
      view.tone = "error"; view.icon = ICONS.unconfigured; view.badge = "○ Entity missing";
      view.kicker = "GUARDED RECOVERY · NOT FOUND";
      view.headline = "Recovery entity not found";
      view.reason = this.config.entity
        ? `The configured entity ${this.config.entity} is not available.`
        : "No Wi-Fi loss recovery switch was found. Multiple AFERIY entries need the entity option, or the integration needs reloading.";
      view.hint = "Add entity: switch.your_battery_wifi_loss_recovery to the card configuration.";
      view.facts = facts(["Switch", "not found"], ["Allowed channels", "6 ↔ 11"]);
      view.switchState = "unavailable"; view.switchDisabled = true;
      view.switchHelp = "The guarded switch cannot be controlled without an entity.";
      view.details = [
        ["Card entity option", this.config.entity || "not set"],
        ["Grace entity option", this.config.grace_entity || "discovered"],
      ];
      view.note = "Configure the AFERIY integration, then reload the card.";
      view.footer = ["Battery unknown", "Router unknown"];
      return view;
    }

    switch (status) {
      case "Monitoring":
        view.tone = "success"; view.icon = ICONS.monitoring; view.badge = "● Monitoring";
        view.kicker = "ARMED · WATCHING"; view.headline = "Watching the battery link";
        view.reason = attributes.reason || "Waiting for the PS240 to become unavailable after sustained poll failures.";
        view.facts = facts(["Battery", attributes.battery_available === false ? "offline" : "available"],
          ["Next channel", channel ? `${channel} → ${target}` : "unknown"]);
        view.rail = ["now", "todo", "todo", "todo"];
        view.railNote = "Armed. Nothing happens unless the battery goes quiet.";
        view.meter = meter;
        view.switchHelp = "Armed. Turn off to stop automatic changes.";
        break;

      case "Grace period":
        view.tone = "warning"; view.icon = ICONS.grace; view.badge = "● Grace period";
        view.kicker = "OUTAGE · GRACE PERIOD"; view.headline = "Channel change is waiting";
        view.tick = { lead: "Channel change in ", deadline: graceEnds };
        view.reason = `The PS240 is unavailable. The 2.4 GHz channel changes to ${target ?? "the alternate channel"} at ${this._time(attributes.grace_period_ends_at)} unless telemetry returns first.`;
        view.hint = failures >= threshold ? `${failures} consecutive poll failures confirmed the outage.` : "";
        view.facts = facts(["Change due", this._time(attributes.grace_period_ends_at)], ["Poll failures", `${failures} of ${threshold}`]);
        view.rail = ["done", "now", "todo", "todo"];
        view.railNote = "Valid battery telemetry during the wait cancels the channel change.";
        view.meter = meter;
        view.switchHelp = "Turning off cancels the pending channel change.";
        view.graceHelp = "Changing this recalculates the wait that is running.";
        break;

      case "Changing channel":
        view.tone = "warning"; view.icon = ICONS.changing; view.badge = "● Changing channel";
        view.kicker = "OUTAGE · CHANGING CHANNEL";
        view.headline = `Switching channel ${channel ?? "—"} → ${target ?? "—"}`;
        view.reason = `The PS240 is unavailable after ${failures} consecutive poll failures. The channel is re-read from the router to verify the change.`;
        view.facts = facts(["Requested channel", target ?? "—"], ["Poll failures", `${failures} of ${threshold}`]);
        view.rail = ["done", "done", "now", "todo"];
        view.railNote = "Only the channel number changes. Everything else on the radio is preserved.";
        view.meter = meter;
        view.busy = true;
        view.switchHelp = "A change already in progress finishes first.";
        break;

      case "Waiting for battery":
        view.tone = "success"; view.icon = ICONS.waiting; view.badge = "● Waiting for battery";
        view.kicker = "CHANGE VERIFIED · WAITING";
        view.headline = `Channel ${channel ?? target ?? "—"} verified · waiting for telemetry`;
        view.reason = "The router reports the new channel. Recovery completes when the PS240 answers a poll again.";
        view.facts = facts(["Verified channel", String(channel ?? target ?? "—")], ["Cooldown starts", this._time(attributes.last_attempt_at)]);
        view.rail = ["done", "done", "done", "now"];
        view.railNote = "No further change is attempted for this outage.";
        view.meter = meter;
        view.switchHelp = "Armed. The next outage starts a fresh attempt.";
        break;

      case "Recovered":
        view.tone = "success"; view.icon = ICONS.recovered; view.badge = "● Recovered";
        view.kicker = "RECOVERED · WATCHING"; view.headline = "Battery telemetry is back";
        view.reason = Number.isFinite(lastRecovery)
          ? `Valid PS240 telemetry resumed at ${this._time(lastRecovery)}.`
          : "Valid PS240 telemetry has resumed.";
        view.facts = facts(["Recovered at", this._time(lastRecovery)], ["Channel", String(channel ?? "—")]);
        view.rail = ["done", "done", "done", "done"];
        view.railNote = "This outage is closed. Watching resumes for the next one.";
        view.meter = meter;
        view.switchHelp = "Armed. Turn off to stop automatic changes.";
        break;

      case "Cooldown":
        view.tone = "warning"; view.icon = ICONS.cooldown; view.badge = "● Cooldown";
        view.kicker = "OUTAGE · COOLDOWN"; view.headline = "Cooling down after one channel change";
        view.tick = { lead: "Next change allowed in ", deadline: cooldownEnds };
        view.reason = `The PS240 is still unavailable, but the ${cooldownHours}-hour guard blocks another router change until ${this._time(attributes.next_allowed_attempt_at)}.`;
        view.hint = "Nothing else happens automatically for this outage. A router restart or a manual channel change may still be needed.";
        view.facts = facts(["Blocked until", this._time(attributes.next_allowed_attempt_at)], ["Poll failures", `${failures} of ${threshold}`]);
        view.rail = ["done", "done", "blocked", "todo"];
        view.railNote = "One channel change per outage, then a one-hour pause.";
        view.meter = meter;
        view.switchHelp = "Turn off to stop automatic changes.";
        break;

      case "Configuration required":
        view.tone = "error"; view.icon = ICONS.unconfigured; view.badge = "○ Setup needed";
        view.kicker = "GUARDED RECOVERY · NOT CONFIGURED"; view.headline = "Router not configured";
        view.reason = attributes.reason || "Add the Linksys router address and local administrator credentials in the integration options.";
        view.hint = "Settings → Devices & Services → AFERIY PS240 → Configure.";
        view.facts = facts(["Router", "not configured"], ["Allowed channels", "6 ↔ 11"]);
        // Recovery cannot be armed without credentials, but an already-on switch
        // must stay switchable off.
        view.switchState = on ? "on" : "unavailable";
        view.switchDisabled = !on;
        view.switchHelp = on
          ? "Turn off to stop automatic changes."
          : "Recovery cannot be armed until the router details are saved.";
        break;

      case "Checking router":
        view.tone = "info"; view.icon = ICONS.checking; view.badge = "● Checking router";
        view.kicker = "ENABLING · VALIDATING ACCESS"; view.headline = "Checking local router access";
        view.reason = "Read-only validation of the Linksys address and local sign-in before recovery is armed.";
        view.facts = facts(["Router", router], ["Policy", "no settings changed"]);
        view.switchState = "pending"; view.busy = true;
        view.switchHelp = "Validation in progress.";
        break;

      case "Authentication failed":
        view.tone = "error"; view.icon = ICONS.authFailed; view.badge = "● Sign-in failed";
        view.kicker = "OUTAGE · ROUTER SIGN-IN FAILED"; view.headline = "The router rejected the credentials";
        view.reason = attributes.reason || "The Linksys router refused the local administrator credentials, so no channel change was attempted.";
        view.hint = "Update the Linksys address or sign-in in the integration options. Recovery stays off until a check succeeds.";
        view.facts = facts(["Last result", "authentication failed"], ["Poll failures", `${failures} of ${threshold}`]);
        view.rail = ["done", "done", "blocked", "todo"];
        view.railNote = "The change stopped before the channel was touched. Nothing was altered on the router.";
        view.meter = meter;
        break;

      case "Failed":
        view.tone = "error"; view.icon = ICONS.failed; view.badge = "● Change failed";
        view.kicker = "OUTAGE · CHANGE FAILED"; view.headline = "The channel change could not be verified";
        view.reason = attributes.reason || `The router did not report channel ${target ?? "the new channel"} within ${VERIFY_SECONDS} seconds, so recovery stopped.`;
        view.hint = "No further change is attempted for this outage. Check the router, then let the next outage retry after the cooldown.";
        view.facts = facts(["Last attempt", Number.isFinite(lastAttempt) ? `${this._time(lastAttempt)} · ${this._ago(lastAttempt)}` : "—"], ["Result", "not verified"]);
        view.rail = ["done", "done", "blocked", "todo"];
        view.railNote = "One attempt per outage. The next outage may try again after the cooldown.";
        view.meter = meter;
        break;

      default: /* Off, with the battery reachable or not */
        if (!on && attributes.battery_available === false) {
          view.tone = "warning"; view.icon = ICONS.off; view.badge = "○ Off · battery offline";
          view.kicker = "OUTAGE · RECOVERY OFF"; view.headline = "Battery offline and recovery is off";
          view.reason = `The PS240 has missed ${failures} polls and no channel change will be made.`;
          view.hint = "Turn recovery on to arm automatic changes for the next outage.";
          view.facts = facts(["Battery", "offline"], ["Poll failures", `${failures} of ${threshold}`]);
        } else {
          view.facts = facts(["Battery", "available"], ["Would change", channel ? `${channel} → ${target}` : "6 → 11"]);
          view.hint = "Turn recovery on to allow one verified channel change per Wi-Fi outage.";
        }
    }

    const graceDetail = grace
      ? `${graceMinutes} min · 0 changes the channel immediately`
      : "Unavailable · the number entity was not found";
    view.details = [
      ["Router", router],
      ["Allowed channels", "6 ↔ 11 only · SSID, security and 5 GHz are untouched"],
      ["Trigger", `After ${threshold} consecutive poll failures`],
      ["Cooldown", `${cooldownHours} hour between changes · survives a restart`],
      ["Verification", `Channel re-read from the router within ${VERIFY_SECONDS} seconds`],
      ["Grace period", graceDetail],
      ["Last attempt", Number.isFinite(lastAttempt) ? `${this._time(lastAttempt)} · ${this._ago(lastAttempt)}` : "No attempt yet"],
      ["Last result", RESULT_LABELS[attributes.last_result] || "No attempt yet"],
      ["Last recovery", Number.isFinite(lastRecovery) ? `${this._time(lastRecovery)} · ${this._ago(lastRecovery)}` : "None since setup"],
    ];
    view.note = `${attributes.policy ? `${attributes.policy} ` : ""}The router is only asked for the 2.4 GHz channel number. Credentials never reach the card, the entity attributes or the log.`;
    view.footer = [
      attributes.battery_available === false ? "Battery offline" : "Battery available",
      attributes.last_result === "verified" && channel ? `${router} · channel ${channel}` : router,
    ];
    // A countdown only runs while its deadline is genuinely in the future; an
    // expired deadline becomes a plain sentence until the integration publishes
    // the next status.
    const pending = Math.max(
      status === "Grace period" ? graceEnds : 0,
      status === "Cooldown" ? cooldownEnds : 0,
    );
    if (view.tick && pending > Date.now()) {
      view.deadline = pending;
    } else {
      if (view.tick) view.headline = status === "Cooldown" ? "Cooldown is ending" : "Channel change is due now";
      view.tick = null;
      view.deadline = 0;
    }
    return view;
  }

  /* -------------------------------------------------------------- render -- */

  _styles() {
    return `
      :host { display:block; container-type:inline-size; }
      * { box-sizing:border-box; }
      .wr-card { --wr-tone:var(--primary-color,#4498c3); display:block; padding:0; overflow:hidden; background:var(--ha-card-background,var(--card-background-color)); color:var(--primary-text-color); border-radius:var(--ha-card-border-radius,20px); font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif); font-size:14px; line-height:1.45; }
      .wr-card[data-tone=success] { --wr-tone:var(--success-color,#168366); }
      .wr-card[data-tone=warning] { --wr-tone:var(--warning-color,#a56700); }
      .wr-card[data-tone=error] { --wr-tone:var(--error-color,#db5365); }
      .wr-card[data-tone=idle] { --wr-tone:var(--secondary-text-color,#727272); }
      .wr-card[data-tone=info] { --wr-tone:var(--primary-color,#4498c3); }
      h2,h3,p { margin:0; } b,strong { font-weight:500; }
      button { font:inherit; color:inherit; background:none; border:0; cursor:pointer; }
      button:disabled { cursor:default; opacity:.5; }
      button:focus-visible,summary:focus-visible { outline:2px solid var(--wr-tone); outline-offset:2px; }
      ha-icon { display:block; }
      .wr-muted { color:var(--secondary-text-color); } .wr-small { font-size:12px; }
      .wr-sr { position:absolute; width:1px; height:1px; margin:-1px; padding:0; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }

      .wr-header { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:22px 24px 17px; }
      .wr-title { display:flex; align-items:center; gap:12px; min-width:0; }
      .wr-tile { display:grid; place-items:center; flex:none; width:42px; height:42px; border-radius:14px; color:var(--wr-tone); background:color-mix(in srgb,var(--wr-tone) 14%,var(--ha-card-background,var(--card-background-color))); }
      .wr-tile ha-icon { --mdc-icon-size:22px; }
      h2 { font-size:19px; font-weight:500; overflow-wrap:anywhere; }
      .wr-sub { font-size:12px; margin-top:2px; }
      .wr-badge { flex:none; font-size:12px; color:var(--wr-tone); text-align:right; white-space:nowrap; }

      .wr-hero { margin:0 24px; padding:18px; border-radius:15px; background:color-mix(in srgb,var(--wr-tone) 9%,var(--ha-card-background,var(--card-background-color))); }
      .wr-kicker { color:var(--wr-tone); font-size:11px; font-weight:500; letter-spacing:1px; text-transform:uppercase; }
      h3 { font-size:23px; font-weight:500; letter-spacing:-.5px; margin:6px 0 4px; }
      .wr-reason { font-size:13px; overflow-wrap:anywhere; }
      .wr-hint { margin-top:11px; padding:9px 11px; border-radius:9px; font-size:12px; overflow-wrap:anywhere; border-left:3px solid var(--wr-tone); background:color-mix(in srgb,var(--wr-tone) 12%,transparent); }
      .wr-foot { display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px 14px; font-size:12px; border-top:1px solid var(--divider-color); margin-top:14px; padding-top:12px; }
      .wr-foot span { white-space:nowrap; }

      .wr-sec { border-top:1px solid var(--divider-color); }
      .wr-rail-wrap { padding:17px 24px 15px; }
      .wr-rail { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); margin:0; padding:0; list-style:none; }
      .wr-step { position:relative; display:flex; flex-direction:column; align-items:center; gap:8px; text-align:center; }
      .wr-step::before { content:""; position:absolute; top:6px; left:-50%; width:100%; height:2px; border-radius:2px; background:var(--divider-color); }
      .wr-step:first-child::before { display:none; }
      .wr-step[data-state=done]::before,.wr-step[data-state=now]::before { background:color-mix(in srgb,var(--wr-tone) 60%,transparent); }
      .wr-dot { position:relative; z-index:1; width:12px; height:12px; border-radius:50%; background:var(--secondary-background-color); border:2px solid var(--divider-color); }
      .wr-step[data-state=done] .wr-dot { background:color-mix(in srgb,var(--wr-tone) 60%,transparent); border-color:transparent; }
      .wr-step[data-state=now] .wr-dot { background:var(--wr-tone); border-color:color-mix(in srgb,var(--wr-tone) 40%,transparent); box-shadow:0 0 0 4px color-mix(in srgb,var(--wr-tone) 18%,transparent); }
      .wr-step[data-state=blocked] .wr-dot { background:transparent; border-color:var(--wr-tone); border-style:dashed; }
      .wr-step[data-state=blocked]::before { background:color-mix(in srgb,var(--wr-tone) 45%,transparent); }
      .wr-step span { font-size:12px; color:var(--secondary-text-color); }
      .wr-step[data-state=done] span { color:var(--primary-text-color); }
      .wr-step[data-state=now] span,.wr-step[data-state=blocked] span { color:var(--wr-tone); font-weight:500; }
      .wr-rail-note { margin-top:13px; font-size:12px; color:var(--secondary-text-color); }
      .wr-meter { margin-top:14px; }
      .wr-meter-head { display:flex; justify-content:space-between; gap:10px; font-size:12px; }
      .wr-meter-head b { font-variant-numeric:tabular-nums; }
      .wr-pips { display:flex; gap:5px; margin-top:9px; }
      .wr-pips i { flex:1; height:5px; border-radius:5px; background:var(--secondary-background-color); }
      .wr-pips i.on { background:var(--wr-tone); }
      .wr-bar { height:5px; border-radius:5px; overflow:hidden; margin-top:9px; background:var(--secondary-background-color); }
      .wr-bar>i { display:block; height:100%; border-radius:5px; background:var(--wr-tone); }
      @keyframes wr-pulse { 0%,100% { box-shadow:0 0 0 3px color-mix(in srgb,var(--wr-tone) 16%,transparent); } 50% { box-shadow:0 0 0 7px color-mix(in srgb,var(--wr-tone) 8%,transparent); } }
      .wr-card[data-busy=true] .wr-step[data-state=now] .wr-dot { animation:wr-pulse 1.8s ease-in-out infinite; }

      .wr-controls { padding:9px 24px 13px; }
      .wr-control-row { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:9px 0; }
      .wr-label { font-size:13px; min-width:0; }
      .wr-label small { display:block; margin-top:3px; max-width:34ch; font-size:11px; font-weight:400; color:var(--secondary-text-color); }
      /* The switch keeps the accent colour so it always reads as a control, never
         as a status: state colour stays in the hero, badge, rail and meter. */
      .wr-switch { flex:none; min-width:62px; min-height:36px; padding:6px 14px; border-radius:20px; font-size:13px; border:1px solid var(--divider-color); background:var(--secondary-background-color); }
      .wr-switch[aria-checked=true] { background:var(--primary-color,#4498c3); border-color:transparent; color:var(--text-primary-color,#fff); }
      .wr-stepper { flex:none; display:flex; align-items:center; gap:2px; padding:2px; border-radius:20px; border:1px solid var(--divider-color); background:var(--secondary-background-color); }
      .wr-stepper button { display:grid; place-items:center; width:32px; height:30px; border-radius:16px; font-size:17px; line-height:1; }
      .wr-stepper button:not(:disabled):hover { background:color-mix(in srgb,var(--primary-text-color) 10%,transparent); }
      .wr-value { min-width:56px; text-align:center; font-size:13px; font-variant-numeric:tabular-nums; }
      .wr-error { margin-top:6px; font-size:12px; color:var(--error-color); overflow-wrap:anywhere; }

      .wr-more { border-top:1px solid var(--divider-color); }
      .wr-more>summary { display:flex; align-items:center; gap:8px; padding:14px 24px; font-size:12px; cursor:pointer; color:var(--secondary-text-color); list-style:none; }
      .wr-more>summary::-webkit-details-marker { display:none; }
      .wr-more>summary ha-icon { --mdc-icon-size:16px; }
      .wr-more>summary::after { content:"▾"; margin-left:auto; font-size:11px; }
      .wr-more[open]>summary { color:var(--primary-text-color); }
      .wr-more[open]>summary::after { content:"▴"; }
      .wr-dl { display:grid; grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr); gap:7px 16px; margin:0; padding:2px 24px 10px; font-size:12px; }
      .wr-dl dt { color:var(--secondary-text-color); }
      .wr-dl dd { margin:0; overflow-wrap:anywhere; }
      .wr-note { margin:0; padding:4px 24px 16px; font-size:11px; line-height:1.55; color:var(--secondary-text-color); }
      .wr-footer { display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; padding:12px 24px 14px; border-top:1px solid var(--divider-color); font-size:11px; }
      .wr-footer span { white-space:nowrap; }

      @container (max-width:420px) {
        .wr-header { padding:18px 16px 15px; }
        .wr-tile { width:38px; height:38px; border-radius:12px; }
        h2 { font-size:17px; }
        .wr-hero { margin:0 16px; padding:15px; }
        h3 { font-size:21px; }
        .wr-rail-wrap,.wr-controls { padding-left:16px; padding-right:16px; }
        .wr-more>summary,.wr-dl,.wr-note,.wr-footer { padding-left:16px; padding-right:16px; }
        .wr-step span { font-size:11px; }
      }
      @media (pointer:coarse) { button,summary { min-height:44px!important; } }
      @media (prefers-reduced-motion:reduce) { .wr-card[data-busy=true] .wr-step[data-state=now] .wr-dot { animation:none; } }
    `;
  }

  _heroHeadline(view) {
    if (!view.tick) return this._escape(view.headline);
    // The visible number ticks every second; assistive technology hears the
    // remaining minutes instead of a value that changes continuously.
    const remaining = view.tick.deadline - Date.now();
    const spoken = `under ${Math.max(1, Math.ceil(remaining / MINUTE_MS))} minutes`;
    return `${this._escape(view.tick.lead)}<span data-countdown aria-hidden="true">${this._countdown(remaining)}</span><span class="wr-sr" data-countdown-sr>${this._escape(spoken)}</span>`;
  }

  _railMarkup(view) {
    if (!view.rail) return "";
    const labels = ["Watch", "Wait", "Switch", "Verify"];
    const spoken = { done: "completed", now: "current step", blocked: "blocked", todo: "upcoming" };
    const steps = labels.map((label, index) => {
      const state = view.rail[index];
      return `<li class="wr-step" data-state="${state}"${state === "now" ? ' aria-current="step"' : ""}>
        <i class="wr-dot" aria-hidden="true"></i><span>${label}</span><span class="wr-sr">, ${spoken[state]}</span></li>`;
    }).join("");
    const meter = view.meter
      ? `<div class="wr-meter">
          <div class="wr-meter-head"><span class="wr-muted">${this._escape(view.meter.label)}</span><b>${this._escape(view.meter.value)}</b></div>
          ${view.meter.bar
            ? `<div class="wr-bar"><i style="width:${view.meter.pct}%"></i></div>`
            : `<div class="wr-pips">${Array.from({ length: view.meter.pips }, (_, index) => `<i class="${index < view.meter.filled ? "on" : ""}"></i>`).join("")}</div>`}
        </div>`
      : "";
    return `<section class="wr-sec wr-rail-wrap">
      <ol class="wr-rail" aria-label="Recovery progress">${steps}</ol>
      ${view.railNote ? `<p class="wr-rail-note">${this._escape(view.railNote)}</p>` : ""}
      ${meter}
    </section>`;
  }

  render(recovery, grace) {
    if (!this._hass) return;
    const view = this._view(recovery, grace);
    this._deadline = view.deadline;
    const focus = this._root.activeElement?.dataset.focus;
    // The details block keeps whatever the user opened between renders.
    if (this._root.querySelector(".wr-more")) {
      this._detailsOpen = this._root.querySelector(".wr-more").open;
    }
    const help = (label, text) => `<div class="wr-label">${this._escape(label)}<small>${this._escape(text)}</small></div>`;
    const switchLabel = view.switchState === "on" ? "On"
      : view.switchState === "pending" ? "Checking…"
        : view.switchState === "unavailable" ? "Unavailable" : "Off";
    this._root.innerHTML = `<ha-card class="wr-card" data-tone="${view.tone}" data-busy="${view.busy}">
      <style>${this._styles()}</style>
      <header class="wr-header">
        <div class="wr-title"><span class="wr-tile"><ha-icon icon="${view.icon}"></ha-icon></span>
          <div><h2>${this._escape(view.title)}</h2><div class="wr-sub wr-muted">${this._escape(view.subtitle)}</div></div></div>
        <span class="wr-badge">${this._escape(view.badge)}</span>
      </header>
      <section class="wr-hero" aria-live="polite">
        <div class="wr-kicker">${this._escape(view.kicker)}</div>
        <h3>${this._heroHeadline(view)}</h3>
        <p class="wr-reason wr-muted">${this._escape(view.reason)}</p>
        ${view.hint ? `<p class="wr-hint">${this._escape(view.hint)}</p>` : ""}
        <div class="wr-foot">${view.facts.map((fact) => `<span>${this._escape(fact.label)} <b>${this._escape(fact.value)}</b></span>`).join("")}</div>
      </section>
      ${this._railMarkup(view)}
      <section class="wr-sec wr-controls">
        <div class="wr-control-row">${help("Automatic recovery", view.switchHelp)}
          <button class="wr-switch" role="switch" data-focus="switch" data-action="toggle" aria-label="Automatic recovery"
            aria-checked="${view.switchState === "on"}" ${view.switchDisabled || this._busy ? "disabled" : ""}>${this._busy ? "Working…" : switchLabel}</button>
        </div>
        <div class="wr-control-row">${help("Grace period", view.graceHelp)}
          <div class="wr-stepper" role="group" aria-label="Grace period in minutes">
            <button type="button" data-action="grace-down" data-focus="grace-down" aria-label="Decrease grace period" ${view.grace <= 0 || !grace || this._graceBusy ? "disabled" : ""}>−</button>
            <span class="wr-value" aria-live="polite">${this._escape(`${view.grace} min`)}</span>
            <button type="button" data-action="grace-up" data-focus="grace-up" aria-label="Increase grace period" ${view.grace >= GRACE_MAX_MINUTES || !grace || this._graceBusy ? "disabled" : ""}>+</button>
          </div>
        </div>
        <p class="wr-error" role="alert">${this._escape(this._error || "")}</p>
      </section>
      <details class="wr-more"${this._detailsOpen ? " open" : ""}>
        <summary data-focus="details"><ha-icon icon="mdi:shield-outline"></ha-icon> Guardrails, router and history</summary>
        <dl class="wr-dl">${view.details.map(([label, value]) => `<dt>${this._escape(label)}</dt><dd>${this._escape(value)}</dd>`).join("")}</dl>
        <p class="wr-note">${this._escape(view.note)}</p>
      </details>
      <footer class="wr-footer wr-muted"><span>${this._escape(view.footer[0])}</span><span>${this._escape(view.footer[1])}</span></footer>
    </ha-card>`;
    this._root.querySelector("details.wr-more")?.addEventListener("toggle", (event) => {
      this._detailsOpen = event.target.open;
    });
    this._root.querySelector('[data-action="toggle"]')?.addEventListener("click", () => this._toggle(recovery));
    this._root.querySelector('[data-action="grace-down"]')?.addEventListener("click", () => this._setGrace(grace, view.grace - 1));
    this._root.querySelector('[data-action="grace-up"]')?.addEventListener("click", () => this._setGrace(grace, view.grace + 1));
    if (focus) this._root.querySelector(`[data-focus="${focus}"]`)?.focus();
    this._syncTicker();
  }

  /* ------------------------------------------------------------- actions -- */

  async _toggle(entity) {
    if (!entity || this._busy) return;
    this._busy = true;
    this._error = "";
    this._renderIfNeeded(true);
    try {
      // Only the existing guarded switch is invoked, never a battery or router command.
      await this._hass.callService("switch", entity.state === "on" ? "turn_off" : "turn_on", { entity_id: entity.entity_id });
    } catch (error) {
      this._error = `Recovery could not be changed: ${error?.message || error}`;
    } finally {
      this._busy = false;
      this._renderIfNeeded(true);
    }
  }

  async _setGrace(entity, minutes) {
    if (!entity || this._graceBusy) return;
    const value = Math.max(0, Math.min(GRACE_MAX_MINUTES, Math.round(Number(minutes) || 0)));
    this._graceBusy = true;
    this._error = "";
    this._renderIfNeeded(true);
    try {
      await this._hass.callService("number", "set_value", { entity_id: entity.entity_id, value });
    } catch (error) {
      this._error = `Grace period could not be saved: ${error?.message || error}`;
    } finally {
      this._graceBusy = false;
      this._renderIfNeeded(true);
    }
  }

  /* ------------------------------------------------------------- ticker --- */

  _syncTicker() {
    const pending = Number(this._deadline) > Date.now();
    if (pending && !this._ticker) {
      this._ticker = window.setInterval(() => this._tick(), 1000);
    } else if (!pending) {
      this._stopTicker();
    }
  }

  _stopTicker() {
    if (this._ticker) window.clearInterval(this._ticker);
    this._ticker = null;
  }

  _tick() {
    const remaining = Number(this._deadline) - Date.now();
    if (remaining <= 0) {
      this._stopTicker();
      // The integration publishes the next status; re-render now so the
      // countdown never sits at 0:00 while that update is in flight.
      this._renderIfNeeded(true);
      return;
    }
    const label = this._root.querySelector("[data-countdown]");
    if (label) label.textContent = this._countdown(remaining);
    const spoken = this._root.querySelector("[data-countdown-sr]");
    if (spoken) spoken.textContent = `under ${Math.max(1, Math.ceil(remaining / MINUTE_MS))} minutes`;
  }
}

customElements.define("aferiy-wifi-recovery-card", AferiyWifiRecoveryCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "aferiy-wifi-recovery-card",
  name: "AFERIY Wi-Fi Loss Recovery",
  description: "Guarded Linksys 2.4 GHz channel recovery, with state, progress and opt-in in one card.",
});
