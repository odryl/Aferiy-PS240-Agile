class AferiyWifiRecoveryCard extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const recovery = this._findRecoverySwitch();
    const grace = this._findGraceNumber(recovery);
    const signature = JSON.stringify([
      recovery?.entity_id,
      recovery?.state,
      recovery?.attributes,
      grace?.entity_id,
      grace?.state,
    ]);
    if (signature === this._signature) return;
    this._signature = signature;
    this._render(recovery, grace);
  }

  getCardSize() {
    return 5;
  }

  _findRecoverySwitch() {
    const configured = this.config?.entity;
    if (configured && this._hass.states[configured]) return this._hass.states[configured];
    return Object.values(this._hass.states).find(
      (state) => state.entity_id.startsWith("switch.") && (
        state.entity_id.endsWith("_wifi_loss_recovery")
        || state.attributes?.friendly_name?.endsWith("Wi-Fi Loss Recovery")
      ),
    );
  }

  _findGraceNumber(recovery = this._findRecoverySwitch()) {
    const configured = this.config?.grace_entity;
    if (configured && this._hass.states[configured]) return this._hass.states[configured];
    const matchingEntity = recovery?.entity_id
      ?.replace(/^switch\./, "number.")
      .replace(/_wifi_loss_recovery$/, "_wifi_recovery_grace_period");
    if (matchingEntity && this._hass.states[matchingEntity]) return this._hass.states[matchingEntity];
    return Object.values(this._hass.states).find(
      (state) => state.entity_id.startsWith("number.") && (
        state.entity_id.endsWith("_wifi_recovery_grace_period")
        || state.attributes?.friendly_name?.endsWith("Wi-Fi Recovery Grace Period")
      ),
    );
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
    })[character]);
  }

  _time(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? this._escape(value) : parsed.toLocaleString();
  }

  _metric(label, value) {
    return `<div class="metric"><span>${this._escape(label)}</span><strong>${this._escape(value ?? "—")}</strong></div>`;
  }

  async _toggle(entity) {
    if (!entity || this._busy) return;
    this._busy = true;
    this._render(entity);
    try {
      await this._hass.callService(
        "switch",
        entity.state === "on" ? "turn_off" : "turn_on",
        { entity_id: entity.entity_id },
      );
    } finally {
      this._busy = false;
      const recovery = this._findRecoverySwitch();
      this._render(recovery, this._findGraceNumber(recovery));
    }
  }

  async _setGrace(entity, value) {
    if (!entity || this._graceBusy) return;
    const minutes = Math.max(0, Math.min(60, Number.parseInt(value, 10) || 0));
    this._graceBusy = true;
    this._render(this._findRecoverySwitch(), entity);
    try {
      await this._hass.callService("number", "set_value", {
        entity_id: entity.entity_id,
        value: minutes,
      });
    } finally {
      this._graceBusy = false;
      const recovery = this._findRecoverySwitch();
      this._render(recovery, this._findGraceNumber(recovery));
    }
  }

  _render(recovery = this._findRecoverySwitch(), grace = this._findGraceNumber(recovery)) {
    if (!this._hass) return;
    if (!recovery) {
      this.innerHTML = `<ha-card><style>ha-card{padding:16px}</style><h2>Wi-Fi loss recovery</h2><p>
        Waiting for the AFERIY Wi-Fi Loss Recovery entity. Configure the integration and reload it.
      </p></ha-card>`;
      return;
    }
    const attrs = recovery.attributes || {};
    const channel = attrs.current_2_4ghz_channel;
    const nextChannel = channel === 6 ? 11 : channel === 11 ? 6 : "—";
    const statusClass = String(attrs.status || "off").toLowerCase().replaceAll(" ", "-");
    const buttonLabel = this._busy
      ? "Working…"
      : recovery.state === "on" ? "Disable recovery" : "Enable recovery";
    const buttonDisabled = this._busy || (recovery.state !== "on" && attrs.configured === false);
    this.innerHTML = `<ha-card>
      <style>
        ha-card { padding: 16px; overflow: hidden; }
        h2, p { margin: 0; } h2 { font-size: 20px; }
        .heading { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }
        .status { border-radius:999px; padding:5px 9px; font-size:12px; font-weight:700; background:var(--secondary-background-color); }
        .status.monitoring, .status.recovered, .status.waiting-for-battery { color:var(--success-color,#2e7d32); }
        .status.failed, .status.authentication-failed, .status.configuration-required { color:var(--error-color,#c62828); }
        .reason { color:var(--secondary-text-color); margin-top:8px; }
        .metrics { display:grid; grid-template-columns:repeat(3,minmax(100px,1fr)); gap:8px; margin:14px 0; }
        .metric { background:var(--secondary-background-color); border-radius:10px; padding:10px; border-left:3px solid var(--primary-color); }
        .metric span, .footnote { display:block; color:var(--secondary-text-color); font-size:11px; }
        .metric strong { display:block; margin-top:4px; font-size:16px; }
        .grace-control { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:0 0 14px; padding:10px; background:var(--secondary-background-color); border-radius:10px; }
        .grace-control label { font-weight:600; }
        .grace-control small { display:block; color:var(--secondary-text-color); font-weight:400; margin-top:2px; }
        .grace-control input { width:76px; padding:8px; border:1px solid var(--divider-color); border-radius:7px; color:var(--primary-text-color); background:var(--card-background-color); font:inherit; }
        button { width:100%; border:0; border-radius:10px; padding:11px; color:var(--text-primary-color); background:var(--primary-color); font-weight:700; cursor:pointer; }
        button.off { background:var(--secondary-background-color); color:var(--primary-text-color); }
        button:disabled { opacity:.6; cursor:wait; }
        .footnote { margin-top:10px; }
        @media(max-width:600px){.metrics{grid-template-columns:repeat(2,minmax(100px,1fr));}}
      </style>
      <div class="heading"><div><h2>${this._escape(this.config.title || "Wi-Fi loss recovery")}</h2>
        <p class="reason">PS240 unavailable → Linksys channel 6 ↔ 11</p></div>
        <span class="status ${this._escape(statusClass)}">${this._escape(attrs.status || recovery.state)}</span>
      </div>
      <p class="reason">${this._escape(attrs.reason || "Waiting for status")}</p>
      <div class="metrics">
        ${this._metric("Battery", attrs.battery_available ? "Available" : "Unavailable")}
        ${this._metric("Current channel", channel)}
        ${this._metric("Next recovery", nextChannel)}
        ${this._metric("Poll failures", `${attrs.current_consecutive_failures ?? 0} / ${attrs.trigger_after_consecutive_failures ?? 6}`)}
        ${this._metric("Grace period", `${attrs.grace_period_minutes ?? grace?.state ?? 0} min`)}
        ${this._metric("Last result", attrs.last_result || "No attempt")}
        ${this._metric("Last attempt", this._time(attrs.last_attempt_at))}
        ${attrs.grace_period_ends_at ? this._metric("Change due", this._time(attrs.grace_period_ends_at)) : ""}
      </div>
      ${grace ? `<div class="grace-control">
        <label for="wifi-grace">Grace period<small>0 changes immediately; valid telemetry cancels the wait.</small></label>
        <input id="wifi-grace" type="number" min="0" max="60" step="1" value="${this._escape(grace.state)}" ${this._graceBusy ? "disabled" : ""} aria-label="Wi-Fi recovery grace period in minutes">
      </div>` : ""}
      <button class="${recovery.state === "on" ? "" : "off"}" ${buttonDisabled ? "disabled" : ""}>${buttonLabel}</button>
      <p class="footnote">One verified channel change per outage. Recovery during the grace period cancels it; a one-hour cooldown prevents repeats.</p>
    </ha-card>`;
    this.querySelector("button")?.addEventListener("click", () => this._toggle(recovery));
    this.querySelector("#wifi-grace")?.addEventListener("change", (event) => this._setGrace(grace, event.target.value));
  }
}

customElements.define("aferiy-wifi-recovery-card", AferiyWifiRecoveryCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "aferiy-wifi-recovery-card",
  name: "AFERIY Wi-Fi Loss Recovery",
  description: "Monitor and opt in to guarded Linksys 2.4 GHz channel recovery.",
});
