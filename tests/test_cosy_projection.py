"""Fixed schedule accounting must describe the actions that Cosy displays."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from test_agile_planner import AGILE, _rates


def plan_at(day="2026-09-17", clock="14:10", **options):
    params = {
        "timezone": "Europe/London",
        "battery_capacity_kwh": 5.874,
        "starting_soc": 50,
        "reserve_soc": 20,
        "target_soc": 90,
        "expected_date": date.fromisoformat(day),
        "now": datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=ZoneInfo("Europe/London")),
    }
    params.update(options)
    return AGILE.build_agile_day_plan(_rates(day), **params)


@pytest.mark.parametrize("day", ["2026-09-17", "2026-03-29", "2026-10-25"])
@pytest.mark.parametrize("clock", ["00:00", "14:10", "23:50"])
def test_schedule_totals_conserve_energy_and_reconcile_with_slots(day, clock):
    economic = plan_at(day, clock)
    plan = AGILE.apply_cosy_rate_schedule(economic)
    slots = plan["slots"]
    charging = [s for s in slots if s["action"] == "charge"]
    supplying = [s for s in slots if s["action"] == "self_gen"]
    grid = sum(s["energy_kwh"] for s in charging)
    output = sum(s["energy_kwh"] for s in supplying)
    assert plan["planned_grid_charge_kwh"] == pytest.approx(grid, abs=0.00051)
    assert plan["planned_discharge_kwh"] == pytest.approx(output, abs=0.00051)
    for total, field in [
        ("estimated_grid_charge_cost_gbp", "charge_cost_gbp"),
        ("estimated_avoided_import_cost_gbp", "avoided_import_cost_gbp"),
        ("estimated_discharge_replacement_cost_gbp", "replacement_cost_gbp"),
        ("estimated_net_saving_gbp", "net_saving_gbp"),
    ]:
        assert plan[total] == pytest.approx(sum(s[field] for s in slots), abs=0.0051)
    capacity = plan["battery_capacity_kwh"]
    expected_end = plan["starting_soc"] + (grid * 0.9 - output / 0.95) / capacity * 100
    assert plan["projected_soc_at_day_end"] == pytest.approx(expected_end, abs=0.051)
    assert plan["charge_periods"] == sum(s["energy_kwh"] > 0 for s in charging)
    assert plan["discharge_periods"] == sum(s["energy_kwh"] > 0 for s in supplying)
    assert plan["next_day_rates_used"] is False
    assert plan["estimate_scope"] == ("full_day" if clock == "00:00" else "remaining_day")
    now = datetime.fromisoformat(plan["planning_time"])
    for slot in slots:
        if datetime.fromisoformat(slot["end"]) <= now:
            assert slot["energy_kwh"] == 0
            assert slot["projected_end_soc"] is None
    assert sum(p["planned_energy_kwh"] for p in plan["cosy_periods"]) == pytest.approx(grid + output, abs=0.004)
    # Applying the schedule does not mutate the economic plan supplied by the caller.
    assert all("projected_end_soc" not in s for s in economic["slots"])


def test_partial_charge_slot_and_target_reached_before_ready_time():
    plan = AGILE.apply_cosy_rate_schedule(plan_at(clock="15:10", starting_soc=89, ready_by="15:15"))
    slot = next(s for s in plan["slots"] if s["local_start"] == "15:00")
    assert slot["actionable_minutes"] == 20
    assert slot["energy_kwh"] == pytest.approx(5.874 * 0.01 / 0.9, abs=1e-6)
    assert plan["projected_soc_at_ready_by"] == 90
    assert slot["projected_end_soc"] == 90


def test_reserve_reached_before_protection_time():
    plan = AGILE.apply_cosy_rate_schedule(plan_at(clock="16:00", starting_soc=21, protected_until="16:30"))
    assert plan["projected_soc_at_protection_end"] == 20


def test_elapsed_milestones_are_unavailable():
    plan = AGILE.apply_cosy_rate_schedule(plan_at(clock="23:50"))
    assert plan["projected_soc_at_ready_by"] is None
    assert plan["projected_soc_at_protection_end"] is None
    assert plan["projected_soc_at_day_end"] >= 50


def test_happy_hour_credit_is_separate_from_net_value():
    economic = plan_at(clock="10:00")
    windows = [{"start": "2026-09-17T11:00:00+01:00", "end": "2026-09-17T12:00:00+01:00"}]
    plan = AGILE.apply_cosy_rate_schedule(economic, happy_hour_windows=windows)
    assert plan["happy_hour_grid_charge_kwh"] > 0
    assert plan["estimated_happy_hour_credit_gbp"] == pytest.approx(
        sum(s["credited_back_gbp"] for s in plan["slots"]), abs=0.0051
    )
    assert plan["estimated_net_saving_gbp"] == pytest.approx(
        sum(s["net_saving_gbp"] for s in plan["slots"]), abs=0.0051
    )


def test_economic_totals_cannot_leak_into_fixed_schedule():
    economic = plan_at()
    for key in (
        "planned_grid_charge_kwh",
        "planned_stored_charge_kwh",
        "planned_discharge_kwh",
        "estimated_grid_charge_cost_gbp",
        "estimated_avoided_import_cost_gbp",
        "estimated_discharge_replacement_cost_gbp",
        "estimated_net_saving_gbp",
        "projected_soc_at_ready_by",
        "projected_soc_at_protection_end",
        "charge_periods",
        "discharge_periods",
    ):
        economic[key] = 999
    economic["next_day_rates_used"] = True
    actual = AGILE.apply_cosy_rate_schedule(economic)
    expected = AGILE.apply_cosy_rate_schedule(plan_at())
    assert actual == expected


def test_projection_respects_lower_system_output_limit():
    plan = AGILE.apply_cosy_rate_schedule(plan_at(clock="16:00", starting_soc=90, max_discharge_power_w=400))
    slot = next(s for s in plan["slots"] if s["local_start"] == "16:00")
    assert slot["energy_kwh"] == pytest.approx(0.2)
    assert slot["power_w"] == 400
