class AferiyAgilePlanCard extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return 8;
  }

  _find(configured, entitySuffix, friendlyName) {
    if (configured && this._hass.states[configured]) return this._hass.states[configured];
    return Object.values(this._hass.states).find(
      (state) => state.entity_id.startsWith("sensor.") && (
        state.entity_id.endsWith(entitySuffix)
        || state.attributes?.friendly_name?.endsWith(friendlyName)
      ),
    );
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
    })[character]);
  }

  _day(state, label) {
    if (!state) return `<section><h3>${label}</h3><p>Waiting for Proposed Plan sensor.</p></section>`;
    const attrs = state.attributes || {};
    const active = (attrs.slots || []).filter((slot) => slot.action !== "hold");
    const rows = active.map((slot) => `
      <tr class="${this._escape(slot.action)}">
        <td>${this._escape(slot.local_start)}</td>
        <td>${this._escape(slot.action)}</td>
        <td>£${this._escape(slot.rate_gbp_per_kwh)}/kWh</td>
        <td>${this._escape(slot.energy_kwh)} kWh · ${this._escape(slot.power_w)} W avg<br>
          ≤${this._escape(slot.command_power_limit_w)} W for ${this._escape(slot.duration_minutes)} min</td>
      </tr>`).join("");
    return `<section>
      <div class="heading"><h3>${label} · ${this._escape(attrs.date || "Waiting")}</h3>
        <span>${this._escape(state.state)}</span></div>
      <p>${this._escape(attrs.reason)}</p>
      <div class="metrics">
        <b>${this._escape(attrs.planned_grid_charge_kwh ?? "—")} kWh charge</b>
        <b>${this._escape(attrs.planned_discharge_kwh ?? "—")} kWh discharge</b>
        <b>800 W discharge cap</b>
      </div>
      ${rows ? `<table><thead><tr><th>Time</th><th>Action</th><th>Rate</th><th>Planned energy and power</th></tr></thead><tbody>${rows}</tbody></table>` : ""}
    </section>`;
  }

  render() {
    if (!this._hass) return;
    const today = this._find(
      this.config.today_entity,
      "_agile_proposed_plan_today",
      "Agile Proposed Plan Today",
    );
    const tomorrow = this._find(
      this.config.tomorrow_entity,
      "_agile_proposed_plan_tomorrow",
      "Agile Proposed Plan Tomorrow",
    );
    this.innerHTML = `<ha-card>
      <style>
        ha-card { padding: 14px; } h2, h3, p { margin: 0 0 9px; }
        section { border-top: 1px solid var(--divider-color); padding-top: 12px; margin-top: 12px; }
        .heading, .metrics { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
        .heading span { color: var(--secondary-text-color); }
        .metrics { margin: 8px 0; font-size: 12px; }
        table { border-collapse: collapse; width: 100%; font-size: 12px; }
        th, td { border-bottom: 1px solid var(--divider-color); padding: 6px; text-align: left; }
        tr.charge td:nth-child(2) { color: #2196f3; font-weight: 700; }
        tr.discharge td:nth-child(2) { color: #f57c00; font-weight: 700; }
      </style>
      <h2>${this._escape(this.config.title || "Octopus Agile Proposed Plan")}</h2>
      <p>Shadow mode — this schedule cannot control the battery.</p>
      ${this._day(today, "Today")}
      ${this._day(tomorrow, "Tomorrow")}
    </ha-card>`;
  }
}

customElements.define("aferiy-agile-plan-card", AferiyAgilePlanCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "aferiy-agile-plan-card",
  name: "AFERIY Agile Proposed Plan",
  description: "View today and tomorrow's shadow Octopus Agile battery plan.",
});
