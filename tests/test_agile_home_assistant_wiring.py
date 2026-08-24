"""Regression checks for Agile Home Assistant and Lovelace wiring."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENSOR_SOURCE = (ROOT / "custom_components" / "aecc_battery" / "sensor.py").read_text()
INIT_SOURCE = (ROOT / "custom_components" / "aecc_battery" / "__init__.py").read_text()
CARD_SOURCE = (
    ROOT
    / "custom_components"
    / "aecc_battery"
    / "frontend"
    / "aferiy-agile-plan-card.js"
).read_text()
SELECT_SOURCE = (ROOT / "custom_components" / "aecc_battery" / "select.py").read_text()


def test_sensor_applies_behavioral_source_validator_and_stale_guard() -> None:
    assert "validate_octopus_rate_source(" in SENSOR_SOURCE
    assert "registry_entry.platform" in SENSOR_SOURCE
    assert 'timedelta(hours=36)' in SENSOR_SOURCE


def test_sensor_waits_for_unpublished_rate_events_without_invalidating_the_other_day() -> None:
    assert 'raw_rates is None or raw_rates == []' in SENSOR_SOURCE
    assert 'Octopus has not published {self._day_kind}-day rates' in SENSOR_SOURCE
    assert 'counterpart_attributes = None' in SENSOR_SOURCE
    assert 'and counterpart.attributes.get("rates")' in SENSOR_SOURCE


def test_sensor_passes_expected_day_time_and_demand_profile_to_planner() -> None:
    assert "expected_date=expected_date" in SENSOR_SOURCE
    assert "now=now_utc" in SENSOR_SOURCE
    assert "demand_profile_kwh=AGILE_DEFAULT_DEMAND_PROFILE_KWH" in SENSOR_SOURCE
    assert "demand_profile_revision=AGILE_DEMAND_PROFILE_REVISION" in SENSOR_SOURCE


def test_sensor_replans_both_days_as_one_rolling_horizon_when_rates_exist() -> None:
    assert 'next_day_rates=counterpart_rates if self._day_kind == "current" else None' in SENSOR_SOURCE
    assert 'starting_soc_source = "today_projected_protection_end_soc"' in SENSOR_SOURCE
    assert 'today_plan.get("projected_soc_at_protection_end")' in SENSOR_SOURCE
    assert "counterpart.last_updated if counterpart_rates is not None else None" in SENSOR_SOURCE


def test_agile_path_remains_shadow_only() -> None:
    agile_sensor = SENSOR_SOURCE.split("class AeccAgileProposedPlanSensor", 1)[1].split(
        "class AeccSensor",
        1,
    )[0]
    assert '"control_enabled": False' in agile_sensor
    assert "async_write_register" not in agile_sensor
    assert "async_set_" not in agile_sensor


def test_self_gen_reconnect_queue_is_manual_only_and_not_an_agile_control_path() -> None:
    assert "AeccSelfGenReconnectQueueSelect" in SELECT_SOURCE
    assert '"On (60 minutes)"' in SELECT_SOURCE
    assert "async_queue_self_gen_on_reconnect" in SELECT_SOURCE
    assert "Charge, Discharge, Feed, and Agile Proposed Plans are never queued." in SELECT_SOURCE
    assert "_SELF_GEN_RECONNECT_QUEUE_TTL = timedelta(minutes=60)" in (
        ROOT / "custom_components" / "aecc_battery" / "coordinator.py"
    ).read_text()


def test_agile_planner_always_exposes_its_battery_capacity_setting() -> None:
    assert "CONF_AGILE_PLANNER_ENABLED" in SELECT_SOURCE
    assert "DEFAULT_AGILE_PLANNER_ENABLED" in SELECT_SOURCE
    assert "or config_entry.options.get(" in SELECT_SOURCE
    assert "AeccBatteryCapacityPresetSelect" in SELECT_SOURCE


def test_agile_plan_export_is_read_only_and_redacts_rate_source_metadata() -> None:
    assert 'SERVICE_EXPORT_AGILE_PLAN = "export_agile_plan"' in INIT_SOURCE
    assert "AGILE_PLAN_EXPORT_FILENAME" in INIT_SOURCE
    assert 'frozenset({"mpan", "source_entity"})' in INIT_SOURCE
    assert "_agile_trial_telemetry(" in INIT_SOURCE
    assert '"house_demand_power_w"' in INIT_SOURCE
    assert '"grid_power_w"' in INIT_SOURCE
    assert '"soc_percent"' in INIT_SOURCE
    assert '"schema_version": 3' in INIT_SOURCE
    assert '"planner_revisions": planner_revisions' in INIT_SOURCE
    assert '"demand_profile_revisions": demand_profile_revisions' in INIT_SOURCE
    assert '"energy_charged_kwh"' in INIT_SOURCE
    assert '"energy_discharged_kwh"' in INIT_SOURCE
    assert '"pv_energy_generated_kwh"' in INIT_SOURCE
    assert '"control_context"' in INIT_SOURCE
    assert '"operating_mode"' in INIT_SOURCE
    assert '"last_local_command"' in INIT_SOURCE
    assert '"commanded_direction"' in INIT_SOURCE
    assert '"automatic_overnight_charging"' in INIT_SOURCE
    assert '"connection_last_update_success"' in INIT_SOURCE
    assert '"connection_age_seconds"' in INIT_SOURCE
    assert '"agile_shadow_decision"' in INIT_SOURCE
    assert "append_agile_json_line" in INIT_SOURCE
    assert '"control_enabled": False' in INIT_SOURCE
    export_service = INIT_SOURCE.split("async def async_export_agile_plan", 1)[1].split(
        "async def async_restore_original_self_consumption", 1
    )[0]
    assert "async_write_register" not in export_service
    assert "async_set_" not in export_service


def test_card_discovers_entities_and_exposes_energy_costs_and_savings() -> None:
    assert '"_agile_proposed_plan_today"' in CARD_SOURCE
    assert '"_agile_proposed_plan_tomorrow"' in CARD_SOURCE
    assert '"_agile_shadow_operating_state"' in CARD_SOURCE
    assert "Shadow operating state" in CARD_SOURCE
    assert "slot.rate_gbp_per_kwh" in CARD_SOURCE
    assert "slot.energy_kwh" in CARD_SOURCE
    assert "slot.duration_minutes" in CARD_SOURCE
    assert "slot.command_power_limit_w" in CARD_SOURCE
    assert "estimated_grid_charge_cost_gbp" in CARD_SOURCE
    assert "estimated_avoided_import_cost_gbp" in CARD_SOURCE
    assert "estimated_discharge_replacement_cost_gbp" in CARD_SOURCE
    assert "estimated_net_saving_gbp" in CARD_SOURCE
    assert "current_rate_gbp_per_kwh" in CARD_SOURCE
    assert "lowest_future_rate_gbp_per_kwh" in CARD_SOURCE
    assert "lowlimit" in CARD_SOURCE
    assert "mediumlimit" in CARD_SOURCE
    assert "highlimit" in CARD_SOURCE
    assert "rate.current" in CARD_SOURCE
    assert "All half-hour Agile prices" in CARD_SOURCE
    assert "Rolling horizon active" in CARD_SOURCE
    assert "Battery SOC starts below reserve" in CARD_SOURCE
    assert "projected_soc_at_protection_end" in CARD_SOURCE
    assert "replacement_rate_source" in CARD_SOURCE
    assert '"_agile_proposed_plan_current"' not in CARD_SOURCE
    assert '"_agile_proposed_plan_next"' not in CARD_SOURCE


def test_shadow_state_machine_is_registered_and_remains_view_only() -> None:
    assert "AeccAgileShadowOperatingStateSensor" in SENSOR_SOURCE
    assert "_agile_shadow_operating_state" in SENSOR_SOURCE
    assert "build_agile_shadow_decision(" in SENSOR_SOURCE
    shadow_sensor = SENSOR_SOURCE.split("class AeccAgileShadowOperatingStateSensor", 1)[1].split(
        "class AeccSensor",
        1,
    )[0]
    assert "async_write_register" not in shadow_sensor
    assert "async_set_battery_control" not in shadow_sensor


def test_midnight_rate_entity_rollover_is_a_waiting_state() -> None:
    assert 'plan.get("status") == "invalid"' in SENSOR_SOURCE
    assert '"rollover_grace_active": True' in SENSOR_SOURCE
    assert "Octopus is rolling the current-day and next-day rate entities" in SENSOR_SOURCE


def test_card_avoids_unrelated_renders_and_preserves_open_rate_tables() -> None:
    assert "_renderIfNeeded()" in CARD_SOURCE
    assert "signature === this._renderSignature" in CARD_SOURCE
    assert "nextSignature !== this._configSignature" in CARD_SOURCE
    assert "today?.attributes" in CARD_SOURCE
    assert "today?.last_updated" not in CARD_SOURCE
    assert "window.sessionStorage" in CARD_SOURCE
    assert "details.open = this._openTimelines.has(details.dataset.timeline)" in CARD_SOURCE
    assert 'details.addEventListener("toggle"' in CARD_SOURCE
