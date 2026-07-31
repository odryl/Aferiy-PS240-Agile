"""Tests for the read-only Octopus Agile planner."""

from __future__ import annotations

import importlib.util
import math
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components" / "aecc_battery" / "agile.py"
SPEC = importlib.util.spec_from_file_location("aecc_agile_test_module", MODULE_PATH)
assert SPEC and SPEC.loader
AGILE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AGILE
SPEC.loader.exec_module(AGILE)


def _rates(day: str, *, protected_rate: float = 0.45) -> list[dict[str, object]]:
    local = ZoneInfo("Europe/London")
    local_day = date.fromisoformat(day)
    local_start = datetime.combine(local_day, time.min, tzinfo=local)
    local_end = datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=local)
    cursor = local_start.astimezone(UTC)
    end = local_end.astimezone(UTC)
    rates = []
    index = 0
    while cursor < end:
        local_period = cursor.astimezone(local)
        value = 0.05 + index / 10000
        if 16 <= local_period.hour < 22:
            value = protected_rate + index / 10000
        rates.append(
            {
                "start": cursor.isoformat(),
                "end": (cursor + timedelta(minutes=30)).isoformat(),
                "value_inc_vat": value,
            }
        )
        cursor += timedelta(minutes=30)
        index += 1
    return rates


def _plan(day: str = "2026-07-27", **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "timezone": "Europe/London",
        "battery_capacity_kwh": 5.874,
        "starting_soc": 10,
        "reserve_soc": 10,
        "expected_date": date.fromisoformat(day),
    }
    values.update(overrides)
    return AGILE.build_agile_day_plan(_rates(day), **values)


def test_discharge_is_capped_at_800w_system_wide() -> None:
    plan = _plan(max_discharge_power_w=1200)

    discharge_slots = [slot for slot in plan["slots"] if slot["action"] == "discharge"]
    assert plan["max_system_discharge_power_w"] == 800
    assert plan["max_discharge_per_half_hour_kwh"] == 0.4
    assert discharge_slots
    assert all(slot["power_w"] == 800 for slot in discharge_slots)
    assert all(slot["energy_kwh"] <= 0.4 for slot in discharge_slots)
    assert plan["planned_discharge_kwh"] <= 5.874 * 0.9 * 0.95


def test_plan_charges_before_1600_and_uses_household_profile() -> None:
    profile = {f"{hour:02d}:{minute:02d}": 0.0 for hour in range(16, 22) for minute in (0, 30)}
    profile["19:00"] = 0.1
    plan = _plan(demand_profile_kwh=profile)

    charge_slots = [slot for slot in plan["slots"] if slot["action"] == "charge"]
    discharge_slots = [slot for slot in plan["slots"] if slot["action"] == "discharge"]
    assert plan["status"] == "proposed"
    assert charge_slots
    assert all(slot["local_start"] < "16:00" for slot in charge_slots)
    assert [slot["local_start"] for slot in discharge_slots] == ["19:00"]
    assert plan["planned_discharge_kwh"] == 0.1
    assert plan["control_enabled"] is False


def test_today_never_selects_elapsed_periods() -> None:
    now = datetime(2026, 7, 27, 15, 0, tzinfo=ZoneInfo("Europe/London"))
    plan = _plan(now=now, battery_capacity_kwh=1.0, starting_soc=10)
    active = [slot for slot in plan["slots"] if slot["action"] != "hold"]

    assert active
    assert all(datetime.fromisoformat(slot["start"]) >= now for slot in active)


def test_midnight_ending_slot_is_not_mistaken_for_pre_deadline_charge() -> None:
    raw_rates = _rates("2026-07-27")
    raw_rates[-1]["value_inc_vat"] = -1.0
    now = datetime(2026, 7, 27, 18, 0, tzinfo=ZoneInfo("Europe/London"))

    plan = AGILE.build_agile_day_plan(
        raw_rates,
        timezone="Europe/London",
        battery_capacity_kwh=1.958,
        starting_soc=66,
        reserve_soc=15,
        expected_date=date(2026, 7, 27),
        now=now,
    )

    assert plan["planned_grid_charge_kwh"] == 0
    assert not any(
        slot["local_start"] == "23:30" and slot["action"] == "charge"
        for slot in plan["slots"]
    )


def test_current_day_can_omit_elapsed_periods_when_all_actionable_periods_exist() -> None:
    raw_rates = _rates("2026-07-27")[2:]
    now = datetime(2026, 7, 27, 1, 15, tzinfo=ZoneInfo("Europe/London"))
    plan = AGILE.build_agile_day_plan(
        raw_rates,
        timezone="Europe/London",
        battery_capacity_kwh=5.874,
        starting_soc=10,
        reserve_soc=10,
        expected_date=date(2026, 7, 27),
        now=now,
    )

    assert plan["status"] == "proposed"
    assert plan["rate_period_count"] == 46
    assert plan["expected_rate_period_count"] == 48
    assert plan["expected_actionable_rate_period_count"] == 41


def test_current_day_can_omit_periods_after_the_protection_window() -> None:
    raw_rates = _rates("2026-07-27")[:-2]
    now = datetime(2026, 7, 27, 15, 15, tzinfo=ZoneInfo("Europe/London"))
    plan = AGILE.build_agile_day_plan(
        raw_rates,
        timezone="Europe/London",
        battery_capacity_kwh=5.874,
        starting_soc=100,
        reserve_soc=10,
        expected_date=date(2026, 7, 27),
        now=now,
    )

    assert plan["status"] == "proposed"
    assert plan["rate_period_count"] == 46
    assert plan["expected_actionable_rate_period_count"] == 13


def test_limited_charge_cannot_create_impossible_discharge_energy() -> None:
    now = datetime(2026, 7, 27, 15, 0, tzinfo=ZoneInfo("Europe/London"))
    plan = _plan(
        now=now,
        battery_capacity_kwh=20.0,
        starting_soc=0,
        reserve_soc=0,
    )

    achievable_delivered_kwh = plan["planned_stored_charge_kwh"] * 0.95
    assert plan["status"] == "limited"
    assert plan["projected_soc_at_ready_by"] < 100
    assert plan["planned_discharge_kwh"] <= achievable_delivered_kwh + 1e-9


def test_rates_are_gbp_and_savings_are_not_divided_by_100() -> None:
    plan = _plan()

    assert plan["rate_unit"] == "GBP/kWh"
    assert plan["average_planned_charge_rate_gbp_per_kwh"] < 0.10
    assert plan["estimated_net_saving_gbp"] > 1.0
    assert plan["estimated_grid_charge_cost_gbp"] > 0
    assert plan["estimated_avoided_import_cost_gbp"] > plan["estimated_discharge_replacement_cost_gbp"]
    assert all("rate_gbp_per_kwh" in slot for slot in plan["slots"])

    charge_slots = [slot for slot in plan["slots"] if slot["action"] == "charge"]
    discharge_slots = [slot for slot in plan["slots"] if slot["action"] == "discharge"]
    assert all(slot["charge_cost_gbp"] > 0 for slot in charge_slots)
    assert all(slot["avoided_import_cost_gbp"] > 0 for slot in discharge_slots)
    assert all(slot["net_saving_gbp"] > 0 for slot in discharge_slots)


def test_current_and_cheapest_prices_are_derived_from_validated_rate_data() -> None:
    now = datetime(2026, 7, 27, 12, 15, tzinfo=ZoneInfo("Europe/London"))
    plan = _plan(now=now)

    assert plan["current_rate_gbp_per_kwh"] == 0.0524
    assert plan["current_rate_start"] == "2026-07-27T11:00:00+00:00"
    assert plan["current_rate_end"] == "2026-07-27T11:30:00+00:00"
    assert plan["lowest_future_rate_gbp_per_kwh"] == 0.0524
    assert plan["lowest_future_rate_start"] == "2026-07-27T11:00:00+00:00"


def test_unprofitable_periods_are_not_discharged() -> None:
    raw_rates = _rates("2026-07-27", protected_rate=0.01)
    plan = AGILE.build_agile_day_plan(
        raw_rates,
        timezone="Europe/London",
        battery_capacity_kwh=5.874,
        starting_soc=10,
        reserve_soc=10,
        expected_date=date(2026, 7, 27),
    )

    assert plan["discharge_periods"] == 0
    assert plan["planned_discharge_kwh"] == 0


def test_published_tomorrow_rates_value_tonights_discharge() -> None:
    today_rates = _rates("2026-07-27", protected_rate=0.25)
    for rate in today_rates:
        if datetime.fromisoformat(str(rate["start"])).astimezone(
            ZoneInfo("Europe/London")
        ).hour >= 16:
            rate["value_inc_vat"] = 0.25
    tomorrow_rates = _rates("2026-07-28")
    now = datetime(2026, 7, 27, 16, 0, tzinfo=ZoneInfo("Europe/London"))

    same_day_only = AGILE.build_agile_day_plan(
        today_rates,
        timezone="Europe/London",
        battery_capacity_kwh=5.874,
        starting_soc=100,
        reserve_soc=10,
        expected_date=date(2026, 7, 27),
        now=now,
    )
    rolling = AGILE.build_agile_day_plan(
        today_rates,
        timezone="Europe/London",
        battery_capacity_kwh=5.874,
        starting_soc=100,
        reserve_soc=10,
        expected_date=date(2026, 7, 27),
        now=now,
        next_day_rates=tomorrow_rates,
    )

    assert same_day_only["planned_discharge_kwh"] == 0
    assert rolling["planned_discharge_kwh"] > 0
    assert rolling["next_day_rates_used"] is True
    assert rolling["replacement_rate_source"] == "next_day_published_rates"
    assert rolling["projected_soc_at_protection_end"] < rolling["starting_soc"]


def test_invalid_or_non_contiguous_tomorrow_rates_are_ignored_safely() -> None:
    plan = _plan(next_day_rates=_rates("2026-07-30"))

    assert plan["status"] == "proposed"
    assert plan["next_day_rates_used"] is False
    assert plan["next_day_rate_validation_errors"]


def test_tomorrow_payload_with_appended_later_day_is_rejected() -> None:
    tomorrow_rates = _rates("2026-07-28")
    later_rates = _rates("2026-07-29")
    for rate in later_rates:
        rate["value_inc_vat"] = 0.001

    plan = _plan(next_day_rates=tomorrow_rates + later_rates)

    assert plan["next_day_rates_used"] is False
    assert any(
        "outside the immediately following date" in error
        for error in plan["next_day_rate_validation_errors"]
    )


def test_tomorrow_midnight_ending_slot_is_not_used_as_refill_price() -> None:
    today_rates = _rates("2026-07-27", protected_rate=0.25)
    tomorrow_rates = _rates("2026-07-28")
    for rate in tomorrow_rates:
        rate["value_inc_vat"] = 0.20
    tomorrow_rates[-1]["value_inc_vat"] = -1.0
    now = datetime(2026, 7, 27, 16, 0, tzinfo=ZoneInfo("Europe/London"))

    plan = AGILE.build_agile_day_plan(
        today_rates,
        timezone="Europe/London",
        battery_capacity_kwh=1.958,
        starting_soc=100,
        reserve_soc=15,
        expected_date=date(2026, 7, 27),
        now=now,
        next_day_rates=tomorrow_rates,
    )

    assert plan["next_day_rates_used"] is True
    assert plan["delivered_replacement_cost_gbp_per_kwh"] > 0.20


def test_incomplete_tomorrow_payload_is_not_used_for_replacement_prices() -> None:
    tomorrow_rates = _rates("2026-07-28")
    del tomorrow_rates[10]

    plan = _plan(next_day_rates=tomorrow_rates)

    assert plan["next_day_rates_used"] is False
    assert plan["next_day_rate_validation_errors"]


def test_rolling_horizon_accepts_dst_transition_days() -> None:
    spring = _plan("2026-03-28", next_day_rates=_rates("2026-03-29"))
    autumn = _plan("2026-10-24", next_day_rates=_rates("2026-10-25"))

    assert spring["next_day_rates_used"] is True
    assert spring["next_day_rate_validation_errors"] == []
    assert autumn["next_day_rates_used"] is True
    assert autumn["next_day_rate_validation_errors"] == []


def test_octopus_source_metadata_is_validated_behaviorally() -> None:
    valid = {
        "mpan": "1234567890123",
        "serial_number": "meter-1",
        "tariff_code": "E-1R-AGILE-24-10-01-A",
    }
    assert AGILE.validate_octopus_rate_source(
        "event.renamed_current_rates",
        "octopus_energy",
        valid,
        dict(valid),
    ) == []

    assert AGILE.validate_octopus_rate_source(
        "event.fake_current_day_rates",
        "template",
        valid,
    )
    assert AGILE.validate_octopus_rate_source(
        "event.octopus_energy_current_day_rates",
        "octopus_energy",
        {**valid, "tariff_code": "E-1R-FIXED-24-01-01-A"},
    )
    assert AGILE.validate_octopus_rate_source(
        "event.octopus_energy_current_day_rates",
        "octopus_energy",
        {key: value for key, value in valid.items() if key != "mpan"},
    )
    assert AGILE.validate_octopus_rate_source(
        "event.octopus_energy_current_day_rates",
        "octopus_energy",
        valid,
        {**valid, "serial_number": "meter-2"},
    )


def test_non_finite_battery_inputs_fail_safe() -> None:
    fields = {
        "battery_capacity_kwh": 5.874,
        "starting_soc": 50,
        "reserve_soc": 10,
        "target_soc": 100,
        "charge_efficiency": 0.9,
        "discharge_efficiency": 0.95,
        "minimum_saving_gbp_per_kwh": 0.03,
        "max_charge_power_w": 800,
        "max_discharge_power_w": 800,
    }
    for field in fields:
        values = dict(fields)
        values[field] = math.nan
        plan = AGILE.build_agile_day_plan(
            _rates("2026-07-27"),
            timezone="Europe/London",
            expected_date=date(2026, 7, 27),
            **values,
        )
        assert plan["status"] == "invalid", field
        assert plan["slots"] == [], field


def test_partial_slots_report_energy_average_power_limit_and_duration() -> None:
    profile = {f"{hour:02d}:{minute:02d}": 0.0 for hour in range(16, 22) for minute in (0, 30)}
    profile["19:00"] = 0.055
    plan = _plan(
        battery_capacity_kwh=1.0,
        starting_soc=80,
        demand_profile_kwh=profile,
    )
    charge = next(slot for slot in plan["slots"] if slot["action"] == "charge")
    discharge = next(slot for slot in plan["slots"] if slot["action"] == "discharge")

    assert charge["energy_kwh"] < 0.4
    assert charge["power_w"] < 800
    assert charge["command_power_limit_w"] == 800
    assert charge["duration_minutes"] < 30
    assert discharge["energy_kwh"] == 0.055
    assert discharge["power_w"] == 110
    assert discharge["command_power_limit_w"] == 800
    assert discharge["duration_minutes"] == 30


def test_incomplete_demand_profile_fails_closed_for_missing_periods() -> None:
    plan = _plan(demand_profile_kwh={"19:00": 0.1})
    discharge = [slot for slot in plan["slots"] if slot["action"] == "discharge"]

    assert [slot["local_start"] for slot in discharge] == ["19:00"]
    assert plan["planned_discharge_kwh"] == 0.1


def test_non_finite_demand_profile_fails_safe() -> None:
    plan = _plan(demand_profile_kwh={"19:00": math.nan})

    assert plan["status"] == "invalid"
    assert plan["slots"] == []


def test_wrong_day_payload_fails_safe() -> None:
    plan = AGILE.build_agile_day_plan(
        _rates("2026-07-28"),
        timezone="Europe/London",
        battery_capacity_kwh=5.874,
        starting_soc=50,
        reserve_soc=10,
        expected_date=date(2026, 7, 27),
    )

    assert plan["status"] == "invalid"
    assert plan["slots"] == []


def test_incomplete_46_period_ordinary_day_fails_safe() -> None:
    raw_rates = _rates("2026-07-27")[:46]
    plan = AGILE.build_agile_day_plan(
        raw_rates,
        timezone="Europe/London",
        battery_capacity_kwh=5.874,
        starting_soc=50,
        reserve_soc=10,
        expected_date=date(2026, 7, 27),
        protected_until="23:30",
    )

    assert plan["status"] == "invalid"
    assert plan["slots"] == []


def test_dst_days_require_the_correct_period_count() -> None:
    spring_plan = _plan("2026-03-29")
    autumn_plan = _plan("2026-10-25")

    assert spring_plan["status"] == "proposed"
    assert spring_plan["rate_period_count"] == 46
    assert spring_plan["expected_rate_period_count"] == 46
    assert spring_plan["expected_actionable_rate_period_count"] == 42
    assert autumn_plan["status"] == "proposed"
    assert autumn_plan["rate_period_count"] == 50
    assert autumn_plan["expected_rate_period_count"] == 50
    assert autumn_plan["expected_actionable_rate_period_count"] == 46


def test_non_finite_and_partially_malformed_payloads_fail_safe() -> None:
    for bad_value in (math.nan, math.inf, -math.inf):
        raw_rates = _rates("2026-07-27")
        raw_rates[0]["value_inc_vat"] = bad_value
        plan = AGILE.build_agile_day_plan(
            raw_rates,
            timezone="Europe/London",
            battery_capacity_kwh=5.874,
            starting_soc=50,
            reserve_soc=10,
            expected_date=date(2026, 7, 27),
        )
        assert plan["status"] == "invalid"
        assert plan["slots"] == []

    malformed = _rates("2026-07-27") + [{"start": "bad"}]
    plan = AGILE.build_agile_day_plan(
        malformed,
        timezone="Europe/London",
        battery_capacity_kwh=5.874,
        starting_soc=50,
        reserve_soc=10,
        expected_date=date(2026, 7, 27),
    )
    assert plan["status"] == "invalid"


def test_gap_in_rate_coverage_fails_safe() -> None:
    raw_rates = _rates("2026-07-27")
    del raw_rates[10]
    plan = AGILE.build_agile_day_plan(
        raw_rates,
        timezone="Europe/London",
        battery_capacity_kwh=5.874,
        starting_soc=50,
        reserve_soc=10,
        expected_date=date(2026, 7, 27),
    )

    assert plan["status"] == "invalid"
    assert any("consecutive" in error or "gap" in error for error in plan["validation_errors"])


def test_invalid_rate_payload_fails_safe() -> None:
    plan = AGILE.build_agile_day_plan(
        [{"start": "bad", "end": "bad", "value_inc_vat": "bad"}],
        timezone="Europe/London",
        battery_capacity_kwh=5.874,
        starting_soc=50,
        reserve_soc=10,
        expected_date=date(2026, 7, 27),
    )

    assert plan["status"] == "invalid"
    assert plan["slots"] == []
    assert plan["validation_errors"]
