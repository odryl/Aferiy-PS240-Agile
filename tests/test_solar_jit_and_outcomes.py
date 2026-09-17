"""Forecast timing and outcome accounting scenarios, without device writes."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_agile_planner import AGILE
from test_cosy_projection import plan_at

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "aecc_battery"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SOLAR = load("solar_planning")
INSIGHTS = load("plan_insights")
NOW = datetime(2026, 9, 17, 12, tzinfo=UTC)  # 13:00 local


def forecast(now=NOW, energy=1000):
    return SOLAR.normalize_forecasts(
        {"site": {"wh_hours": {(now.replace(minute=0) + timedelta(hours=i)).isoformat(): energy for i in range(6)}}},
        now,
    )


def decision(plan, at=NOW, soc=70, prediction=None, action=None, **kwargs):
    return AGILE.build_agile_shadow_decision(
        plan,
        now=at.astimezone(__import__("zoneinfo").ZoneInfo("Europe/London")),
        connection_fresh=True,
        soc_percent=soc,
        reserve_soc=20,
        pv_power_w=0,
        total_charge_power_w=0,
        ac_charge_power_w=0,
        pv_quiet_minutes=30,
        locked_action=action or AGILE.cosy_period_action(plan, at),
        solar_forecast=prediction,
        **kwargs,
    )


def test_configured_providers_are_deduplicated_and_energy_units_are_explicit():
    prefs = {
        "energy_sources": [
            {"type": "solar", "config_entry_solar_forecast": ["a", "b", "a"]},
            {"type": "grid", "config_entry_solar_forecast": ["wrong"]},
        ]
    }
    assert SOLAR.forecast_entries(prefs) == ["a", "b"]
    result = SOLAR.normalize_forecasts(
        {"a": {"wh_hours": {NOW.isoformat(): 1000}}, "b": {"wh_hours": {NOW.isoformat(): 500}}}, NOW
    )
    assert result["periods"][0]["kwh"] == 1.5
    assert result["periods"][0]["end"] == (NOW + timedelta(hours=1)).isoformat()


@pytest.mark.parametrize(
    "time,value",
    [("not a date", 500), ("2026-09-17T12:00", 500), (NOW.isoformat(), float("nan")), (NOW.isoformat(), -1)],
)
def test_bad_provider_data_is_unusable(time, value):
    assert SOLAR.normalize_forecasts({"site": {"wh_hours": {time: value}}}, NOW)["status"] == "invalid_forecast"


def test_dst_repeated_hours_remain_distinct_utc_buckets():
    result = SOLAR.normalize_forecasts(
        {
            "site": {
                "wh_hours": {
                    "2026-10-25T01:00:00+01:00": 1000,
                    "2026-10-25T01:00:00+00:00": 2000,
                }
            }
        },
        datetime(2026, 10, 25, tzinfo=UTC),
    )
    assert [p["kwh"] for p in result["periods"]] == [1, 2]
    assert result["periods"][0]["end"] == result["periods"][1]["start"]


def test_cosy_forecast_wait_preserves_target_and_grid_only_deadline():
    plan = AGILE.apply_cosy_rate_schedule(plan_at(clock="13:00", starting_soc=70))
    result = decision(plan, prediction=forecast())
    assert result["state"] == "Forecast Solar Wait"
    assert result["target_soc"] == 90
    assert result["forecast_target_credit_kwh"] == 0
    assert result["required_charge_minutes"] == pytest.approx(5.874 * 0.2 / 1.08 * 60, abs=0.051)
    latest = datetime.fromisoformat(result["latest_grid_charge_start"])
    # Even an enormous solar forecast cannot postpone grid catch-up.
    huge = decision(plan, prediction=forecast(energy=50000))
    assert huge["latest_grid_charge_start"] == result["latest_grid_charge_start"]
    forced = decision(plan, at=latest, prediction=forecast(latest))
    assert forced["state"] == "Planned Charge"
    assert forced["recommended_operating_mode"] == "Charge"
    assert AGILE.agile_control_mode_for_state(result["state"], result["recommended_operating_mode"]) == "Idle"
    assert AGILE.bounded_agile_command_window("Charge", forced, latest) is not None


@pytest.mark.parametrize("kind", ["missing", "stale", "future_retrieval", "gap", "zero", "provider_failure"])
def test_unusable_forecasts_do_not_defer_grid_charging(kind):
    prediction = forecast()
    if kind == "missing":
        prediction = None
    elif kind == "stale":
        prediction["retrieved_at"] = (NOW - timedelta(hours=1)).isoformat()
    elif kind == "future_retrieval":
        prediction["retrieved_at"] = (NOW + timedelta(hours=1)).isoformat()
    elif kind == "gap":
        prediction["periods"].pop(1)
    elif kind == "zero":
        prediction = forecast(energy=0)
    else:
        prediction["status"] = "provider_unavailable"
    plan = AGILE.apply_cosy_rate_schedule(plan_at(clock="13:00", starting_soc=70))
    assert decision(plan, prediction=prediction)["state"] == "Planned Charge"


def test_unreachable_target_charges_immediately_despite_sunny_forecast():
    plan = AGILE.apply_cosy_rate_schedule(plan_at(clock="15:45", starting_soc=30))
    at = NOW + timedelta(hours=2, minutes=45)
    result = decision(plan, at=at, soc=30, prediction=forecast(at))
    assert result["state"] == "Planned Charge"
    assert result["target_reachable_on_grid"] is False


def test_free_window_is_never_deferred_by_forecast():
    plan = AGILE.apply_cosy_rate_schedule(
        plan_at(clock="13:00", starting_soc=70),
        happy_hour_windows=[{"start": NOW.isoformat(), "end": (NOW + timedelta(hours=1)).isoformat()}],
    )
    assert decision(plan, prediction=forecast())["state"] != "Forecast Solar Wait"


def test_agile_jit_respects_shortened_command_window():
    plan = plan_at(clock="13:00", starting_soc=89)
    action = {
        "start": NOW.isoformat(),
        "end": (NOW + timedelta(minutes=30)).isoformat(),
        "action": "charge",
        "command_power_limit_w": 1200,
        "duration_minutes": 10,
        "energy_kwh": 0.2,
    }
    result = decision(plan, soc=89, prediction=forecast(), action=action)
    assert result["state"] == "Forecast Solar Wait"
    assert datetime.fromisoformat(result["charge_deadline"]) == NOW + timedelta(minutes=10)
    latest = datetime.fromisoformat(result["latest_grid_charge_start"])
    forced = decision(plan, at=latest, soc=89, prediction=forecast(), action=action)
    window = AGILE.bounded_agile_command_window("Charge", forced, latest)
    assert window is not None
    assert window[1] == NOW + timedelta(minutes=10)


def sample(at=NOW, **kwargs):
    return {
        "at": at.isoformat(),
        "fresh": True,
        "charge_w": 1200,
        "output_w": 0,
        "grid_w": 800,
        "soc": 70,
        "enabled": True,
        "control": "Active",
        "mode": "Charge",
        "reason": "test",
        "rates": [
            {
                "start": (at - timedelta(hours=1)).isoformat(),
                "end": (at + timedelta(hours=1)).isoformat(),
                "rate_gbp_per_kwh": 0.1,
            }
        ],
        "plan_grid_charge_kwh": 2.0,
        **kwargs,
    }


def test_power_energy_costs_and_frozen_plan_are_comparable():
    ledger = INSIGHTS.OutcomeLedger("Europe/London")
    ledger.observe(sample())
    ledger.observe(sample(NOW + timedelta(seconds=30), plan_grid_charge_kwh=1.0))
    day = ledger.summary()[0]
    assert day["ac_charge_kwh"] == pytest.approx(0.01)
    assert day["grid_charge_kwh"] == pytest.approx(800 / 120000)
    assert day["charge_cost_gbp"] == pytest.approx(800 / 120000 * 0.1)
    assert day["plan_grid_charge_kwh"] == 2
    assert day["ac_since_plan_kwh"] == pytest.approx(0.01)


@pytest.mark.parametrize("gap", [91, 1800, 3600])
def test_telemetry_gaps_are_not_integrated(gap):
    ledger = INSIGHTS.OutcomeLedger("Europe/London")
    ledger.observe(sample())
    ledger.observe(sample(NOW + timedelta(seconds=gap)))
    assert ledger.summary()[0]["observed_seconds"] == 0
    assert ledger.summary()[0]["ac_charge_kwh"] == 0


def test_restart_preserves_history_without_bridging_gap_or_mutating_snapshot():
    ledger = INSIGHTS.OutcomeLedger("Europe/London")
    ledger.observe(sample())
    ledger.observe(sample(NOW + timedelta(seconds=30)))
    saved = ledger.snapshot()
    restarted = INSIGHTS.OutcomeLedger("Europe/London", saved)
    restarted.observe(sample(NOW + timedelta(seconds=60)))
    assert restarted.summary()[0]["ac_charge_kwh"] == pytest.approx(0.01)
    ledger.observe(sample(NOW + timedelta(seconds=60)))
    assert saved["days"]["2026-09-17"]["ac_charge_kwh"] == pytest.approx(0.01)


def test_midnight_splits_energy_cost_and_target_into_correct_days():
    midnight = datetime(2026, 9, 17, 23, tzinfo=UTC)
    ledger = INSIGHTS.OutcomeLedger("Europe/London")
    before = sample(midnight - timedelta(seconds=30), targets=[{"at": midnight.isoformat(), "target_soc": 80}])
    before["rates"] = [
        {"start": (midnight - timedelta(minutes=30)).isoformat(), "end": midnight.isoformat(), "rate_gbp_per_kwh": 0.1}
    ]
    after = sample(midnight + timedelta(seconds=30), soc=81)
    after["rates"] = [
        {"start": midnight.isoformat(), "end": (midnight + timedelta(minutes=30)).isoformat(), "rate_gbp_per_kwh": 0.3}
    ]
    ledger.observe(before)
    ledger.observe(after)
    today, yesterday = ledger.summary()
    assert today["date"] == "2026-09-18"
    assert today["ac_charge_kwh"] == yesterday["ac_charge_kwh"] == pytest.approx(0.01)
    assert today["charge_cost_gbp"] == pytest.approx(yesterday["charge_cost_gbp"] * 3)
    assert yesterday["targets"][0]["result"] == "achieved"
    assert yesterday["coverage_percent"] < 1


def test_target_after_restart_is_unknown_and_failed_enable_is_recorded():
    deadline = NOW + timedelta(minutes=1)
    ledger = INSIGHTS.OutcomeLedger("Europe/London")
    ledger.observe(sample(targets=[{"at": deadline.isoformat(), "target_soc": 80}]))
    restarted = INSIGHTS.OutcomeLedger("Europe/London", ledger.snapshot())
    restarted.observe(
        sample(
            deadline + timedelta(seconds=10), soc=90, enabled=False, control="Inhibited", reason="Select Self-Gen first"
        )
    )
    day = restarted.summary()[0]
    assert day["targets"][0]["result"] == "unknown"
    assert day["interruptions"] == 1
    assert day["events"][-1]["reason"] == "Select Self-Gen first"


def test_solar_wait_requires_executed_wait_and_invalid_grid_is_unpriced():
    ledger = INSIGHTS.OutcomeLedger("Europe/London")
    ledger.observe(sample(solar_wait_active=False, grid_w=None))
    ledger.observe(sample(NOW + timedelta(seconds=30), solar_wait_active=True, grid_w=None))
    ledger.observe(sample(NOW + timedelta(seconds=60), solar_wait_active=False, grid_w=None))
    day = ledger.summary()[0]
    assert day["solar_wait_minutes"] == 0.5
    assert day["grid_observed_seconds"] == 0
    assert day["ac_charge_kwh"] == 0.02


def test_history_is_bounded_to_fourteen_days():
    ledger = INSIGHTS.OutcomeLedger("Europe/London")
    for offset in range(20):
        ledger.observe(sample(NOW + timedelta(days=offset)))
    assert len(ledger.summary()) == 14


def test_running_ac_charge_and_reserve_recovery_do_not_start_forecast_waits():
    plan = AGILE.apply_cosy_rate_schedule(plan_at(clock="13:00", starting_soc=70))
    action = AGILE.cosy_period_action(plan, NOW)
    base = {
        "plan": plan,
        "now": NOW,
        "connection_fresh": True,
        "reserve_soc": 20,
        "pv_power_w": 0,
        "total_charge_power_w": 0,
        "pv_quiet_minutes": 30,
        "locked_action": action,
        "solar_forecast": forecast(),
    }
    running = AGILE.build_agile_shadow_decision(**base, soc_percent=70, ac_charge_power_w=1200)
    assert running["state"] == "Planned Charge"
    assert running["forecast_wait_allowed"] is False
    reserve = AGILE.build_agile_shadow_decision(
        **base, soc_percent=19, ac_charge_power_w=0, cosy_daylight_flex_enabled=True
    )
    assert reserve["state"] == "Planned Charge"
    assert "reserve" in reserve["reason"]


@pytest.mark.parametrize("weather", ["cloudy", "sunny", "forecast_failed"])
def test_simulated_afternoon_reaches_target_without_forecast_credit(weather):
    plan = AGILE.apply_cosy_rate_schedule(plan_at(clock="13:00", starting_soc=70))
    soc, ac = 70.0, 0.0
    prediction = forecast()
    for step in range(360):  # Three hours, thirty-second telemetry polls.
        at = NOW + timedelta(seconds=step * 30)
        if step % 30 == 0:
            prediction = forecast(at)
        if weather == "forecast_failed" and step >= 120:
            prediction = {"status": "provider_unavailable", "periods": []}
        result = AGILE.build_agile_shadow_decision(
            plan,
            now=at,
            connection_fresh=True,
            soc_percent=soc,
            reserve_soc=20,
            pv_power_w=0,
            total_charge_power_w=ac,
            ac_charge_power_w=ac,
            pv_quiet_minutes=30,
            locked_action=AGILE.cosy_period_action(plan, at),
            solar_forecast=prediction,
        )
        mode = result["recommended_operating_mode"]
        assert mode in ("Idle", "Charge", "Self-Gen/Zero Export")
        ac = 1200 if mode == "Charge" else 0
        solar = 400 if weather == "sunny" and step < 240 else 0
        soc = min(90, soc + (ac + solar) / 1000 * 0.9 / 120 / 5.874 * 100)
    assert soc >= 89.5


def test_happy_hour_observed_credit_is_separate_from_charge_cost():
    ledger = INSIGHTS.OutcomeLedger("Europe/London")
    first = sample()
    first["rates"][0]["tariff_phase"] = "free_energy"
    ledger.observe(first)
    ledger.observe(sample(NOW + timedelta(seconds=30)))
    day = ledger.summary()[0]
    assert day["grid_charge_kwh"] > 0
    assert day["charge_cost_gbp"] == 0
    assert day["happy_hour_credit_gbp"] > 0


def test_failed_poll_breaks_coverage_and_repeated_inhibition_does_not_inflate_count():
    ledger = INSIGHTS.OutcomeLedger("Europe/London")
    ledger.observe(sample())
    ledger.observe(sample(NOW + timedelta(seconds=30), fresh=False, control="Fail-safe"))
    ledger.observe(sample(NOW + timedelta(seconds=60), fresh=False, control="Fail-safe"))
    ledger.observe(sample(NOW + timedelta(seconds=90)))
    day = ledger.summary()[0]
    assert day["observed_seconds"] == 0
    assert day["interruptions"] == 1
