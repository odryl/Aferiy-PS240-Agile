"""Pure Octopus Agile rate parsing and shadow-plan generation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

_SAFE_AGILE_CHARGE_POWER_CEILING_W = 1200
_SAFE_AGILE_DISCHARGE_POWER_CEILING_W = 1000
_DEFAULT_MINIMUM_SAVING_GBP_PER_KWH = 0.03
_REQUIRED_SOURCE_ATTRIBUTES = ("mpan", "serial_number", "tariff_code")
_PLANNER_REVISION = 3
_SHADOW_DECISION_REVISION = 1


def validate_octopus_rate_source(
    entity_id: str,
    platform: str | None,
    attributes: Mapping[str, Any],
    counterpart_attributes: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return reasons an event cannot be trusted as an Agile import source."""
    errors: list[str] = []
    if not entity_id.startswith("event."):
        errors.append("The selected rate source is not an event entity.")
    if platform != "octopus_energy":
        errors.append("The selected rate source is not owned by the Octopus Energy integration.")
    if "_export_" in entity_id or bool(attributes.get("is_export")):
        errors.append("An export-rate entity cannot be used for import planning.")
    for attribute in _REQUIRED_SOURCE_ATTRIBUTES:
        if not str(attributes.get(attribute) or "").strip():
            errors.append(f"The rate source is missing required {attribute} metadata.")
    tariff_code = str(attributes.get("tariff_code") or "")
    if tariff_code and "AGILE" not in tariff_code.upper():
        errors.append("The selected import tariff is not an Octopus Agile tariff.")

    if counterpart_attributes is not None:
        for attribute in _REQUIRED_SOURCE_ATTRIBUTES:
            primary = str(attributes.get(attribute) or "").strip()
            counterpart = str(counterpart_attributes.get(attribute) or "").strip()
            if not counterpart:
                errors.append(f"The counterpart rate source is missing required {attribute} metadata.")
            elif primary and primary != counterpart:
                errors.append(f"Current-day and next-day rate entities have different {attribute}.")
    return errors


@dataclass(frozen=True)
class AgileRate:
    """One Octopus import-rate period, priced in GBP/kWh."""

    start: datetime
    end: datetime
    value_inc_vat: float

    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


def parse_octopus_rates(raw_rates: Any) -> tuple[list[AgileRate], list[str]]:
    """Parse BottlecapDave rate attributes without trusting malformed input."""
    parsed: list[AgileRate] = []
    errors: list[str] = []
    if not isinstance(raw_rates, list):
        return [], ["The source entity has no rates list."]

    for index, item in enumerate(raw_rates):
        if not isinstance(item, dict):
            errors.append(f"Rate {index + 1} is not an object.")
            continue
        try:
            start = datetime.fromisoformat(str(item["start"]))
            end = datetime.fromisoformat(str(item["end"]))
            value = float(item["value_inc_vat"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"Rate {index + 1} has invalid start, end, or value_inc_vat.")
            continue
        if not isfinite(value):
            errors.append(f"Rate {index + 1} has a non-finite value_inc_vat.")
            continue
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            errors.append(f"Rate {index + 1} has an invalid time range.")
            continue
        duration_minutes = (end - start).total_seconds() / 60
        if not 29.0 <= duration_minutes <= 31.0:
            errors.append(f"Rate {index + 1} is not a 30-minute period.")
            continue
        parsed.append(AgileRate(start, end, value))

    parsed.sort(key=lambda rate: rate.start)
    for previous, current in pairwise(parsed):
        if current.start < previous.end:
            errors.append(f"Rates overlap at {current.start.isoformat()}.")
    return parsed, errors


def _invalid_plan(reason: str, errors: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": "invalid",
        "reason": reason,
        "validation_errors": errors or [reason],
        "control_enabled": False,
        "slots": [],
    }


def _next_half_hour_boundary(moment: datetime) -> datetime:
    """Return the first 30-minute boundary at or after a timezone-aware time."""
    if moment.tzinfo is None:
        raise ValueError("Rate coverage time must include a timezone.")
    rounded = moment.replace(second=0, microsecond=0)
    remainder = rounded.minute % 30
    if remainder:
        rounded += timedelta(minutes=30 - remainder)
    return rounded


def _validate_actionable_coverage(
    rates: list[AgileRate],
    *,
    expected_date: date,
    local_zone: ZoneInfo,
    planning_time: datetime,
    protected_until: time,
) -> tuple[int, list[str]]:
    """Validate all plan-eligible periods through protection end, including DST."""
    day_start = datetime.combine(expected_date, time.min, tzinfo=local_zone)
    next_day_start = datetime.combine(expected_date + timedelta(days=1), time.min, tzinfo=local_zone)
    coverage_start = max(day_start, _next_half_hour_boundary(planning_time))
    coverage_end = min(
        next_day_start,
        datetime.combine(expected_date, protected_until, tzinfo=local_zone),
    )
    expected_periods = int(
        max(
            0,
            (coverage_end.astimezone(UTC) - coverage_start.astimezone(UTC)).total_seconds()
            / 1800,
        )
    )
    actionable_rates = [
        rate
        for rate in rates
        if coverage_start <= rate.start < coverage_end
    ]
    errors: list[str] = []
    if len(actionable_rates) != expected_periods:
        errors.append(
            f"Expected {expected_periods} consecutive actionable periods from "
            f"{coverage_start.isoformat()} to {coverage_end.isoformat()} for "
            f"{expected_date.isoformat()}, "
            f"received {len(actionable_rates)}."
        )
    if actionable_rates and actionable_rates[0].start != coverage_start:
        errors.append(
            f"First actionable rate does not begin at {coverage_start.isoformat()}."
        )
    if actionable_rates and actionable_rates[-1].end != coverage_end:
        errors.append(
            f"Last actionable rate does not end at {coverage_end.isoformat()}."
        )
    for previous, current in pairwise(actionable_rates):
        if current.start != previous.end:
            errors.append(f"Rate coverage has a gap or overlap at {current.start.isoformat()}.")
            break
    if any(rate.start.astimezone(local_zone).date() != expected_date for rate in actionable_rates):
        errors.append("The payload contains rates for a different local date.")
    return expected_periods, errors


def build_agile_day_plan(
    raw_rates: Any,
    *,
    timezone: str,
    battery_capacity_kwh: float,
    starting_soc: float,
    reserve_soc: float,
    expected_date: date | None = None,
    now: datetime | None = None,
    demand_profile_kwh: dict[str, float] | None = None,
    demand_profile_revision: str | None = None,
    next_day_rates: Any | None = None,
    target_soc: float = 100.0,
    ready_by: str = "16:00",
    protected_until: str = "22:00",
    max_charge_power_w: int = _SAFE_AGILE_CHARGE_POWER_CEILING_W,
    max_discharge_power_w: int = _SAFE_AGILE_DISCHARGE_POWER_CEILING_W,
    charge_efficiency: float = 0.90,
    discharge_efficiency: float = 0.95,
    minimum_saving_gbp_per_kwh: float = _DEFAULT_MINIMUM_SAVING_GBP_PER_KWH,
) -> dict[str, Any]:
    """Build a feasible read-only daily plan; never control hardware.

    When a complete next-day payload is supplied, its pre-deadline prices are
    used to value energy discharged today.  The returned slots remain limited
    to ``expected_date`` so existing Today and Tomorrow entities stay stable.
    """
    rates, parse_errors = parse_octopus_rates(raw_rates)
    if not rates:
        return _invalid_plan(
            parse_errors[0] if parse_errors else "Waiting for Octopus rate data.",
            parse_errors,
        )
    if parse_errors:
        return _invalid_plan("One or more Octopus rates failed validation.", parse_errors)

    local_zone = ZoneInfo(timezone)
    payload_date = rates[0].start.astimezone(local_zone).date()
    day = expected_date or payload_date
    if payload_date != day:
        return _invalid_plan(
            f"Rate payload is for {payload_date.isoformat()}, expected {day.isoformat()}."
        )
    if now is None:
        planning_time = datetime.combine(day, time.min, tzinfo=local_zone)
    elif now.tzinfo is None:
        return _invalid_plan("Planner time must include a timezone.")
    else:
        planning_time = now.astimezone(local_zone)

    try:
        ready_time = time.fromisoformat(ready_by)
        protected_time = time.fromisoformat(protected_until)
    except ValueError:
        return _invalid_plan("Ready-by and protection-end times must use HH:MM format.")
    if ready_time >= protected_time:
        return _invalid_plan("Protection end must be later than ready-by time.")
    ready_at = datetime.combine(day, ready_time, tzinfo=local_zone)
    protected_at = datetime.combine(day, protected_time, tzinfo=local_zone)

    next_charge_rates: list[AgileRate] = []
    next_rate_errors: list[str] = []
    if next_day_rates is not None:
        parsed_next_rates, next_parse_errors = parse_octopus_rates(next_day_rates)
        next_day = day + timedelta(days=1)
        if next_parse_errors:
            next_rate_errors.extend(next_parse_errors)
        elif not parsed_next_rates:
            next_rate_errors.append("The next-day source entity has no rates list.")
        elif parsed_next_rates[0].start.astimezone(local_zone).date() != next_day:
            next_rate_errors.append(
                "Next-day rate payload is not for the date immediately after this plan."
            )
        elif any(
            rate.start.astimezone(local_zone).date() != next_day
            for rate in parsed_next_rates
        ):
            next_rate_errors.append(
                "Next-day rate payload contains periods outside the immediately following date."
            )
        else:
            next_ready_at = datetime.combine(next_day, ready_time, tzinfo=local_zone)
            _, next_coverage_errors = _validate_actionable_coverage(
                parsed_next_rates,
                expected_date=next_day,
                local_zone=local_zone,
                planning_time=datetime.combine(next_day, time.min, tzinfo=local_zone),
                protected_until=ready_time,
            )
            next_rate_errors.extend(next_coverage_errors)
            if not next_rate_errors:
                next_charge_rates = [
                    rate
                    for rate in parsed_next_rates
                    if rate.start.astimezone(local_zone).date() == next_day
                    and rate.end.astimezone(local_zone) <= next_ready_at
                ]

    expected_periods, coverage_errors = _validate_actionable_coverage(
        rates,
        expected_date=day,
        local_zone=local_zone,
        planning_time=planning_time,
        protected_until=protected_time,
    )
    if coverage_errors:
        return _invalid_plan("Octopus rates do not cover all actionable periods for the expected day.", coverage_errors)
    full_day_expected_periods = int(
        (
            datetime.combine(day + timedelta(days=1), time.min, tzinfo=local_zone).astimezone(UTC)
            - datetime.combine(day, time.min, tzinfo=local_zone).astimezone(UTC)
        ).total_seconds()
        / 1800
    )

    # Expose the same price landmarks used by the dashboard.  These are derived
    # from the already validated GBP/kWh records, rather than from a separate
    # "current price" sensor that could belong to a different agreement.
    current_rate = next(
        (rate for rate in rates if rate.start <= planning_time < rate.end),
        None,
    )
    future_rates = [rate for rate in rates if rate.end > planning_time]
    cheapest_future_rate = min(
        future_rates,
        key=lambda rate: (rate.value_inc_vat, rate.start),
        default=None,
    )

    try:
        capacity = float(battery_capacity_kwh)
        start_soc = float(starting_soc)
        reserve = float(reserve_soc)
        target = float(target_soc)
        charge_efficiency = float(charge_efficiency)
        discharge_efficiency = float(discharge_efficiency)
        minimum_saving = float(minimum_saving_gbp_per_kwh)
        requested_charge_power_w = float(max_charge_power_w)
        requested_discharge_power_w = float(max_discharge_power_w)
    except (TypeError, ValueError, OverflowError):
        return _invalid_plan("One or more battery planning inputs are not numeric.")
    numeric_inputs = {
        "battery_capacity_kwh": capacity,
        "starting_soc": start_soc,
        "reserve_soc": reserve,
        "target_soc": target,
        "charge_efficiency": charge_efficiency,
        "discharge_efficiency": discharge_efficiency,
        "minimum_saving_gbp_per_kwh": minimum_saving,
        "max_charge_power_w": requested_charge_power_w,
        "max_discharge_power_w": requested_discharge_power_w,
    }
    non_finite = [name for name, value in numeric_inputs.items() if not isfinite(value)]
    if non_finite:
        return _invalid_plan(f"Non-finite planning inputs: {', '.join(non_finite)}.")
    if capacity <= 0:
        return _invalid_plan("Battery capacity must be greater than zero.")
    if not 0 <= start_soc <= 100 or not 0 <= reserve <= target <= 100:
        return _invalid_plan(
            "SOC inputs must satisfy 0 <= starting SOC <= 100 and "
            "0 <= reserve <= target <= 100."
        )
    if not 0 < charge_efficiency <= 1 or not 0 < discharge_efficiency <= 1:
        return _invalid_plan("Charge and discharge efficiencies must be greater than 0 and at most 1.")
    if minimum_saving < 0:
        return _invalid_plan("Minimum saving cannot be negative.")
    if requested_charge_power_w <= 0 or requested_discharge_power_w <= 0:
        return _invalid_plan("Charge and discharge power limits must be greater than zero.")

    max_charge_power_w = min(
        _SAFE_AGILE_CHARGE_POWER_CEILING_W,
        int(requested_charge_power_w),
    )
    max_discharge_power_w = min(
        _SAFE_AGILE_DISCHARGE_POWER_CEILING_W,
        int(requested_discharge_power_w),
    )
    charge_candidates = [
        rate
        for rate in rates
        if rate.start >= planning_time
        and rate.end.astimezone(local_zone) <= ready_at
    ]
    discharge_candidates = [
        rate
        for rate in rates
        if rate.start >= planning_time
        and ready_at <= rate.start.astimezone(local_zone) < protected_at
    ]

    charge_grid_limit_kwh = max_charge_power_w / 1000 * 0.5
    discharge_limit_kwh = max_discharge_power_w / 1000 * 0.5
    starting_below_reserve = start_soc < reserve
    reserve_recovery_stored_kwh = capacity * max(0.0, reserve - start_soc) / 100
    stored_energy_needed = capacity * max(0.0, target - start_soc) / 100

    charge_energy_by_start: dict[datetime, float] = {}
    remaining_stored_need = stored_energy_needed
    for rate in sorted(charge_candidates, key=lambda item: (item.value_inc_vat, item.start)):
        if remaining_stored_need <= 1e-9:
            break
        grid_energy = min(charge_grid_limit_kwh, remaining_stored_need / charge_efficiency)
        charge_energy_by_start[rate.start] = grid_energy
        remaining_stored_need -= grid_energy * charge_efficiency

    charge_grid_kwh = sum(charge_energy_by_start.values())
    stored_charge_kwh = charge_grid_kwh * charge_efficiency
    projected_ready_soc = min(
        target,
        start_soc + (stored_charge_kwh / capacity * 100 if capacity else 0.0),
    )
    charge_cost_total = sum(
        rate.value_inc_vat * charge_energy_by_start.get(rate.start, 0.0) for rate in rates
    )
    average_charge_rate = charge_cost_total / charge_grid_kwh if charge_grid_kwh else None
    usable_discharge_kwh = (
        capacity * max(0.0, projected_ready_soc - reserve) / 100 * discharge_efficiency
    )
    replacement_rate_source = "same_day_planned_charge"
    replacement_charge_rate = average_charge_rate
    if next_charge_rates:
        # Value today's maximum feasible discharge against the cheapest actual
        # periods that can refill it tomorrow. This avoids treating a single
        # unusually cheap half-hour as though it could replace the whole battery.
        grid_energy_to_replace = usable_discharge_kwh / (
            charge_efficiency * discharge_efficiency
        )
        remaining_grid_energy = grid_energy_to_replace
        replacement_cost_total = 0.0
        replacement_grid_energy = 0.0
        for rate in sorted(next_charge_rates, key=lambda item: (item.value_inc_vat, item.start)):
            if remaining_grid_energy <= 1e-9:
                break
            grid_energy = min(charge_grid_limit_kwh, remaining_grid_energy)
            replacement_cost_total += grid_energy * rate.value_inc_vat
            replacement_grid_energy += grid_energy
            remaining_grid_energy -= grid_energy
        if replacement_grid_energy > 0 and remaining_grid_energy <= 1e-6:
            replacement_charge_rate = replacement_cost_total / replacement_grid_energy
            replacement_rate_source = "next_day_published_rates"
    if replacement_charge_rate is None:
        replacement_charge_rate = min(
            (rate.value_inc_vat for rate in future_rates),
            default=None,
        )
        replacement_rate_source = "same_day_future_rate_fallback"
    delivered_replacement_cost = (
        replacement_charge_rate / (charge_efficiency * discharge_efficiency)
        if replacement_charge_rate is not None
        else None
    )
    profile_provided = demand_profile_kwh is not None
    if demand_profile_kwh is not None and not isinstance(demand_profile_kwh, dict):
        return _invalid_plan("Demand profile must be a mapping of local HH:MM to kWh.")
    demand_profile = demand_profile_kwh or {}
    for key, value in demand_profile.items():
        try:
            time.fromisoformat(str(key))
            numeric_value = float(value)
        except (TypeError, ValueError, OverflowError):
            return _invalid_plan(f"Demand profile entry {key!r} is invalid.")
        if not isfinite(numeric_value) or numeric_value < 0:
            return _invalid_plan(f"Demand profile entry {key!r} must be finite and non-negative.")

    def expected_load(rate: AgileRate) -> float:
        local_key = rate.start.astimezone(local_zone).strftime("%H:%M")
        raw_load = demand_profile.get(
            local_key,
            0.0 if profile_provided else discharge_limit_kwh,
        )
        try:
            return min(discharge_limit_kwh, max(0.0, float(raw_load)))
        except (TypeError, ValueError):
            return 0.0

    profitable_candidates: list[AgileRate] = []
    for rate in discharge_candidates:
        if delivered_replacement_cost is None:
            continue
        if rate.value_inc_vat - delivered_replacement_cost >= minimum_saving:
            profitable_candidates.append(rate)

    discharge_energy_by_start: dict[datetime, float] = {}
    remaining_discharge_kwh = usable_discharge_kwh
    for rate in sorted(
        profitable_candidates,
        key=lambda item: (item.value_inc_vat, expected_load(item), item.start),
        reverse=True,
    ):
        if remaining_discharge_kwh <= 1e-9:
            break
        energy = min(expected_load(rate), remaining_discharge_kwh)
        if energy <= 0:
            continue
        discharge_energy_by_start[rate.start] = energy
        remaining_discharge_kwh -= energy

    planned_discharge_kwh = sum(discharge_energy_by_start.values())
    projected_protection_end_soc = max(
        reserve,
        projected_ready_soc
        - (
            planned_discharge_kwh / discharge_efficiency / capacity * 100
            if capacity
            else 0.0
        ),
    )
    avoided_import_cost = sum(
        rate.value_inc_vat * discharge_energy_by_start.get(rate.start, 0.0) for rate in rates
    )
    replacement_cost = (
        planned_discharge_kwh * delivered_replacement_cost
        if delivered_replacement_cost is not None
        else 0.0
    )
    estimated_net_saving = max(0.0, avoided_import_cost - replacement_cost)

    slots: list[dict[str, Any]] = []
    for rate in rates:
        local_start = rate.start.astimezone(local_zone)
        action = "hold"
        planned_energy_kwh = 0.0
        command_power_limit_w = 0
        duration_minutes = 0.0
        if rate.start in charge_energy_by_start:
            action = "charge"
            planned_energy_kwh = charge_energy_by_start[rate.start]
            command_power_limit_w = max_charge_power_w
            duration_minutes = planned_energy_kwh / (max_charge_power_w / 1000) * 60
        elif rate.start in discharge_energy_by_start:
            action = "discharge"
            planned_energy_kwh = discharge_energy_by_start[rate.start]
            command_power_limit_w = max_discharge_power_w
            duration_minutes = rate.duration_hours * 60
        average_power_w = (
            round(planned_energy_kwh / rate.duration_hours * 1000)
            if planned_energy_kwh > 0
            else 0
        )
        charge_cost = (
            rate.value_inc_vat * planned_energy_kwh if action == "charge" else 0.0
        )
        avoided_cost = (
            rate.value_inc_vat * planned_energy_kwh if action == "discharge" else 0.0
        )
        slot_replacement_cost = (
            delivered_replacement_cost * planned_energy_kwh
            if action == "discharge" and delivered_replacement_cost is not None
            else 0.0
        )
        slots.append(
            {
                "start": rate.start.isoformat(),
                "end": rate.end.isoformat(),
                "local_start": local_start.strftime("%H:%M"),
                "rate_gbp_per_kwh": round(rate.value_inc_vat, 5),
                "action": action,
                "power_w": average_power_w,
                "command_power_limit_w": command_power_limit_w,
                "duration_minutes": round(duration_minutes, 1),
                "energy_kwh": round(planned_energy_kwh, 3),
                "expected_house_load_kwh": round(expected_load(rate), 3),
                "charge_cost_gbp": round(charge_cost, 4),
                "avoided_import_cost_gbp": round(avoided_cost, 4),
                "replacement_cost_gbp": round(slot_replacement_cost, 4),
                "net_saving_gbp": round(
                    max(0.0, avoided_cost - slot_replacement_cost),
                    4,
                ),
            }
        )

    status = "proposed"
    reason = "Shadow plan only; no battery commands will be sent."
    if remaining_stored_need > 1e-6:
        status = "limited"
        reason = f"Available future periods cannot reach the target SOC by {ready_by}."

    return {
        "status": status,
        "reason": reason,
        "planner_revision": _PLANNER_REVISION,
        "date": day.isoformat(),
        "timezone": timezone,
        "rate_unit": "GBP/kWh",
        "rate_period_count": len(rates),
        "expected_rate_period_count": full_day_expected_periods,
        "expected_actionable_rate_period_count": expected_periods,
        "planning_time": planning_time.isoformat(),
        "current_rate_gbp_per_kwh": (
            round(current_rate.value_inc_vat, 5) if current_rate is not None else None
        ),
        "current_rate_start": current_rate.start.isoformat() if current_rate is not None else None,
        "current_rate_end": current_rate.end.isoformat() if current_rate is not None else None,
        "lowest_future_rate_gbp_per_kwh": (
            round(cheapest_future_rate.value_inc_vat, 5)
            if cheapest_future_rate is not None
            else None
        ),
        "lowest_future_rate_start": (
            cheapest_future_rate.start.isoformat() if cheapest_future_rate is not None else None
        ),
        "ready_by": ready_by,
        "protected_until": protected_until,
        "starting_soc": round(start_soc, 1),
        "target_soc": round(target, 1),
        "projected_soc_at_ready_by": round(projected_ready_soc, 1),
        "projected_soc_at_protection_end": round(projected_protection_end_soc, 1),
        "reserve_soc": round(reserve, 1),
        "starting_below_reserve": starting_below_reserve,
        "reserve_recovery_stored_kwh": round(reserve_recovery_stored_kwh, 3),
        "battery_capacity_kwh": round(capacity, 3),
        "max_system_charge_power_w": max_charge_power_w,
        "max_system_discharge_power_w": max_discharge_power_w,
        "max_discharge_per_half_hour_kwh": round(discharge_limit_kwh, 3),
        "power_constraint_note": (
            "Agile allows up to 1200 W AC grid charging. Peak supply uses Self-Gen/Zero "
            "Export with a 1000 W household-output planning ceiling; no fixed discharge "
            "command is sent."
        ),
        "demand_profile_source": (
            "configured_historical_half_hour_profile"
            if profile_provided
            else "no_profile_max_load_assumption"
        ),
        "demand_profile_revision": (
            demand_profile_revision
            if profile_provided and demand_profile_revision
            else "caller_supplied" if profile_provided else None
        ),
        "demand_profile_total_kwh": round(sum(float(value) for value in demand_profile.values()), 3),
        "demand_profile_safety_note": (
            "Historical demand estimates advisory energy and value. Self-Gen/Zero Export "
            "can use its CT feedback to match actual household demand; any future executor "
            "must preserve that live zero-export constraint."
        ),
        "charge_periods": len(charge_energy_by_start),
        "discharge_periods": len(discharge_energy_by_start),
        "planned_grid_charge_kwh": round(charge_grid_kwh, 3),
        "planned_stored_charge_kwh": round(stored_charge_kwh, 3),
        "planned_discharge_kwh": round(planned_discharge_kwh, 3),
        "average_planned_charge_rate_gbp_per_kwh": (
            round(average_charge_rate, 5) if average_charge_rate is not None else None
        ),
        "delivered_replacement_cost_gbp_per_kwh": (
            round(delivered_replacement_cost, 5)
            if delivered_replacement_cost is not None
            else None
        ),
        "replacement_rate_source": replacement_rate_source,
        "next_day_rates_used": replacement_rate_source == "next_day_published_rates",
        "next_day_rate_validation_errors": next_rate_errors,
        "minimum_saving_gbp_per_kwh": round(minimum_saving, 5),
        "estimated_grid_charge_cost_gbp": round(charge_cost_total, 2),
        "estimated_avoided_import_cost_gbp": round(avoided_import_cost, 2),
        "estimated_discharge_replacement_cost_gbp": round(replacement_cost, 2),
        "estimated_net_saving_gbp": round(estimated_net_saving, 2),
        "cost_estimate_note": (
            "Estimates cover planned grid charging and planned protected-window discharge, "
            "not the household's complete daily electricity bill."
        ),
        "validation_errors": [],
        "control_enabled": False,
        "slots": slots,
    }


def build_agile_shadow_decision(
    plan: Mapping[str, Any] | None,
    *,
    now: datetime,
    connection_fresh: bool,
    soc_percent: float | None,
    reserve_soc: float,
    pv_power_w: float,
    total_charge_power_w: float,
    ac_charge_power_w: float,
    pv_quiet_minutes: float,
    locked_action: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recommend a view-only operating state without sending device commands."""
    base = {
        "decision_revision": _SHADOW_DECISION_REVISION,
        "control_enabled": False,
        "decision_time": now.isoformat(),
        "soc_percent": round(soc_percent, 1) if soc_percent is not None else None,
        "reserve_soc": round(reserve_soc, 1),
        "pv_power_w": round(max(0.0, pv_power_w), 1),
        "total_charge_power_w": round(max(0.0, total_charge_power_w), 1),
        "ac_charge_power_w": round(max(0.0, ac_charge_power_w), 1),
        "pv_quiet_minutes": round(max(0.0, pv_quiet_minutes), 1),
        "failsafe_mode": "Self-Gen/Zero Export",
    }

    def result(state: str, mode: str, reason: str, **extra: Any) -> dict[str, Any]:
        return {
            **base,
            "state": state,
            "recommended_operating_mode": mode,
            "reason": reason,
            **extra,
        }

    if not connection_fresh:
        return result(
            "Connection Fail-safe",
            "Self-Gen/Zero Export",
            "Telemetry is unavailable or stale; do not start a timed command.",
        )
    if soc_percent is None or not isfinite(soc_percent):
        return result(
            "Connection Fail-safe",
            "Self-Gen/Zero Export",
            "A trustworthy battery SOC is unavailable.",
        )
    if not plan or plan.get("status") not in ("proposed", "limited"):
        return result(
            "Rate Fail-safe",
            "Self-Gen/Zero Export",
            "A validated current-day Agile plan is unavailable.",
        )

    action = dict(locked_action or {})
    action_name = str(action.get("action") or "hold")
    action_source = str(
        action.pop("decision_source", None)
        or ("pre_boundary_lock" if locked_action else "current_plan")
    )
    action_attrs = {
        "planned_action": action_name,
        "planned_action_source": action_source,
        "planned_slot_start": action.get("start"),
        "planned_slot_end": action.get("end"),
        "planned_slot_energy_kwh": action.get("energy_kwh"),
        "planned_slot_power_limit_w": action.get("command_power_limit_w"),
        "planned_slot_duration_minutes": action.get("duration_minutes"),
        "target_soc": plan.get("target_soc"),
    }

    inferred_pv_charge_w = max(0.0, total_charge_power_w - ac_charge_power_w)
    solar_active = max(0.0, pv_power_w) >= 50 or inferred_pv_charge_w >= 50
    target_soc = plan.get("target_soc")
    target_reached = bool(
        isinstance(target_soc, int | float)
        and isfinite(float(target_soc))
        and soc_percent >= float(target_soc) - 0.5
    )

    if action_name == "charge" and target_reached:
        return result(
            "Charge Target Reached",
            "Self-Gen/Zero Export",
            "Battery SOC has reached the plan target; grid charging is inhibited.",
            charge_inhibited_reason="target_reached",
            **action_attrs,
        )
    if action_name == "charge" and solar_active:
        return result(
            "Solar Charge Deferred",
            "Self-Gen/Zero Export",
            "Useful PV is already charging the site; preserve solar headroom instead of starting grid charge.",
            charge_inhibited_reason="useful_pv_present",
            inferred_pv_charge_w=round(inferred_pv_charge_w, 1),
            **action_attrs,
        )
    if action_name == "charge":
        return result(
            "Planned Charge",
            "Charge",
            "The action was selected before the half-hour boundary as a cheap charge slot.",
            **action_attrs,
        )
    if soc_percent <= reserve_soc + 0.5:
        return result(
            "Reserve Protection",
            "Self-Gen/Zero Export",
            "Battery SOC is at the configured reserve; fixed discharge is prohibited.",
            **action_attrs,
        )
    if action_name == "discharge":
        return result(
            "Peak Self-Gen",
            "Self-Gen/Zero Export",
            "Use CT-controlled Self-Gen during this selected profitable period.",
            **action_attrs,
        )

    if solar_active:
        return result(
            "Solar Self-Gen",
            "Self-Gen/Zero Export",
            "Useful PV is present; preserve normal solar capture and CT-controlled flows.",
            **action_attrs,
        )

    future_discharges = []
    for slot in plan.get("slots", []):
        if not isinstance(slot, Mapping) or slot.get("action") != "discharge":
            continue
        try:
            start = datetime.fromisoformat(str(slot.get("start")))
        except ValueError:
            continue
        if start.tzinfo is not None and start > now:
            future_discharges.append(start)
    if future_discharges and pv_quiet_minutes >= 15:
        return result(
            "Post-solar Hold",
            "Idle",
            "PV has remained negligible and a later selected discharge period remains.",
            next_discharge_at=min(future_discharges).isoformat(),
            **action_attrs,
        )

    return result(
        "Solar Self-Gen",
        "Self-Gen/Zero Export",
        "No locked Agile action requires a mode change; Self-Gen remains the safe default.",
        **action_attrs,
    )


def agile_control_mode_for_state(
    state: str | None,
    recommended_mode: str | None,
) -> str | None:
    """Return the only automated mode permitted for a validated decision state."""
    if state == "Planned Charge" and recommended_mode == "Charge":
        return "Charge"
    if state == "Post-solar Hold" and recommended_mode == "Idle":
        return "Idle"
    if state in {
        "Solar Self-Gen",
        "Solar Charge Deferred",
        "Charge Target Reached",
        "Peak Self-Gen",
        "Reserve Protection",
        "Connection Fail-safe",
        "Rate Fail-safe",
    } and recommended_mode == "Self-Gen/Zero Export":
        return "Self-Gen/Zero Export"
    return None


def bounded_agile_command_window(
    mode: str,
    attributes: Mapping[str, Any],
    now: datetime,
) -> tuple[datetime, datetime] | None:
    """Return a safe current-slot window for an automated custom command."""
    if now.tzinfo is None or mode not in ("Charge", "Idle"):
        return None
    if mode == "Charge":
        try:
            start = datetime.fromisoformat(str(attributes.get("planned_slot_start")))
            end = datetime.fromisoformat(str(attributes.get("planned_slot_end")))
        except (TypeError, ValueError):
            return None
        if start.tzinfo is None or end.tzinfo is None:
            return None
        try:
            planned_minutes = float(attributes.get("planned_slot_duration_minutes"))
        except (TypeError, ValueError):
            try:
                energy_kwh = float(attributes.get("planned_slot_energy_kwh"))
                power_w = float(attributes.get("planned_slot_power_limit_w"))
                planned_minutes = energy_kwh / (power_w / 1000) * 60
            except (TypeError, ValueError, ZeroDivisionError):
                return None
        if not isfinite(planned_minutes) or not 0 < planned_minutes <= 30:
            return None
        end = min(end, start + timedelta(minutes=max(1.0, planned_minutes)))
    else:
        start = now.replace(
            minute=(now.minute // 30) * 30,
            second=0,
            microsecond=0,
        )
        end = start + timedelta(minutes=30)
    if end <= now + timedelta(seconds=45):
        return None
    if start > now + timedelta(minutes=1):
        return None
    if end <= start or end - start > timedelta(minutes=31):
        return None
    return start, end


def agile_control_command_errors(
    direction: str,
    power_w: int,
    slot_start: str | None,
    slot_end: str | None,
) -> list[str]:
    """Validate the final bounded Agile command immediately before a write."""
    errors: list[str] = []
    if direction not in ("Charge", "Idle"):
        errors.append("Agile control never permits fixed Discharge or Feed")
    if direction == "Charge" and not 0 < power_w <= _SAFE_AGILE_CHARGE_POWER_CEILING_W:
        errors.append("Agile charge power exceeds its 1200 W limit")
    if direction == "Idle" and power_w != 0:
        errors.append("Agile Idle must use a zero-power command")
    if not slot_start or not slot_end:
        errors.append("Agile control commands must have a bounded slot")
        return errors

    parsed_minutes: list[int] = []
    for value in (slot_start, slot_end):
        parts = value.split(":")
        if (
            len(parts) != 2
            or len(parts[0]) != 2
            or len(parts[1]) != 2
            or not all(part.isdigit() for part in parts)
            or not 0 <= int(parts[0]) <= 23
            or not 0 <= int(parts[1]) <= 59
        ):
            errors.append("Agile control slot times must use HH:MM")
            return errors
        parsed_minutes.append(int(parts[0]) * 60 + int(parts[1]))
    duration_minutes = (parsed_minutes[1] - parsed_minutes[0]) % (24 * 60)
    if not 0 < duration_minutes <= 30:
        errors.append("Agile control windows must be 1 to 30 minutes")
    return errors
