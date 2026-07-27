"""Regression checks for Agile Home Assistant and Lovelace wiring."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENSOR_SOURCE = (ROOT / "custom_components" / "aecc_battery" / "sensor.py").read_text()
CARD_SOURCE = (
    ROOT
    / "custom_components"
    / "aecc_battery"
    / "frontend"
    / "aferiy-agile-plan-card.js"
).read_text()


def test_sensor_applies_behavioral_source_validator_and_stale_guard() -> None:
    assert "validate_octopus_rate_source(" in SENSOR_SOURCE
    assert "registry_entry.platform" in SENSOR_SOURCE
    assert 'timedelta(hours=36)' in SENSOR_SOURCE


def test_sensor_passes_expected_day_time_and_demand_profile_to_planner() -> None:
    assert "expected_date=expected_date" in SENSOR_SOURCE
    assert "now=now_utc" in SENSOR_SOURCE
    assert "demand_profile_kwh=AGILE_DEFAULT_DEMAND_PROFILE_KWH" in SENSOR_SOURCE


def test_agile_path_remains_shadow_only() -> None:
    agile_sensor = SENSOR_SOURCE.split("class AeccAgileProposedPlanSensor", 1)[1].split(
        "class AeccSensor",
        1,
    )[0]
    assert '"control_enabled": False' in agile_sensor
    assert "async_write_register" not in agile_sensor
    assert "async_set_" not in agile_sensor


def test_card_discovers_name_based_entity_ids_and_labels_gbp() -> None:
    assert '"_agile_proposed_plan_today"' in CARD_SOURCE
    assert '"_agile_proposed_plan_tomorrow"' in CARD_SOURCE
    assert "slot.rate_gbp_per_kwh" in CARD_SOURCE
    assert "slot.energy_kwh" in CARD_SOURCE
    assert "slot.duration_minutes" in CARD_SOURCE
    assert "slot.command_power_limit_w" in CARD_SOURCE
    assert "p/kWh" not in CARD_SOURCE
    assert '"_agile_proposed_plan_current"' not in CARD_SOURCE
    assert '"_agile_proposed_plan_next"' not in CARD_SOURCE
