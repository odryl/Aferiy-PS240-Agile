class AferiyAgilePlanCard extends HTMLElement {
  setConfig(config) {
    const nextConfig = config || {};
    const nextSignature = JSON.stringify(nextConfig);
    const configChanged = nextSignature !== this._configSignature;
    this.config = nextConfig;
    this._configSignature = nextSignature;
    if (configChanged) {
      this._renderSignature = null;
      this._openTimelines = null;
      if (this._hass) this._renderIfNeeded(true);
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._renderIfNeeded();
  }

  getCardSize() {
    return 12;
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

  _findSwitch(configured, entitySuffix, friendlyName) {
    if (configured && this._hass.states[configured]) return this._hass.states[configured];
    return Object.values(this._hass.states).find(
      (state) => state.entity_id.startsWith("switch.") && (
        state.entity_id.endsWith(entitySuffix)
        || state.attributes?.friendly_name?.endsWith(friendlyName)
      ),
    );
  }

  _renderIfNeeded(force = false) {
    const today = this._find(this.config.today_entity, "_agile_proposed_plan_today", "Agile Proposed Plan Today");
    const tomorrow = this._find(this.config.tomorrow_entity, "_agile_proposed_plan_tomorrow", "Agile Proposed Plan Tomorrow");
    const shadow = this._find(this.config.shadow_entity, "_agile_shadow_operating_state", "Agile Shadow Operating State");
    const isCosy = (today?.attributes?.tariff_name || tomorrow?.attributes?.tariff_name) === "Cosy Octopus";
    const control = isCosy
      ? this._findSwitch(this.config.cosy_control_entity, "_cosy_automated_control", "Cosy Automated Control")
      : this._findSwitch(this.config.control_entity, "_agile_automated_control", "Agile Automated Control");
    const daylightFlex = isCosy
      ? this._findSwitch(this.config.cosy_daylight_flex_entity, "_cosy_daylight_flex", "Cosy Daylight Flex")
      : null;
    const signature = JSON.stringify([
      today?.entity_id,
      today?.state,
      today?.attributes,
      tomorrow?.entity_id,
      tomorrow?.state,
      tomorrow?.attributes,
      shadow?.entity_id,
      shadow?.state,
      shadow?.attributes?.recommended_operating_mode,
      shadow?.attributes?.reason,
      shadow?.attributes?.planned_slot_start,
      shadow?.attributes?.daylight_flex_margin_minutes,
      control?.entity_id,
      control?.state,
      control?.attributes?.status,
      control?.attributes?.reason,
      control?.attributes?.active_mode,
      daylightFlex?.entity_id,
      daylightFlex?.state,
    ]);
    if (!force && signature === this._renderSignature) return;
    this._renderSignature = signature;
    this.render(today, tomorrow, shadow, control, daylightFlex);
  }

  _timelineStorageKey() {
    return `aferiy-agile-plan-card:open:${this.config.today_entity || "auto"}:${this.config.tomorrow_entity || "auto"}:${this.config.title || "default"}`;
  }

  _loadOpenTimelines() {
    if (this._openTimelines) return;
    this._openTimelines = new Set();
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(this._timelineStorageKey()) || "[]");
      if (Array.isArray(saved)) this._openTimelines = new Set(saved);
    } catch (_error) {
      // Storage can be unavailable in privacy-restricted WebViews; in-memory
      // state still preserves expansion during this card instance's lifetime.
    }
  }

  _saveOpenTimelines() {
    try {
      window.sessionStorage.setItem(
        this._timelineStorageKey(),
        JSON.stringify(Array.from(this._openTimelines)),
      );
    } catch (_error) {
      // Keep the card usable when browser storage is unavailable.
    }
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
    })[character]);
  }

  _money(value, fallback = "—") {
    const number = Number(value);
    return Number.isFinite(number) ? `£${number.toFixed(2)}` : fallback;
  }

  _rate(value) {
    const number = Number(value);
    return Number.isFinite(number) ? `${(number * 100).toFixed(1)}p` : "—";
  }

  _number(value, suffix = "", digits = 1) {
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toFixed(digits)}${suffix}` : "—";
  }

  _priceLimit(name, fallback) {
    const value = Number(this.config[name]);
    return Number.isFinite(value) ? value : fallback;
  }

  _priceTone(rate, cheapestRate) {
    const pence = Number(rate) * 100;
    if (!Number.isFinite(pence)) return "unknown";
    if (pence < 0) return "negative";
    if (Number.isFinite(cheapestRate) && Math.abs(Number(rate) - cheapestRate) < 0.000001) return "cheapest";
    if (pence > this._priceLimit("highlimit", 30)) return "high";
    if (pence > this._priceLimit("mediumlimit", 20)) return "medium";
    if (pence > this._priceLimit("lowlimit", 5)) return "low";
    return "cheap";
  }

  _isCurrent(slot, now) {
    const start = Date.parse(slot.start);
    const end = Date.parse(slot.end);
    return Number.isFinite(start) && Number.isFinite(end) && start <= now && now < end;
  }

  _metric(label, value, tone = "") {
    return `<div class="metric ${tone}"><span>${this._escape(label)}</span><strong>${this._escape(value)}</strong></div>`;
  }

  _slotValue(slot) {
    if (slot.action === "charge") {
      if (slot.tariff_phase === "cheap_charge") {
        const shortfall = Number(slot.cover_shortfall_kwh);
        return `<span class="cost">Cover ${this._number(slot.required_cover_kwh, " kWh", 2)} to ${this._escape(slot.cover_until || "next cheap period")}${Number.isFinite(shortfall) && shortfall > 0 ? `<br><strong>Capacity shortfall ${this._number(shortfall, " kWh", 2)}</strong>` : ""}</span>`;
      }
      return Number(slot.energy_kwh) > 0
        ? `<span class="cost">Cost ${this._money(slot.charge_cost_gbp)}</span>`
        : `<span class="cost">Charge to target</span>`;
    }
    if (slot.action === "discharge") {
      return `<span class="saving">Avoid ${this._money(slot.avoided_import_cost_gbp)}<br>
        Save ${this._money(slot.net_saving_gbp)}</span>`;
    }
    if (slot.action === "self_gen") return `<span class="self-gen">CT-controlled</span>`;
    if (slot.action === "idle") return `<span class="idle">Hold SOC</span>`;
    return "";
  }

  _actionLabel(action, slot = {}) {
    if (slot.tariff_phase === "cheap_charge") {
      const target = Number(slot.slot_target_soc);
      return Number.isFinite(target) ? `Charge / Idle to ${target.toFixed(0)}%` : "Charge / Idle";
    }
    if (action === "self_gen") return "Self-Gen/Zero Export";
    if (action === "idle") return "Idle";
    if (action === "charge") return "Charge";
    if (action === "discharge") return "Self-Gen";
    return action;
  }

  _activeRows(slots, tariffName) {
    const active = slots.filter((slot) => slot.action !== "hold");
    if (!active.length) return `<p class="empty">No charge or discharge periods are proposed.</p>`;
    return `<div class="table-wrap"><table>
      <thead><tr><th>Time</th><th>Plan</th><th>${this._escape(tariffName)} price</th><th>Energy</th><th>Power</th><th>Cost/value</th></tr></thead>
      <tbody>${active.map((slot) => `
        <tr class="${this._escape(slot.action)}">
          <td><strong>${this._escape(slot.local_start)}</strong></td>
          <td><span class="action">${this._escape(this._actionLabel(slot.action, slot))}</span></td>
          <td>${this._rate(slot.rate_gbp_per_kwh)}/kWh</td>
          <td>${this._number(slot.energy_kwh, " kWh", 3)}</td>
          <td>${this._number(slot.power_w, " W", 0)} avg<br><small>≤${this._number(slot.command_power_limit_w, " W", 0)} · ${this._number(slot.duration_minutes, " min", 1)}</small></td>
          <td>${this._slotValue(slot)}</td>
        </tr>`).join("")}</tbody>
    </table></div>`;
  }

  _rateTimeline(slots, cheapestRate, timelineKey, tariffName) {
    if (!slots.length) return "";
    const now = Date.now();
    return `<details data-timeline="${this._escape(timelineKey)}"><summary>All half-hour ${this._escape(tariffName)} prices</summary><div class="rates">
      ${slots.map((slot) => {
        const current = this._isCurrent(slot, now);
        const tone = this._priceTone(slot.rate_gbp_per_kwh, cheapestRate);
        const title = `${slot.local_start}: ${this._rate(slot.rate_gbp_per_kwh)}/kWh · ${this._actionLabel(slot.action, slot)}${current ? " · current period" : ""}`;
        return `<div class="rate ${this._escape(slot.action)} ${this._escape(tone)} ${current ? "current" : ""}" title="${this._escape(title)}">
        <span>${current ? "Now · " : ""}${this._escape(slot.local_start)}</span><strong>${this._rate(slot.rate_gbp_per_kwh)}</strong>
      </div>`;
      }).join("")}
    </div></details>`;
  }

  _day(state, label) {
    if (!state) return `<section><h3>${label}</h3><p>Waiting for the Proposed Plan sensor.</p></section>`;
    const attrs = state.attributes || {};
    const tariffName = attrs.tariff_name || "Octopus Agile";
    const slots = attrs.slots || [];
    const statusClass = String(attrs.status || state.state).toLowerCase().replaceAll("_", "-");
    const conservativeTomorrow = attrs.starting_soc_source === "conservative_reserve_assumption";
    const recoveringReserve = attrs.starting_below_reserve === true;
    const rollingToday = attrs.next_day_rates_used === true;
    const rollingTomorrow = attrs.starting_soc_source === "today_projected_protection_end_soc";
    const cheapestRate = Number(attrs.lowest_future_rate_gbp_per_kwh);
    const currentRate = attrs.current_rate_gbp_per_kwh;
    const cheapestStart = slots.find((slot) => slot.start === attrs.lowest_future_rate_start)?.local_start || "—";
    return `<section>
      <div class="heading">
        <div><h3>${this._escape(label)}</h3><span>${this._escape(attrs.date || "Waiting for rates")}</span></div>
        <span class="status ${this._escape(statusClass)}">${this._escape(state.state)}</span>
      </div>
      <p class="reason">${this._escape(attrs.reason || "")}</p>
      ${recoveringReserve ? `<p class="notice">Battery SOC starts below reserve. The plan prioritises charging back to reserve and will not schedule discharge until that reserve has been recovered.</p>` : ""}
      ${conservativeTomorrow ? `<p class="notice">Tomorrow assumes the battery starts at its reserve SOC; the plan will refine when it becomes Today.</p>` : ""}
      ${rollingToday ? `<p class="notice rolling">Rolling horizon active: tonight's discharge is valued against published refill prices tomorrow.</p>` : ""}
      ${rollingTomorrow ? `<p class="notice rolling">Rolling horizon active: Tomorrow starts from Today's projected ${this._number(attrs.starting_soc, "%", 0)} SOC.</p>` : ""}
      ${attrs.tariff_strategy === "cosy_fixed_daily_schedule" ? `<p class="notice rolling">${this._escape(attrs.schedule_note || "Cosy fixed daily schedule is active.")}</p>` : ""}
      <div class="metrics">
        ${this._metric(`Current ${tariffName} price`, `${this._rate(currentRate)}/kWh`, "price")}
        ${this._metric("Cheapest remaining", `${this._rate(attrs.lowest_future_rate_gbp_per_kwh)}/kWh · ${cheapestStart}`, "price")}
        ${this._metric("Battery SOC", `${this._number(attrs.starting_soc, "%", 0)} → ${this._number(attrs.projected_soc_at_ready_by, "%", 0)}`, "soc")}
        ${this._metric(`SOC after protection`, this._number(attrs.projected_soc_at_protection_end, "%", 0), "soc")}
        ${this._metric(`Grid charge by ${attrs.ready_by || "16:00"}`, this._number(attrs.planned_grid_charge_kwh, " kWh", 2), "charge")}
        ${this._metric("Estimated charge cost", this._money(attrs.estimated_grid_charge_cost_gbp), "charge")}
        ${this._metric(`Discharge to ${attrs.protected_until || "22:00"}`, this._number(attrs.planned_discharge_kwh, " kWh", 2), "discharge")}
        ${this._metric("Peak import avoided", this._money(attrs.estimated_avoided_import_cost_gbp), "discharge")}
        ${this._metric("Estimated net saving", this._money(attrs.estimated_net_saving_gbp), "saving")}
      </div>
      <div class="assumptions">
        <span>Charge avg ${this._rate(attrs.average_planned_charge_rate_gbp_per_kwh)}/kWh</span>
        <span>Discharged-energy replacement ${this._money(attrs.estimated_discharge_replacement_cost_gbp)} at ${this._rate(attrs.delivered_replacement_cost_gbp_per_kwh)}/kWh</span>
        <span>Replacement prices: ${this._escape(attrs.replacement_rate_source === "next_day_published_rates" ? "published tomorrow" : "same day")}</span>
        <span>Reserve ${this._number(attrs.reserve_soc, "%", 0)}</span>
        <span>AC charge limit ${this._number(attrs.max_system_charge_power_w, " W", 0)}</span>
        <span>Self-Gen house output ${this._number(attrs.max_system_discharge_power_w, " W", 0)}</span>
      </div>
      <h4>Battery operating schedule</h4>
      ${this._activeRows(slots, tariffName)}
      ${this._rateTimeline(slots, cheapestRate, label.toLowerCase(), tariffName)}
      <p class="footnote">${this._escape(attrs.cost_estimate_note || "Costs are estimates, not a complete electricity bill.")}</p>
    </section>`;
  }

  render(today, tomorrow, shadow, control, daylightFlex) {
    if (!this._hass) return;
    this._loadOpenTimelines();
    this.querySelectorAll("details[data-timeline]").forEach((details) => {
      if (details.open) this._openTimelines.add(details.dataset.timeline);
      else this._openTimelines.delete(details.dataset.timeline);
    });
    const tariffName = today?.attributes?.tariff_name
      || tomorrow?.attributes?.tariff_name
      || "Octopus Agile";
    const isCosy = tariffName === "Cosy Octopus";
    this.innerHTML = `<ha-card>
      <style>
        ha-card { padding: 16px; overflow: hidden; }
        h2, h3, h4, p { margin: 0; } h2 { font-size: 20px; } h3 { font-size: 18px; }
        h4 { margin: 16px 0 8px; } section { border-top: 1px solid var(--divider-color); padding-top: 16px; margin-top: 16px; }
        .subtitle, .reason, .footnote, .heading span, small { color: var(--secondary-text-color); }
        .subtitle { margin-top: 4px; } .reason { margin-top: 10px; }
        .heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
        .status { border-radius: 999px; background: var(--secondary-background-color); padding: 5px 9px; font-size: 12px; font-weight: 700; }
        .status.proposed { color: var(--success-color, #2e7d32); } .status.invalid, .status.limited { color: var(--error-color, #c62828); }
        .notice { margin-top: 10px; padding: 9px; border-left: 3px solid var(--warning-color, #f9a825); background: var(--secondary-background-color); font-size: 12px; }
        .notice.rolling { border-left-color: var(--success-color, #43a047); }
        .shadow-state { margin-top: 12px; padding: 10px; border-left: 3px solid var(--primary-color); background: var(--secondary-background-color); }
        .shadow-state strong, .shadow-state span { display: block; } .shadow-state span { margin-top: 3px; color: var(--secondary-text-color); font-size: 12px; }
        .metrics { display: grid; grid-template-columns: repeat(3, minmax(120px, 1fr)); gap: 8px; margin: 14px 0 9px; }
        .metric { background: var(--secondary-background-color); border-radius: 10px; padding: 10px; border-left: 3px solid var(--divider-color); }
        .metric span { display: block; color: var(--secondary-text-color); font-size: 11px; margin-bottom: 4px; }
        .metric strong { font-size: 17px; } .metric.charge { border-left-color: #2196f3; } .metric.discharge { border-left-color: #f57c00; }
        .metric.saving { border-left-color: var(--success-color, #43a047); } .metric.soc { border-left-color: #7e57c2; } .metric.price { border-left-color: #00838f; }
        .assumptions { display: flex; flex-wrap: wrap; gap: 6px; }
        .assumptions span { border: 1px solid var(--divider-color); border-radius: 999px; padding: 4px 7px; font-size: 11px; }
        .table-wrap { overflow-x: auto; } table { border-collapse: collapse; width: 100%; min-width: 650px; font-size: 12px; }
        th, td { border-bottom: 1px solid var(--divider-color); padding: 8px 6px; text-align: left; vertical-align: top; }
        .action { text-transform: capitalize; font-weight: 700; } tr.charge .action, .cost { color: #2196f3; } tr.discharge .action { color: #f57c00; }
        tr.self_gen .action, .self-gen { color: #f57c00; } tr.idle .action, .idle { color: #7e57c2; }
        .saving { color: var(--success-color, #43a047); font-weight: 700; } .empty { color: var(--secondary-text-color); padding: 8px 0; }
        details { margin-top: 14px; } summary { cursor: pointer; font-weight: 600; }
        .rates { display: grid; grid-template-columns: repeat(8, minmax(54px, 1fr)); gap: 4px; margin-top: 8px; }
        .rate { background: var(--secondary-background-color); border-radius: 6px; padding: 5px; text-align: center; font-size: 10px; border-bottom: 3px solid transparent; }
        .rate span, .rate strong { display: block; } .rate.charge { border-bottom-color: #2196f3; } .rate.discharge, .rate.self_gen { border-bottom-color: #f57c00; } .rate.idle { border-bottom-color: #7e57c2; }
        .rate.negative { background: #391cd9; color: white; } .rate.cheapest { background: #b9f6ca; color: #102a16; }
        .rate.cheap { background: #d7f5df; color: #12331d; } .rate.low { background: #dcedc8; color: #263b10; }
        .rate.medium { background: #ffe0b2; color: #472400; } .rate.high { background: #ffcdd2; color: #4a1015; }
        .rate.current { outline: 2px solid var(--primary-color); outline-offset: 1px; font-weight: 700; }
        .footnote { margin-top: 12px; font-size: 11px; }
        @media (max-width: 700px) { .metrics { grid-template-columns: repeat(2, minmax(110px, 1fr)); } .rates { grid-template-columns: repeat(4, minmax(54px, 1fr)); } }
      </style>
      <h2>${this._escape(this.config.title || `${tariffName} Battery Plan`)}</h2>
      <p class="subtitle">Today and tomorrow · price-aware planning${control?.state === "on" ? " · automated control enabled" : " · shadow-only while control is off"}</p>
      ${control ? `<div class="shadow-state"><strong>${this._escape(isCosy ? "Cosy" : "Agile")} automated control: ${this._escape(control.state)} · ${this._escape(control.attributes?.status || "Waiting")}</strong><span>${this._escape(control.attributes?.active_mode || "Self-Gen/Zero Export")} · ${this._escape(control.attributes?.reason || `Use the ${isCosy ? "Cosy" : "Agile"} Automated Control entity to opt in`)}</span></div>` : ""}
      ${daylightFlex ? `<div class="shadow-state"><strong>Cosy Daylight Flex: ${this._escape(daylightFlex.state)}</strong><span>13:00–16:00 solar-aware Self-Gen · keeps a 30-minute cheap-rate charging reserve${Number.isFinite(Number(shadow?.attributes?.daylight_flex_margin_minutes)) ? ` · ${this._number(shadow.attributes.daylight_flex_margin_minutes, " min", 1)} margin now` : ""}</span></div>` : ""}
      ${shadow ? `<div class="shadow-state"><strong>${this._escape(tariffName)} operating state: ${this._escape(shadow.state)}</strong><span>${control?.state === "on" ? "Using" : "Would use"} ${this._escape(shadow.attributes?.recommended_operating_mode || "Self-Gen/Zero Export")} · ${this._escape(shadow.attributes?.reason || "Waiting for a decision")}</span></div>` : ""}
      ${this._day(today, "Today")}
      ${this._day(tomorrow, "Tomorrow")}
    </ha-card>`;
    this.querySelectorAll("details[data-timeline]").forEach((details) => {
      details.open = this._openTimelines.has(details.dataset.timeline);
      details.addEventListener("toggle", () => {
        if (details.open) this._openTimelines.add(details.dataset.timeline);
        else this._openTimelines.delete(details.dataset.timeline);
        this._saveOpenTimelines();
      });
    });
  }
}

customElements.define("aferiy-agile-plan-card", AferiyAgilePlanCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "aferiy-agile-plan-card",
  name: "AFERIY Octopus Battery Plan",
  description: "View Octopus Agile or Cosy rates, plans, and control status.",
});
