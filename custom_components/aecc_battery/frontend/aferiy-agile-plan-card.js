class AferiyAgilePlanCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    this._timer = window.setInterval(() => {
      if (this._hass && this.config) this._renderIfNeeded();
    }, 30000);
    if (this._hass && this.config) this._renderIfNeeded(true);
  }

  disconnectedCallback() {
    window.clearInterval(this._timer);
  }

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

  _findEntity(configured, domain, entitySuffix, friendlyName) {
    if (configured) return this._hass.states[configured];
    let candidates = Object.values(this._hass.states).filter(
      state => state.entity_id.startsWith(`${domain}.`) && (
        state.entity_id.endsWith(entitySuffix)
        || state.attributes?.friendly_name?.endsWith(friendlyName)
      ),
    );
    if (this._entityReference) {
      const deviceId = this._hass.entities?.[this._entityReference.entity_id]?.device_id;
      if (deviceId) {
        candidates = candidates.filter(state => this._hass.entities?.[state.entity_id]?.device_id === deviceId);
      } else {
        const prefix = this._entityReference.entity_id.replace(/^sensor\./, "")
          .replace(/_agile_proposed_plan_(today|tomorrow)$/, "");
        const sameDevice = candidates.filter(state => state.entity_id.split(".")[1].startsWith(`${prefix}_`));
        // Without registry data, ambiguous matches must be configured explicitly.
        if (sameDevice.length || /_agile_proposed_plan_(today|tomorrow)$/.test(this._entityReference.entity_id)) candidates = sameDevice;
      }
    }
    return candidates.length === 1 ? candidates[0] : undefined;
  }

  _find(configured, entitySuffix, friendlyName) {
    return this._findEntity(configured, "sensor", entitySuffix, friendlyName);
  }

  _findSwitch(configured, entitySuffix, friendlyName) {
    return this._findEntity(configured, "switch", entitySuffix, friendlyName);
  }

  _renderIfNeeded(force = false) {
    if (!this.config || !this._hass) return;
    this._entityReference = null;
    const today = this._find(this.config.today_entity, "_agile_proposed_plan_today", "Agile Proposed Plan Today");
    this._entityReference = today;
    const tomorrow = this._find(this.config.tomorrow_entity, "_agile_proposed_plan_tomorrow", "Agile Proposed Plan Tomorrow");
    this._entityReference = today || tomorrow;
    const shadow = this._find(this.config.shadow_entity, "_agile_shadow_operating_state", "Agile Shadow Operating State");
    const availablePv = this._find(this.config.available_pv_entity, "_available_pv_power", "Available PV Power");
    const isCosy = (today?.attributes?.tariff_name || tomorrow?.attributes?.tariff_name) === "Cosy Octopus";
    const control = isCosy
      ? this._findSwitch(this.config.cosy_control_entity, "_cosy_automated_control", "Cosy Automated Control")
      : this._findSwitch(this.config.control_entity, "_agile_automated_control", "Agile Automated Control");
    const daylightFlex = isCosy
      ? this._findSwitch(this.config.cosy_daylight_flex_entity, "_cosy_daylight_flex", "Cosy Daylight Flex")
      : null;
    this._forecast = this._find(this.config.forecast_entity, "_planning_solar_forecast", "Planning Solar Forecast");
    this._outcomes = this._find(this.config.outcomes_entity, "_daily_plan_outcomes", "Daily Plan Outcomes");
    const signature = JSON.stringify([
      this._forecast, this._outcomes,
      today?.entity_id,
      today?.state,
      today?.attributes,
      tomorrow?.entity_id,
      tomorrow?.state,
      tomorrow?.attributes,
      shadow?.entity_id,
      shadow?.state,
      shadow?.attributes,
      isCosy ? Math.floor(Date.now() / 30000) : null,
      shadow?.attributes?.recommended_operating_mode,
      shadow?.attributes?.reason,
      shadow?.attributes?.planned_slot_start,
      shadow?.attributes?.daylight_flex_margin_minutes,
      availablePv?.entity_id,
      availablePv?.state,
      availablePv?.attributes?.source,
      availablePv?.attributes?.configured_estimate_status,
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
    this.render(today, tomorrow, shadow, control, daylightFlex, availablePv);
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
    const number = value == null || value === "" ? NaN : Number(value);
    return Number.isFinite(number) ? `£${number.toFixed(2)}` : fallback;
  }

  _rate(value) {
    const number = value == null || value === "" ? NaN : Number(value);
    return Number.isFinite(number) ? `${(number * 100).toFixed(1)}p` : "—";
  }

  _number(value, suffix = "", digits = 1) {
    const number = value == null || value === "" ? NaN : Number(value);
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
      if (slot.tariff_phase === "free_energy") {
        return `<span class="free-energy">Free import<br><strong>${this._money(slot.credited_back_gbp)} credited back</strong></span>`;
      }
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
    if (slot.tariff_phase === "free_energy") {
      const target = Number(slot.slot_target_soc);
      return Number.isFinite(target) ? `Free-power charge to ${target.toFixed(0)}%` : "Free-power charge";
    }
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

  _cosyPeriodPrice(period) {
    const minimum = this._cosyNumber(period.minimum_rate_gbp_per_kwh);
    const maximum = this._cosyNumber(period.maximum_rate_gbp_per_kwh);
    if (Number.isFinite(minimum) && Number.isFinite(maximum) && Math.abs(maximum - minimum) > 0.000001) {
      return `${this._rate(minimum)}–${this._rate(maximum)}/kWh`;
    }
    return `${this._rate(period.rate_gbp_per_kwh)}/kWh`;
  }

  _cosyPeriodRows(periods) {
    if (!periods.length) return `<p class="empty">Waiting for the validated Cosy operating periods.</p>`;
    const now = Date.now();
    return `<div class="cosy-periods">
      ${periods.map((period) => {
        const current = this._isCurrent(period, now);
        const target = Number(period.slot_target_soc);
        const shortfall = Number(period.cover_shortfall_kwh);
        const purpose = period.tariff_phase === "free_energy"
          ? `Octopus Weekend Happy Hour · import credited back, so charge to ${Number.isFinite(target) ? `${target.toFixed(0)}%` : "target"} regardless of tariff band`
          : period.action === "charge"
          ? `PV-first charge / Idle to ${Number.isFinite(target) ? `${target.toFixed(0)}%` : "target"} · cover to ${this._escape(period.cover_until || "next cheap period")}${Number.isFinite(shortfall) && shortfall > 0 ? ` · <strong>${this._number(shortfall, " kWh", 2)} capacity shortfall</strong>` : ""}`
          : period.cosy_rate_band === "peak"
            ? "Peak protection · CT-controlled household supply"
            : "Self-consumption · CT-controlled zero export";
        return `<div class="cosy-period ${this._escape(period.action)} ${period.tariff_phase === "free_energy" ? "free" : ""} ${current ? "current" : ""}">
          <div class="period-time"><strong>${current ? "Now · " : ""}${this._escape(period.local_start)}–${this._escape(period.local_end)}</strong><span>${period.tariff_phase === "free_energy" ? "free power" : `${this._escape(period.cosy_rate_band || "standard")} rate`}</span></div>
          <div class="period-plan"><strong>${this._escape(this._actionLabel(period.action, period))}</strong><span>${purpose}</span></div>
          <div class="period-price"><strong>${this._cosyPeriodPrice(period)}</strong><span>${this._number(period.duration_minutes, " min", 0)}</span></div>
        </div>`;
      }).join("")}
    </div>`;
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
    const isCosy = attrs.tariff_strategy === "cosy_fixed_daily_schedule";
    const slots = attrs.slots || [];
    const cosyPeriods = Array.isArray(attrs.cosy_periods) ? attrs.cosy_periods : [];
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
        <span>Battery capacity ${this._number(attrs.battery_capacity_kwh, " kWh", 3)}</span>
        <span>AC charge limit ${this._number(attrs.max_system_charge_power_w, " W", 0)}</span>
        <span>Self-Gen house output ${this._number(attrs.max_system_discharge_power_w, " W", 0)}</span>
      </div>
      <h4>${isCosy ? "Cosy tariff and operating periods" : "Battery operating schedule"}</h4>
      ${isCosy ? this._cosyPeriodRows(cosyPeriods) : this._activeRows(slots, tariffName)}
      ${isCosy ? "" : this._rateTimeline(slots, cheapestRate, label.toLowerCase(), tariffName)}
      <p class="footnote">${this._escape(attrs.cost_estimate_note || "Costs are estimates, not a complete electricity bill.")}</p>
    </section>`;
  }

  _cosyNumber(value) {
    return value === null || value === undefined || value === "" ? NaN : Number(value);
  }

  _cosyTime(value) {
    const date = new Date(value);
    if (!value || !Number.isFinite(date.getTime())) return "—";
    return new Intl.DateTimeFormat(this._hass.locale?.language || "en-GB", {
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
      timeZone: this._hass.config?.time_zone || "Europe/London",
    }).format(date);
  }

  _cosyValid(state) {
    return state && !["unavailable", "unknown"].includes(state.state)
      && ["proposed", "limited"].includes(state.attributes?.status);
  }

  _cosyRows(periods, today) {
    return periods.map((period) => {
      const current = today && this._isCurrent(period, Date.now());
      const charge = period.action === "charge";
      const free = period.tariff_phase === "free_energy";
      const target = this._number(this._cosyNumber(period.slot_target_soc), "%", 0);
      const band = ["cheap", "peak", "standard"].includes(period.cosy_rate_band) ? period.cosy_rate_band : "standard";
      return `<div class="co-row${current ? " co-current" : ""}${free ? " co-row-free" : ""}">
        <div class="co-time">${this._escape(period.local_start)}–${this._escape(period.local_end)}${current ? '<span class="co-now">● Now</span>' : ""}</div>
        <div><div class="co-action">${free ? `Free power · charge to ${target}` : charge ? `Charge to ${target}` : "Supply home"}</div>
          <div class="co-muted co-small">${free ? "Octopus Weekend Happy Hour · import credited back" : charge ? `Then hold · cover to ${this._escape(period.cover_until || "next cheap period")}` : band === "peak" ? "Peak protection · zero export" : "Self-Gen · zero export"}</div>
          ${Number(period.cover_shortfall_kwh) > 0 ? `<div class="co-warning co-small">Capacity shortfall ${this._number(period.cover_shortfall_kwh, " kWh", 2)}</div>` : ""}</div>
        <div class="co-rate">${this._cosyPeriodPrice(period).replace("/kWh", "")}<span class="co-muted co-small"><i class="co-dot ${free ? "cheap" : band}"></i>${free ? "free power" : `${band} · /kWh`}</span></div>
      </div>`;
    }).join("");
  }

  _cosyDetails(attrs, availablePv) {
    const freeKwh = this._cosyNumber(attrs.happy_hour_grid_charge_kwh);
    const freeCredit = this._cosyNumber(attrs.estimated_happy_hour_credit_gbp);
    const happyHourFields = Number(freeKwh) > 0 ? [
      ["Happy Hour grid charge", this._number(freeKwh, " kWh", 2)],
      ["Happy Hour credit", `${this._money(freeCredit)} at the local unit rate, capped at 16 kWh per hour by Octopus`],
    ] : [];
    const fields = [
      ["Plan starting SOC", this._number(this._cosyNumber(attrs.starting_soc), "%", 0)],
      ["Projected ready-by SOC", this._number(this._cosyNumber(attrs.projected_soc_at_ready_by), "%", 0)],
      ["SOC after protection", this._number(this._cosyNumber(attrs.projected_soc_at_protection_end), "%", 0)],
      ["Estimated charging cost", this._money(this._cosyNumber(attrs.estimated_grid_charge_cost_gbp))],
      ...happyHourFields,
      ["Avoided import value", this._money(this._cosyNumber(attrs.estimated_avoided_import_cost_gbp))],
      ["Discharged-energy replacement", this._money(this._cosyNumber(attrs.estimated_discharge_replacement_cost_gbp))],
      ["Average charge rate", `${this._rate(this._cosyNumber(attrs.average_planned_charge_rate_gbp_per_kwh))}/kWh`],
      ["Delivered replacement rate", `${this._rate(this._cosyNumber(attrs.delivered_replacement_cost_gbp_per_kwh))}/kWh`],
      ["Replacement prices", attrs.replacement_rate_source === "cosy_remaining_cheap_average" ? "Mean remaining Cosy cheap rate" : attrs.replacement_rate_source === "next_day_published_rates" ? "Published tomorrow" : "Same day"],
      ["Planned home supply to midnight", this._number(this._cosyNumber(attrs.planned_discharge_kwh), " kWh", 2)],
      ["Battery capacity", this._number(this._cosyNumber(attrs.battery_capacity_kwh), " kWh", 3)],
      ["Reserve / charge limit", `${this._number(this._cosyNumber(attrs.reserve_soc), "%", 0)} / ${this._number(this._cosyNumber(attrs.charge_limit_soc ?? attrs.target_soc), "%", 0)}`],
      ["AC charge / home supply limit", `${this._number(this._cosyNumber(attrs.max_system_charge_power_w), " W", 0)} / ${this._number(this._cosyNumber(attrs.cosy_max_battery_output_w ?? attrs.max_system_discharge_power_w), " W", 0)}`],
      ["Available PV power", this._number(this._cosyNumber(availablePv?.state), " W", 0)],
      ["PV source", availablePv?.attributes?.source === "configured_available_pv_estimate" ? "Configured uncurtailed estimate" : availablePv ? "Measured live PV" : "Unavailable"],
    ];
    return `<dl>${fields.map(([label, value]) => `<dt>${this._escape(label)}</dt><dd>${this._escape(value)}</dd>`).join("")}</dl>
      <p>${this._escape(attrs.schedule_note || "Targets are calculated separately for each cheap period.")}</p>
      ${attrs.starting_soc_source === "conservative_reserve_assumption" ? "<p>Tomorrow assumes the battery starts at reserve; this will refine when it becomes Today.</p>" : ["today_projected_protection_end_soc", "today_projected_day_end_soc"].includes(attrs.starting_soc_source) ? "<p>Tomorrow starts from today's projected ending SOC.</p>" : ""}
      ${(attrs.happy_hour_warnings || []).length ? `<p>${this._escape((attrs.happy_hour_warnings || []).join(" "))}</p>` : ""}
      <p>${this._escape(attrs.cost_estimate_note || "Estimates cover planned battery actions, not your total electricity bill.")}</p>`;
  }

  _renderCosy(today, tomorrow, shadow, control, daylightFlex, availablePv) {
    const now = Date.now();
    const isToday = this._selectedDay !== "tomorrow";
    const selected = isToday ? today : tomorrow;
    const attrs = selected?.attributes || {};
    const live = today?.attributes || {};
    const decision = shadow?.attributes || {};
    const validToday = this._cosyValid(today);
    const validDay = this._cosyValid(selected);
    const periods = validDay && Array.isArray(attrs.cosy_periods) ? attrs.cosy_periods : [];
    const livePeriods = validToday && Array.isArray(live.cosy_periods) ? live.cosy_periods : [];
    const current = livePeriods.find(period => this._isCurrent(period, now));
    const tomorrowPeriods = this._cosyValid(tomorrow) && Array.isArray(tomorrow.attributes.cosy_periods) ? tomorrow.attributes.cosy_periods : [];
    const upcoming = [...livePeriods, ...tomorrowPeriods].filter(period => Date.parse(period.end) > now);
    const targetPeriod = upcoming.find(period => period.action === "charge");
    const next = upcoming.find(period => Date.parse(period.start) > now);
    const lastTelemetry = Date.parse(decision.connection_last_successful_update);
    const staleAfter = this._cosyNumber(decision.connection_stale_after_seconds);
    const fresh = shadow && !["unavailable", "unknown", "Connection Fail-safe"].includes(shadow.state)
      && Number.isFinite(lastTelemetry) && Number.isFinite(staleAfter) && now - lastTelemetry <= staleAfter * 1000;
    const soc = fresh ? this._cosyNumber(decision.soc_percent) : NaN;
    const reserve = this._cosyNumber(decision.reserve_soc ?? live.reserve_soc);
    // Daylight Flex can raise the current cheap-window target to the live charge limit.
    const target = this._cosyNumber(current?.action === "charge" && fresh
      ? decision.target_soc ?? targetPeriod?.slot_target_soc : targetPeriod?.slot_target_soc);
    const auto = control?.state === "on";
    const controllerStatus = control?.attributes?.status || "Waiting";
    const enableRejected = control?.state === "off" && controllerStatus === "Inhibited";
    const active = auto && controllerStatus === "Active";
    const blocked = (auto && !active) || ["Inhibited", "Restore pending", "Fail-safe"].includes(controllerStatus);
    const mode = active ? control.attributes.active_mode : decision.recommended_operating_mode;
    const labels = { "Charge": "Charging", "Idle": "Holding battery", "Self-Gen/Zero Export": "Supplying home" };
    let headline = labels[mode] || "Waiting for a decision";
    if (mode === "Charge" && Number.isFinite(target)) headline = `Charging to ${target.toFixed(0)}%`;
    if (["Cosy Solar Wait", "Forecast Solar Wait"].includes(shadow?.state) && mode === "Idle") headline = "Waiting for solar";
    if (shadow?.state === "Solar Charge Deferred" && mode === "Self-Gen/Zero Export") headline = "Making use of solar";
    if (!validToday || !current) headline = "Waiting for valid rates";
    if (!fresh) headline = "Battery data unavailable";
    if (blocked) headline = enableRejected ? "Couldn’t enable automatic control" : `Control ${controllerStatus.toLowerCase()}`;
    const reason = blocked ? control.attributes.reason : !fresh ? "Waiting for fresh battery telemetry."
      : !validToday || !current ? live.reason || "A validated current-day plan is unavailable."
      : active ? control.attributes.reason || decision.reason : decision.reason;
    const latestStart = Date.parse(decision.latest_grid_charge_start);
    const margin = Number.isFinite(latestStart) ? Math.max(0, Math.ceil((latestStart - now) / 60000)) : NaN;
    const solarWait = fresh && current && validToday && !blocked && ["Cosy Solar Wait", "Forecast Solar Wait"].includes(shadow?.state);
    const earlier = isToday ? periods.filter(period => Date.parse(period.end) <= now) : [];
    const remaining = isToday ? periods.filter(period => Date.parse(period.end) > now) : periods;
    const shortfalls = remaining.filter(period => Number(period.cover_shortfall_kwh) > 0);
    const title = this.config.title || "Cosy Octopus";
    const focusKey = this._root.activeElement?.dataset.focus;
    const alert = message => `<p class="co-alert" role="status">${this._escape(message)}</p>`;
    this._root.innerHTML = `<ha-card class="co-card">
      <style>${this._cosyStyles()}</style>
      <header class="co-header"><div class="co-title"><ha-icon icon="mdi:battery-charging-outline"></ha-icon><div><h2>${this._escape(title)}</h2><div class="co-muted co-small">Battery plan · AFERIY</div></div></div>
        <span class="co-badge ${active ? "co-success" : "co-muted"}">${auto ? `● Auto · ${this._escape(controllerStatus)}` : control?.state === "off" ? (enableRejected ? "○ Couldn’t enable" : "○ Plan only") : "Control unavailable"}</span></header>
      <section class="co-hero" aria-live="polite"><div class="co-kicker">${active ? "NOW" : auto || blocked ? "CONTROLLER" : "PROPOSED · CONTROL OFF"}${current ? ` · ${this._escape(current.cosy_rate_band)} RATE` : ""}</div>
        <h3>${this._escape(headline)}</h3><div class="co-muted co-reason">${this._escape(reason || "Waiting for a controller decision.")}</div>
        ${!auto ? '<p class="co-small">Automatic control is off. This plan is advisory.</p>' : ""}
        <div class="co-hero-foot"><span>${solarWait && Number.isFinite(margin) ? `Grid charge in <strong>${margin} min</strong>, if needed` : `Mode: ${this._escape(mode || "Unavailable")}`}</span><span>${current ? `${this._cosyPeriodPrice(current)} until ${this._escape(current.local_end)}` : "Rate unavailable"}</span></div></section>
      ${!fresh ? alert("Live battery data is unavailable or stale. Charge progress cannot be confirmed.") : ""}
      <section class="co-battery"><div class="co-battery-head"><div class="co-soc">${this._number(soc, "%", 0)} <span class="co-muted co-small">Battery now</span></div><div class="co-target">${Number.isFinite(target) && targetPeriod ? `<strong>${this._number(target, "%", 0)}</strong> target by ${this._escape(targetPeriod.local_end)}${Date.parse(targetPeriod.start) >= Date.parse(tomorrowPeriods[0]?.start) ? ' tomorrow' : ''}` : 'Target unavailable'}</div></div>
        <div class="co-track" role="img" aria-label="${this._escape(`Battery ${this._number(soc, "%", 0)}, reserve ${this._number(reserve, "%", 0)}, target ${this._number(target, "%", 0)}`)}">
          ${Number.isFinite(soc) ? `<div class="co-fill" style="width:${Math.max(0, Math.min(100, soc))}%"></div>` : ""}
          ${Number.isFinite(reserve) ? `<i class="co-reserve" style="left:${Math.max(0, Math.min(100, reserve))}%"></i>` : ""}
          ${Number.isFinite(target) ? `<i class="co-marker" style="left:${Math.max(0, Math.min(100, target))}%"></i>` : ""}</div>
        <div class="co-battery-foot co-muted co-small"><span>${this._number(reserve, "%", 0)} reserve</span><span>${next ? `Next: ${next.action === "charge" ? "charge" : "supply home"} · ${this._escape(next.local_start)}–${this._escape(next.local_end)}` : 'Next period unavailable'}</span></div></section>
      <section class="co-plan"><div class="co-plan-head"><div class="co-tabs" role="tablist" aria-label="Plan day"><button role="tab" id="co-today" data-day="today" data-focus="today" aria-selected="${isToday}" aria-controls="co-day">Today</button><button role="tab" id="co-tomorrow" data-day="tomorrow" data-focus="tomorrow" aria-selected="${!isToday}" aria-controls="co-day">Tomorrow</button></div><span class="co-muted co-small">${this._escape(attrs.date || (isToday ? "Today" : "Tomorrow"))}</span></div>
        <div id="co-day" role="tabpanel" aria-labelledby="co-${isToday ? "today" : "tomorrow"}">
          ${Number(attrs.charge_target_shortfall_kwh) > 0 ? alert(`Charging time shortfall · ${this._number(attrs.charge_target_shortfall_kwh, " kWh", 2)} of stored energy cannot be added before the charge deadlines.`) : ""}
          ${attrs.starting_below_reserve ? alert("Battery SOC starts below reserve. Charging back to reserve takes priority.") : ""}
          ${shortfalls.length ? alert("Capacity shortfall · Some demand cannot be covered within your battery limits. Grid import may be needed; amounts are shown below.") : ""}
          ${earlier.length ? `<details data-timeline="cosy-earlier"><summary data-focus="earlier">Earlier today · ${earlier.length} periods</summary>${this._cosyRows(earlier, true)}</details>` : ""}
          ${remaining.length ? this._cosyRows(remaining, isToday) : `<p class="co-empty">${this._escape(attrs.reason || "Waiting for validated Cosy operating periods.")}</p>`}
          <div class="co-metrics"><div><span class="co-muted co-small">Estimated net value${attrs.estimate_scope === "remaining_day" ? " · remaining" : ""}</span><strong>${this._money(validDay ? this._cosyNumber(attrs.estimated_net_saving_gbp) : NaN)}</strong></div><div><span class="co-muted co-small">Planned grid charge</span><strong>${this._number(validDay ? this._cosyNumber(attrs.planned_grid_charge_kwh) : NaN, " kWh", 2)}</strong></div></div>
          ${validDay ? `<details data-timeline="cosy-details-${isToday ? "today" : "tomorrow"}"><summary data-focus="details">Cost breakdown &amp; plan details</summary><div class="co-detail">${this._cosyDetails(attrs, availablePv)}</div></details>` : ""}
        </div></section>
      ${this._planningContext(shadow)}
      <footer class="co-footer co-muted co-small"><span>${fresh ? `Battery updated ${this._cosyTime(decision.connection_last_successful_update)}` : "Battery update unavailable"} · ${validDay ? "Rates validated" : "Rates unavailable"}</span></footer>
      <details class="co-controls" data-timeline="cosy-controls"><summary data-focus="controls"><ha-icon icon="mdi:tune-variant"></ha-icon> Controls</summary><div class="co-control-content">${this._cosySwitch(control, "Automatic control · beta", "auto")}${this._cosySwitch(daylightFlex, "Daylight Flex · 13:00–16:00", "flex")}<p class="co-muted co-small">Automatic control switches off after a restart. Configured forecasts can enable safe solar waits. Daylight Flex also permits afternoon waiting without a forecast, while grid catch-up time remains.</p><p class="co-error" role="alert">${this._escape(this._controlError || "")}</p></div></details>
    </ha-card>`;
    this._bindTimelines();
    this._root.querySelectorAll("[data-day]").forEach(button => {
      button.addEventListener("click", () => { this._selectedDay = button.dataset.day; this._renderIfNeeded(true); });
      button.addEventListener("keydown", event => {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          this._selectedDay = event.key === "Home" ? "today" : event.key === "End" ? "tomorrow" : isToday ? "tomorrow" : "today";
          this._renderIfNeeded(true);
          this._root.querySelector(`[data-day="${this._selectedDay}"]`).focus();
        }
      });
    });
    this._root.querySelectorAll("button[data-switch]").forEach(button => {
      button.addEventListener("click", () => this._toggleCosySwitch(button.dataset.switch));
    });
    if (focusKey) this._root.querySelector(`[data-focus="${focusKey}"]`)?.focus();
  }

  _planningContext(shadow) {
    const forecast = this._forecast?.attributes || {};
    const retrieved = Date.parse(forecast.retrieved_at);
    const fresh = this._forecast?.state === "available" && Number.isFinite(retrieved)
      && Date.now() >= retrieved && Date.now() - retrieved <= 45 * 60000;
    const decision = shadow?.attributes || {};
    const decisionAge = Date.now() - Date.parse(decision.connection_last_successful_update);
    const decisionFresh = Number.isFinite(decisionAge) && decisionAge >= 0
      && decisionAge <= Number(decision.connection_stale_after_seconds) * 1000;
    const periods = fresh && Array.isArray(forecast.periods) ? forecast.periods : [];
    const future = periods.filter(p => Date.parse(p.end) > Date.now() && Number(p.kwh) > 0);
    const dateTime = value => {
      if (!value) return "Unavailable";
      const d = new Date(value);
      return Number.isFinite(d.getTime()) ? new Intl.DateTimeFormat("en-GB", {
        timeZone: this._hass.config.time_zone, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
      }).format(d) : "Unavailable";
    };
    const reason = fresh ? (future.length ? `Next forecast solar: ${dateTime(future[0].start)} · ${this._number(future[0].kwh, " kWh", 2)} in that hour`
      : "No upcoming solar energy in the retrieved forecast.")
      : this._forecast?.state === "not_configured" ? "Select a solar forecast provider in Home Assistant’s Energy Dashboard."
      : "Forecast unavailable or stale; the usual charging plan remains in force.";
    const days = Array.isArray(this._outcomes?.attributes?.days) ? this._outcomes.attributes.days.slice(0, 7) : [];
    const storage = this._outcomes?.attributes?.storage_status;
    return `<section class="plan-context"><style>
      .plan-context { margin:16px; font-size:13px; line-height:1.5; }
      .plan-context p { margin:8px 0; } .plan-context summary { cursor:pointer; font-weight:600; }
      .plan-context details { padding:8px 0; border-top:1px solid var(--divider-color); }
      .plan-context .outcome-metrics { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:8px 0; }
      .plan-context .outcome-note { color:var(--secondary-text-color); font-size:12px; }
      .plan-context ul { padding-left:20px; } .plan-context li { margin:5px 0; }
      </style><strong>Solar outlook · targets come first</strong><p>${this._escape(reason)}</p>
      ${fresh ? `<p class="outcome-note">Retrieved ${this._escape(dateTime(forecast.retrieved_at))}. Provider issue time may differ.</p>` : ""}
      ${fresh && decisionFresh && decision.forecast_jit ? `<p>Grid backup by <strong>${this._escape(dateTime(decision.latest_grid_charge_start))}</strong> for the ${this._escape(dateTime(decision.charge_deadline))} target.${decision.target_reachable_on_grid === false ? " Available grid time is already insufficient; charging is needed now." : ""}</p>` : ""}
      <details data-timeline="forecast-explanation"><summary>How solar changes charging</summary>
        <p>Forecasts can delay paid charging to leave space for solar. They never lower your target. The latest safe start reserves enough time for the entire battery shortfall on grid alone, plus a safety margin. Real solar may reduce that shortfall as it arrives.</p>
        <p>Cosy uses the end of the current cheap period. Agile only waits within a reserved charging half-hour, preserving its chosen prices. Booked free-power periods keep their charging priority. Missing forecasts use the existing plan and Daylight Flex setting.</p>
        <p>Energy and cost projections remain a zero-forecast baseline; actual solar and interruptions can change the outcome.</p>
      </details>
      <details data-timeline="daily-outcomes"><summary>What happened · daily history</summary>
        <p class="outcome-note">${this._escape(this._outcomes?.attributes?.comparison_note || "History starts after the updated integration is installed. Missing observations are not zero use.")}</p>
        ${this._outcomes && ["unavailable", "unknown", "telemetry_gap"].includes(this._outcomes.state) ? '<p>History has a telemetry gap; values below are partial observations.</p>' : ""}
        ${storage && storage !== "ready" ? `<p role="alert">History storage: ${this._escape(storage)}. Recent observations may not survive a restart.</p>` : ""}
        ${days.length ? days.map(day => `<details data-timeline="outcome-${this._escape(day.date)}"><summary>${this._escape(day.date)} · ${Number(day.observed_seconds) > 0 ? this._number(day.ac_charge_kwh, " kWh AC", 2) : "No observations"} · ${this._number(day.coverage_percent, "% coverage", 0)}</summary>
          <div class="outcome-metrics"><span>Estimated purchased charging<br><strong>${Number(day.grid_observed_seconds) > 0 ? this._number(day.grid_charge_kwh, " kWh", 2) : "Unavailable"}</strong></span>
          <span>Priced charging estimate<br><strong>${Number(day.grid_observed_seconds) > 0 && Math.abs(Number(day.priced_charge_kwh) - Number(day.grid_charge_kwh)) < .0001 ? this._money(day.charge_cost_gbp) : "Incomplete pricing"}</strong></span>
          ${Number(day.happy_hour_credit_gbp) > 0 ? `<span>Happy Hour credit estimate<br><strong>${this._money(day.happy_hour_credit_gbp)}</strong></span>` : ""}
          <span>Solar waits while active<br><strong>${this._number(day.solar_wait_minutes, " min", 1)}</strong></span><span>Interruptions / inhibitions<br><strong>${this._number(day.interruptions, "", 0)}</strong></span></div>
          <p class="outcome-note">Last observation: ${this._escape(dateTime(day.last_observed_at))}</p>
          <p>Plan captured ${this._escape(dateTime(day.plan_captured_at))}: ${this._number(day.plan_grid_charge_kwh, " kWh", 2)} remaining. Observed AC since capture: ${day.plan_captured_at ? this._number(day.ac_since_plan_kwh, " kWh", 2) : "Unavailable"}.</p>
          <ul>${(day.targets || []).map(t => `<li>${this._escape(dateTime(t.at))}: target ${this._number(t.target_soc, "%", 0)} · ${this._escape(t.result)}${t.observed_soc != null ? ` (${this._number(t.observed_soc, "% observed", 0)})` : ""}${t.automation_on === false ? " · automation off" : ""}</li>`).join("")}</ul>
          ${(day.events || []).length ? `<p>Recent controller changes</p><ul>${day.events.slice(-3).map(e => `<li>${this._escape(dateTime(e.at))} · ${this._escape(e.state)}: ${this._escape(e.reason)}</li>`).join("")}</ul>` : ""}
        </details>`).join("") : "<p>No daily observations yet.</p>"}
        <p class="outcome-note">${this._escape(this._outcomes?.attributes?.grid_allocation_note || "AC charging can include external solar. Purchased energy requires site grid telemetry.")} Costs use known tariff rates and booked Happy Hour credits; they are not a bill. No realised savings are claimed. Up to 14 days are retained locally; the latest seven appear here.</p>
      </details></section>`;
  }

  _cosySwitch(entity, label, key) {
    const available = entity && ["on", "off"].includes(entity.state);
    return `<div class="co-control-row"><span>${label}</span><button type="button" role="switch" data-focus="${key}" data-switch="${this._escape(entity?.entity_id || "")}" aria-label="${label}" aria-checked="${entity?.state === "on"}" ${!available || this._pendingSwitches?.has(entity.entity_id) ? "disabled" : ""}>${available ? entity.state === "on" ? "On" : "Off" : "Unavailable"}</button></div>`;
  }

  async _toggleCosySwitch(entityId) {
    const state = this._hass.states[entityId];
    if (!entityId.startsWith("switch.") || !state || !["on", "off"].includes(state.state)) return;
    this._pendingSwitches ||= new Set();
    if (this._pendingSwitches.has(entityId)) return;
    this._pendingSwitches.add(entityId);
    this._controlError = "";
    this._renderIfNeeded(true);
    try {
      // Only the existing guarded switch is invoked, never a battery mode command.
      await this._hass.callService("switch", state.state === "on" ? "turn_off" : "turn_on", { entity_id: entityId });
    } catch (error) {
      this._controlError = `Control could not be changed: ${error.message || error}`;
    } finally {
      this._pendingSwitches.delete(entityId);
      this._renderIfNeeded(true);
    }
  }

  _bindTimelines() {
    this._root.querySelectorAll("details[data-timeline]").forEach((details) => {
      details.open = this._openTimelines.has(details.dataset.timeline);
      details.addEventListener("toggle", () => {
        if (!details.isConnected) return;
        if (details.open) this._openTimelines.add(details.dataset.timeline);
        else this._openTimelines.delete(details.dataset.timeline);
        this._saveOpenTimelines();
      });
    });
  }

  _cosyStyles() {
    return `
      :host { display:block; container-type:inline-size; }
      * { box-sizing:border-box; }
      .co-card { --co-accent:var(--primary-color,#7350b5); color:var(--primary-text-color); overflow:hidden; padding:0; border-radius:var(--ha-card-border-radius,20px); font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif); font-size:14px; line-height:1.45; }
      h2,h3,p { margin:0; } button { font:inherit; color:inherit; cursor:pointer; } button:disabled { cursor:default; opacity:.55; }
      .co-muted { color:var(--secondary-text-color); } .co-small { font-size:12px; } .co-warning { color:var(--warning-color,#a56700); } .co-success { color:var(--success-color,#168366); }
      .co-header { padding:22px 24px 17px; display:flex; align-items:center; justify-content:space-between; gap:12px; }
      .co-title { display:flex; align-items:center; gap:12px; min-width:0; } .co-title>ha-icon { padding:10px; width:42px; height:42px; flex:none; border-radius:14px; background:color-mix(in srgb,var(--co-accent) 10%,var(--ha-card-background,var(--card-background-color))); color:var(--co-accent); }
      h2 { font-size:19px; font-weight:500; overflow-wrap:anywhere; } .co-badge { font-size:12px; text-align:right; }
      .co-hero { margin:0 24px; padding:18px; border-radius:15px; background:color-mix(in srgb,var(--co-accent) 9%,var(--ha-card-background,var(--card-background-color))); }
      .co-kicker { color:var(--co-accent); font-size:11px; font-weight:500; letter-spacing:1px; text-transform:uppercase; } h3 { font-size:23px; font-weight:500; letter-spacing:-.5px; margin:5px 0 3px; } .co-reason { font-size:13px; overflow-wrap:anywhere; }
      .co-hero p { margin-top:8px; } .co-hero-foot { border-top:1px solid var(--divider-color); padding-top:12px; margin-top:13px; display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; font-size:12px; }
      .co-battery { padding:20px 24px; } .co-battery-head,.co-battery-foot { display:flex; justify-content:space-between; align-items:baseline; gap:12px; } .co-battery-foot span:last-child { text-align:right; }
      .co-soc { font-size:28px; font-weight:500; white-space:nowrap; } .co-soc span { font-weight:400; } .co-target { text-align:right; font-size:13px; }
      .co-track { height:7px; background:var(--secondary-background-color); border-radius:8px; position:relative; margin:10px 0; } .co-fill { height:100%; border-radius:8px; background:var(--co-accent); } .co-marker,.co-reserve { position:absolute; width:2px; height:13px; top:-3px; transform:translateX(-1px); background:var(--primary-text-color); } .co-reserve { background:var(--secondary-text-color); height:11px; top:-2px; }
      .co-plan { border-top:1px solid var(--divider-color); padding:17px 24px 0; } .co-plan-head { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:13px; }
      .co-tabs { display:flex; background:var(--secondary-background-color); padding:3px; gap:4px; border-radius:10px; } .co-tabs button { border:0; border-radius:7px; background:transparent; min-height:36px; padding:6px 12px; font-size:13px; } .co-tabs button[aria-selected=true] { background:var(--ha-card-background,var(--card-background-color)); box-shadow:0 1px 4px #00000015; font-weight:500; }
      .co-row { display:grid; grid-template-columns:90px minmax(0,1fr) minmax(70px,auto); gap:12px; align-items:center; padding:11px 0; border-bottom:1px solid var(--divider-color); font-size:13px; }
      .co-time { font-size:12px; font-variant-numeric:tabular-nums; } .co-now { display:block; color:var(--co-accent); font-size:11px; font-weight:500; margin-top:3px; } .co-action { font-weight:500; } .co-row .co-small { font-size:11px; } .co-rate { text-align:right; font-weight:500; font-variant-numeric:tabular-nums; } .co-rate span { display:block; font-weight:400; } .co-dot { display:inline-block; height:5px; width:5px; border-radius:50%; margin-right:4px; vertical-align:middle; background:var(--secondary-text-color); } .co-dot.cheap { background:var(--success-color,#168366); } .co-dot.peak { background:var(--error-color,#db5365); }
      details { border-bottom:1px solid var(--divider-color); } summary { cursor:pointer; padding:13px 0; font-size:12px; color:var(--secondary-text-color); } summary:focus-visible,button:focus-visible { outline:2px solid var(--co-accent); outline-offset:2px; }
      .co-metrics { display:grid; grid-template-columns:1fr 1fr; gap:12px; padding:17px 0 2px; } .co-metrics strong { display:block; font-size:20px; font-weight:500; margin-top:3px; }
      .co-detail { color:var(--secondary-text-color); font-size:12px; padding-bottom:14px; } dl { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:7px; margin:0; } dt,dd { margin:0; overflow-wrap:anywhere; } dd { text-align:right; color:var(--primary-text-color); } .co-detail p { margin-top:12px; }
      .co-alert { padding:12px; margin:12px 24px 0; border-radius:10px; color:var(--primary-text-color); border-left:3px solid var(--warning-color,#a56700); background:var(--secondary-background-color); font-size:12px; } .co-plan .co-alert { margin:0 0 10px; } .co-empty { color:var(--secondary-text-color); padding:14px 0; }
      .co-footer { padding:13px 24px 0; font-size:11px; } .co-controls { margin:0 24px; border:0; } .co-controls summary { text-align:right; } .co-controls ha-icon { --mdc-icon-size:17px; margin-right:4px; } .co-control-content { padding-bottom:16px; } .co-control-row { display:flex; justify-content:space-between; gap:12px; align-items:center; padding:8px 0; font-size:13px; } .co-control-row button { border:1px solid var(--divider-color); border-radius:20px; min-width:54px; min-height:36px; padding:6px 12px; background:var(--secondary-background-color); } .co-control-row button[aria-checked=true] { background:var(--co-accent); color:var(--text-primary-color,#fff); } .co-error { font-size:12px; color:var(--error-color); margin-top:8px; overflow-wrap:anywhere; }
      @container(max-width:420px) { .co-header { padding:18px 16px; } .co-title>ha-icon { display:none; } h2 { font-size:17px; } .co-hero { margin:0 16px; padding:15px; } .co-battery,.co-plan { padding-left:16px; padding-right:16px; } .co-row { grid-template-columns:76px minmax(0,1fr) minmax(64px,auto); gap:8px; } .co-footer { padding-left:16px; padding-right:16px; } .co-controls { margin:0 16px; } .co-alert { margin-left:16px; margin-right:16px; } }
      @media(pointer:coarse) { button,summary { min-height:44px!important; } }
    `;
  }

  render(today, tomorrow, shadow, control, daylightFlex, availablePv) {
    if (!this._hass) return;
    this._loadOpenTimelines();
    this._root.querySelectorAll("details[data-timeline]").forEach((details) => {
      if (details.open) this._openTimelines.add(details.dataset.timeline);
      else this._openTimelines.delete(details.dataset.timeline);
    });
    const tariffName = today?.attributes?.tariff_name
      || tomorrow?.attributes?.tariff_name
      || "Octopus Agile";
    const isCosy = tariffName === "Cosy Octopus";
    if (isCosy) {
      this._renderCosy(today, tomorrow, shadow, control, daylightFlex, availablePv);
      return;
    }
    this._root.innerHTML = `<ha-card>
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
        .cosy-periods { display: grid; gap: 7px; }
        .cosy-period { display: grid; grid-template-columns: minmax(120px, .8fr) minmax(250px, 2fr) minmax(105px, .8fr); gap: 12px; align-items: center; padding: 10px; border-radius: 9px; background: var(--secondary-background-color); border-left: 4px solid #f57c00; }
        .cosy-period.charge { border-left-color: #2196f3; }
        .cosy-period.free { border-left-color: #168366; background: rgba(22, 131, 102, .10); }
        .co-row-free { background: rgba(22, 131, 102, .10); box-shadow: inset 3px 0 0 #168366; }
        .free-energy { color: #168366; font-weight: 700; }
        tr.charge .free-energy, tr.charge .cost.free-energy { color: #168366; } .cosy-period.current { outline: 2px solid var(--primary-color); outline-offset: 1px; }
        .cosy-period span { display: block; margin-top: 3px; color: var(--secondary-text-color); font-size: 11px; }
        .period-price { text-align: right; }
        details { margin-top: 14px; } summary { cursor: pointer; font-weight: 600; }
        .rates { display: grid; grid-template-columns: repeat(8, minmax(54px, 1fr)); gap: 4px; margin-top: 8px; }
        .rate { background: var(--secondary-background-color); border-radius: 6px; padding: 5px; text-align: center; font-size: 10px; border-bottom: 3px solid transparent; }
        .rate span, .rate strong { display: block; } .rate.charge { border-bottom-color: #2196f3; } .rate.discharge, .rate.self_gen { border-bottom-color: #f57c00; } .rate.idle { border-bottom-color: #7e57c2; }
        .rate.negative { background: #391cd9; color: white; } .rate.cheapest { background: #b9f6ca; color: #102a16; }
        .rate.cheap { background: #d7f5df; color: #12331d; } .rate.low { background: #dcedc8; color: #263b10; }
        .rate.medium { background: #ffe0b2; color: #472400; } .rate.high { background: #ffcdd2; color: #4a1015; }
        .rate.current { outline: 2px solid var(--primary-color); outline-offset: 1px; font-weight: 700; }
        .footnote { margin-top: 12px; font-size: 11px; }
        @media (max-width: 700px) { .metrics { grid-template-columns: repeat(2, minmax(110px, 1fr)); } .rates { grid-template-columns: repeat(4, minmax(54px, 1fr)); } .cosy-period { grid-template-columns: 1fr; gap: 6px; } .period-price { text-align: left; } }
      </style>
      <h2>${this._escape(this.config.title || `${tariffName} Battery Plan`)}</h2>
      <p class="subtitle">Today and tomorrow · price-aware planning${control?.state === "on" ? " · automated control enabled" : " · shadow-only while control is off"}</p>
      ${control ? `<div class="shadow-state"><strong>${this._escape(isCosy ? "Cosy" : "Agile")} automated control: ${this._escape(control.state)} · ${this._escape(control.attributes?.status || "Waiting")}</strong><span>${this._escape(control.attributes?.active_mode || "Self-Gen/Zero Export")} · ${this._escape(control.attributes?.reason || `Use the ${isCosy ? "Cosy" : "Agile"} Automated Control entity to opt in`)}</span></div>` : ""}
      ${daylightFlex ? `<div class="shadow-state"><strong>Cosy Daylight Flex: ${this._escape(daylightFlex.state)}</strong><span>13:00–16:00 PV-first Idle · 1,200 W AC only from the latest safe start${Number.isFinite(Number(shadow?.attributes?.daylight_flex_margin_minutes)) ? ` · ${this._number(shadow.attributes.daylight_flex_margin_minutes, " min", 1)} until forced charge` : ""}</span></div>` : ""}
      ${availablePv ? `<div class="shadow-state"><strong>Available PV power: ${this._number(availablePv.state, " W", 0)}</strong><span>${this._escape(availablePv.attributes?.source === "configured_available_pv_estimate" ? "Using the configured uncurtailed PV estimate" : "Using measured live PV")}${availablePv.attributes?.configured_estimate_status && availablePv.attributes.configured_estimate_status !== "not_configured" ? ` · estimate ${this._escape(availablePv.attributes.configured_estimate_status)}` : ""}</span></div>` : ""}
      ${shadow ? `<div class="shadow-state"><strong>${this._escape(tariffName)} operating state: ${this._escape(shadow.state)}</strong><span>${control?.state === "on" ? "Using" : "Would use"} ${this._escape(shadow.attributes?.recommended_operating_mode || "Self-Gen/Zero Export")} · ${this._escape(shadow.attributes?.reason || "Waiting for a decision")}</span></div>` : ""}
      ${this._planningContext(shadow)}
      ${this._day(today, "Today")}
      ${this._day(tomorrow, "Tomorrow")}
    </ha-card>`;
    this._bindTimelines();
  }
}

customElements.define("aferiy-agile-plan-card", AferiyAgilePlanCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "aferiy-agile-plan-card",
  name: "AFERIY Octopus Battery Plan",
  description: "View Octopus Agile or Cosy rates, plans, and control status.",
});
