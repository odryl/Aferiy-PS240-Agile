"""Tests for Octopus Weekend Happy Hours inside the Cosy battery plan.

Weekend Happy Hours are booked in the Octopus dashboard and published by the
BottlecapDave Octopus Energy integration on its power-up session events entity.
The plan overlays those windows as free energy, so the free-hour behaviour has
to be provable without live Octopus credentials.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components" / "aecc_battery" / "agile.py"
SPEC = importlib.util.spec_from_file_location("aecc_agile_happy_hour_module", MODULE_PATH)
assert SPEC and SPEC.loader
AGILE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AGILE
SPEC.loader.exec_module(AGILE)


def _rates(day: str, *, peak_rate: float = 0.45) -> list[dict[str, object]]:
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
            value = peak_rate + index / 10000
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


def _cosy_plan(day: str, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "timezone": "Europe/London",
        "battery_capacity_kwh": 5.874,
        "starting_soc": 10,
        "reserve_soc": 10,
        "expected_date": date.fromisoformat(day),
    }
    values.update(overrides)
    return AGILE.build_agile_day_plan(_rates(day), **values)


def _power_up_state(
    day: str,
    *,
    start: str,
    end: str,
    code: str = "HAPPY-HOUR-1",
    joined: bool = True,
) -> dict[str, object]:
    """Build the state-attribute shape BottlecapDave publishes for power-up events."""
    local = ZoneInfo("Europe/London")
    local_day = date.fromisoformat(day)
    event = {
        "id": "evt-1",
        "code": code,
        "start": datetime.combine(local_day, time.fromisoformat(start), tzinfo=local).isoformat(),
        "end": datetime.combine(local_day, time.fromisoformat(end), tzinfo=local).isoformat(),
        "duration_in_minutes": 60,
    }
    attributes: dict[str, object] = {"events": [], "available_events": []}
    attributes["events" if joined else "available_events"] = [event]
    return {
        "entity_id": "event.octopus_energy_A-1234ABCD_octoplus_power_up_events",
        "state": "2026-09-17T09:00:00+00:00",
        "attributes": attributes,
    }


def test_power_up_events_parse_joined_and_available_sessions() -> None:
    state = _power_up_state("2026-09-20", start="11:00", end="12:00", joined=True)
    state["attributes"]["available_events"] = [
        {
            "id": "evt-2",
            "code": "HAPPY-HOUR-2",
            "start": "2026-09-20T13:00:00+01:00",
            "end": "2026-09-20T14:00:00+01:00",
        }
    ]

    sessions, warnings = AGILE.parse_power_up_events(state, timezone="Europe/London")

    assert warnings == []
    assert [session["code"] for session in sessions] == ["HAPPY-HOUR-1", "HAPPY-HOUR-2"]
    # Local 11:00 BST is 10:00 UTC.
    assert sessions[0]["start"] == "2026-09-20T10:00:00+00:00"
    assert sessions[0]["end"] == "2026-09-20T11:00:00+00:00"
    assert sessions[0]["duration_minutes"] == 60.0


def test_power_up_events_deduplicate_and_skip_unusable_entries() -> None:
    duplicated = {
        "code": "HAPPY-HOUR-1",
        "start": "2026-09-20T11:00:00+01:00",
        "end": "2026-09-20T12:00:00+01:00",
    }
    state = {
        "attributes": {
            "events": [duplicated],
            "available_events": [
                dict(duplicated),
                {"code": "HAPPY-HOUR-BAD", "start": "not-a-time", "end": "2026-09-20T12:00:00+01:00"},
                {"code": "HAPPY-HOUR-BACKWARDS", "start": "12:00", "end": "11:00"},
                "not-a-mapping",
            ],
        }
    }

    sessions, warnings = AGILE.parse_power_up_events(state, timezone="Europe/London")

    assert len(sessions) == 1
    assert len(warnings) == 2


def test_power_up_events_ignore_explicitly_typed_sessions() -> None:
    state = {
        "attributes": {
            "events": [
                {
                    "code": "POWER-DOWN-TURN_DOWN-1",
                    "start": "2026-09-20T17:00:00+01:00",
                    "end": "2026-09-20T18:00:00+01:00",
                }
            ]
        }
    }

    sessions, warnings = AGILE.parse_power_up_events(state, timezone="Europe/London")

    assert sessions == []
    # Skipping is a guess about an undocumented code format, so it must never be
    # silent: the rejected code has to reach the plan attributes.
    assert len(warnings) == 1
    assert "POWER-DOWN-TURN_DOWN-1" in warnings[0]


def test_power_up_events_tolerate_missing_or_invalid_state() -> None:
    assert AGILE.parse_power_up_events(None, timezone="Europe/London") == ([], [])
    assert AGILE.parse_power_up_events({"attributes": {}}, timezone="Europe/London") == ([], [])
    assert AGILE.parse_power_up_events({"attributes": None}, timezone="Europe/London") == ([], [])
    sessions, warnings = AGILE.parse_power_up_events(
        {"attributes": {"events": []}},
        timezone="Not/AZone",
    )
    assert sessions == []
    assert warnings == ["The configured timezone is invalid."]


def test_happy_hour_windows_are_clipped_to_the_local_planning_day() -> None:
    sessions = [
        {
            "code": "HAPPY-HOUR-1",
            "start": "2026-09-19T23:30:00+01:00",
            "end": "2026-09-20T00:30:00+01:00",
        },
        {
            "code": "HAPPY-HOUR-2",
            "start": "2026-09-20T11:00:00+01:00",
            "end": "2026-09-20T12:00:00+01:00",
        },
        {
            "code": "HAPPY-HOUR-3",
            "start": "2026-09-21T00:00:00+01:00",
            "end": "2026-09-21T01:00:00+01:00",
        },
    ]

    windows = AGILE.resolve_happy_hour_windows(
        sessions,
        expected_date=date(2026, 9, 20),
        timezone="Europe/London",
    )

    assert [(window["local_start"], window["local_end"]) for window in windows] == [
        ("00:00", "00:30"),
        ("11:00", "12:00"),
    ]
    assert windows[0]["code"] == "HAPPY-HOUR-1"


def test_cosy_plan_charges_through_a_booked_happy_hour() -> None:
    day = "2026-09-20"
    plan = _cosy_plan(day)
    sessions, _ = AGILE.parse_power_up_events(
        _power_up_state(day, start="11:00", end="12:00"),
        timezone="Europe/London",
    )
    windows = AGILE.resolve_happy_hour_windows(
        sessions,
        expected_date=date.fromisoformat(day),
        timezone="Europe/London",
    )

    plan = AGILE.apply_cosy_rate_schedule(
        plan,
        happy_hour_windows=windows,
        happy_hour_entity_id="event.octopus_energy_A-1234ABCD_octoplus_power_up_events",
    )

    free_slots = [slot for slot in plan["slots"] if slot["tariff_phase"] == "free_energy"]
    assert [slot["local_start"] for slot in free_slots] == ["11:00", "11:30"]
    assert plan["scheduled_free_energy_periods"] == 2
    assert plan["happy_hour_entity_id"] == "event.octopus_energy_A-1234ABCD_octoplus_power_up_events"
    assert len(plan["happy_hour_windows"]) == 1
    assert "Weekend Happy Hour" in plan["reason"]
    assert "free energy" in plan["schedule_note"].lower()

    target_soc = float(plan["target_soc"])
    for slot in free_slots:
        assert slot["action"] == "charge"
        assert slot["cosy_rate_band"] == "free"
        assert slot["free_energy_rate_credited"] is True
        assert slot["free_energy_event_code"] == "HAPPY-HOUR-1"
        assert float(slot["slot_target_soc"]) <= target_soc
    # The window is inside the 07:00-13:00 Self-Gen block, so it must have
    # replaced generator-following behaviour rather than added to it.
    assert all(
        slot["tariff_phase"] != "self_gen"
        for slot in plan["slots"]
        if slot["local_start"] in ("11:00", "11:30")
    )


def test_happy_hour_import_is_credited_instead_of_billed() -> None:
    day = "2026-09-20"
    baseline = AGILE.apply_cosy_rate_schedule(_cosy_plan(day))
    sessions, _ = AGILE.parse_power_up_events(
        _power_up_state(day, start="11:00", end="12:00"),
        timezone="Europe/London",
    )
    windows = AGILE.resolve_happy_hour_windows(
        sessions,
        expected_date=date.fromisoformat(day),
        timezone="Europe/London",
    )
    with_happy_hour = AGILE.apply_cosy_rate_schedule(
        _cosy_plan(day),
        happy_hour_windows=windows,
    )

    assert with_happy_hour["happy_hour_grid_charge_kwh"] > 0
    assert with_happy_hour["estimated_happy_hour_credit_gbp"] > 0
    # Free import may add grid energy, but it must not add billed cost.
    assert with_happy_hour["planned_grid_charge_kwh"] > baseline["planned_grid_charge_kwh"]
    assert (
        with_happy_hour["estimated_grid_charge_cost_gbp"]
        <= baseline["estimated_grid_charge_cost_gbp"] + 1e-9
    )
    assert (
        with_happy_hour["average_planned_charge_rate_gbp_per_kwh"]
        <= baseline["average_planned_charge_rate_gbp_per_kwh"]
    )

    free_slots = [slot for slot in with_happy_hour["slots"] if slot["tariff_phase"] == "free_energy"]
    assert all(slot["charge_cost_gbp"] == 0.0 for slot in free_slots)
    assert all(slot["credited_back_gbp"] > 0 for slot in free_slots)
    # Credit is disclosed separately; it must not be counted again as net value.
    assert all(slot["net_saving_gbp"] == 0 for slot in free_slots)


def test_cosy_plan_is_unchanged_without_happy_hour_windows() -> None:
    day = "2026-09-20"
    implicit = AGILE.apply_cosy_rate_schedule(_cosy_plan(day))
    explicit_empty = AGILE.apply_cosy_rate_schedule(
        _cosy_plan(day),
        happy_hour_windows=[],
        happy_hour_entity_id=None,
    )

    assert implicit["scheduled_free_energy_periods"] == 0
    assert implicit["happy_hour_windows"] == []
    assert implicit["happy_hour_entity_id"] is None
    assert [slot["tariff_phase"] for slot in implicit["slots"]] == [
        slot["tariff_phase"] for slot in explicit_empty["slots"]
    ]
    assert implicit["planned_grid_charge_kwh"] == explicit_empty["planned_grid_charge_kwh"]
    assert implicit["estimated_happy_hour_credit_gbp"] == 0.0


def test_happy_hour_outside_the_tariff_day_is_ignored() -> None:
    day = "2026-09-20"
    sessions, _ = AGILE.parse_power_up_events(
        _power_up_state("2026-09-19", start="11:00", end="12:00"),
        timezone="Europe/London",
    )
    windows = AGILE.resolve_happy_hour_windows(
        sessions,
        expected_date=date.fromisoformat(day),
        timezone="Europe/London",
    )

    plan = AGILE.apply_cosy_rate_schedule(_cosy_plan(day), happy_hour_windows=windows)

    assert windows == []
    assert plan["scheduled_free_energy_periods"] == 0
    assert plan["happy_hour_grid_charge_kwh"] == 0


def test_happy_hour_periods_are_exposed_for_the_dashboard_card() -> None:
    day = "2026-09-20"
    sessions, _ = AGILE.parse_power_up_events(
        _power_up_state(day, start="11:00", end="12:00"),
        timezone="Europe/London",
    )
    windows = AGILE.resolve_happy_hour_windows(
        sessions,
        expected_date=date.fromisoformat(day),
        timezone="Europe/London",
    )
    plan = AGILE.apply_cosy_rate_schedule(_cosy_plan(day), happy_hour_windows=windows)

    free_periods = [
        period for period in plan["cosy_periods"] if period["tariff_phase"] == "free_energy"
    ]
    assert len(free_periods) == 1
    assert free_periods[0]["local_start"] == "11:00"
    assert free_periods[0]["local_end"] == "12:00"
    assert free_periods[0]["duration_minutes"] == 60.0

    # The live control layer must surface the free period as a charge command.
    action = AGILE.cosy_period_action(
        plan,
        datetime(2026, 9, 20, 11, 10, tzinfo=ZoneInfo("Europe/London")),
    )
    assert action is not None
    assert action["action"] == "charge"
    assert action["tariff_phase"] == "free_energy"
    assert action["decision_source"] == "current_cosy_period"


def test_happy_hour_charge_carries_into_the_evening_peak() -> None:
    day = "2026-09-20"
    baseline = AGILE.apply_cosy_rate_schedule(_cosy_plan(day))
    sessions, _ = AGILE.parse_power_up_events(
        _power_up_state(day, start="17:00", end="18:00"),
        timezone="Europe/London",
    )
    windows = AGILE.resolve_happy_hour_windows(
        sessions,
        expected_date=date.fromisoformat(day),
        timezone="Europe/London",
    )
    with_happy_hour = AGILE.apply_cosy_rate_schedule(
        _cosy_plan(day),
        happy_hour_windows=windows,
    )

    # The free hour sits in the 16:00-22:00 peak block, so it must both charge
    # for free and leave more stored energy for the evening.
    assert [slot["local_start"] for slot in with_happy_hour["slots"] if slot["tariff_phase"] == "free_energy"] == [
        "17:00",
        "17:30",
    ]
    # The free hour is spent inside the evening peak, so the value is displaced
    # peak import rather than a fuller battery at midnight: the 850 W home-supply
    # limit means the battery still drains to the same floor either way.
    assert with_happy_hour["planned_discharge_kwh"] > baseline["planned_discharge_kwh"]
    assert (
        with_happy_hour["estimated_avoided_import_cost_gbp"]
        > baseline["estimated_avoided_import_cost_gbp"]
    )
    assert with_happy_hour["estimated_net_saving_gbp"] > baseline["estimated_net_saving_gbp"]
    assert with_happy_hour["estimated_grid_charge_cost_gbp"] <= baseline["estimated_grid_charge_cost_gbp"] + 1e-9


def test_free_window_charges_every_half_hour_it_touches() -> None:
    day = "2026-09-20"
    sessions, _ = AGILE.parse_power_up_events(
        _power_up_state(day, start="15:30", end="16:30"),
        timezone="Europe/London",
    )
    windows = AGILE.resolve_happy_hour_windows(
        sessions,
        expected_date=date.fromisoformat(day),
        timezone="Europe/London",
    )
    plan = AGILE.apply_cosy_rate_schedule(_cosy_plan(day), happy_hour_windows=windows)

    free_starts = [slot["local_start"] for slot in plan["slots"] if slot["tariff_phase"] == "free_energy"]
    assert free_starts == ["15:30", "16:00"]
    assert plan["scheduled_free_energy_periods"] == 2
    # 16:00-16:30 is a peak slot that the free window converts to charging.
    peak_free = next(slot for slot in plan["slots"] if slot["local_start"] == "16:00")
    assert peak_free["action"] == "charge"
    assert peak_free["cosy_rate_band"] == "free"
    assert peak_free["credited_back_gbp"] > 0
