"""Execute the actual HA adapter classes against lightweight host doubles."""

import ast
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from test_solar_jit_and_outcomes import INSIGHTS, NOW, ROOT, SOLAR


class Entity:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.writes = 0
        self.removers = []

    @classmethod
    def __class_getitem__(cls, _item):
        return cls

    async def async_added_to_hass(self):
        pass

    async def async_will_remove_from_hass(self):
        pass

    def async_on_remove(self, remove):
        self.removers.append(remove)

    def async_write_ha_state(self):
        self.writes += 1


def runtime():
    source = ast.parse((ROOT / "sensor.py").read_text())
    classes = [
        n
        for n in source.body
        if isinstance(n, ast.ClassDef) and n.name in ("AeccPlanningSolarForecastSensor", "AeccDailyPlanOutcomesSensor")
    ]
    store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
    registry = SimpleNamespace(async_get_entity_id=lambda _p, _d, suffix: "sensor." + suffix)
    clock = [NOW]
    ns = {
        "asyncio": asyncio,
        "AeccRecorderLeanMixin": type("Mixin", (), {}),
        "CoordinatorEntity": Entity,
        "AeccBatteryCoordinator": object,
        "SensorEntity": type("Sensor", (), {}),
        "timedelta": timedelta,
        "datetime": datetime,
        "date": date,
        "ZoneInfo": ZoneInfo,
        "_LOGGER": logging.getLogger(__name__),
        "utcnow": lambda: clock[0],
        "callback": lambda f: f,
        "forecast_entries": SOLAR.forecast_entries,
        "normalize_forecasts": SOLAR.normalize_forecasts,
        "timestamp": INSIGHTS.timestamp,
        "OutcomeLedger": INSIGHTS.OutcomeLedger,
        "_as_float": lambda value, default=None: (
            INSIGHTS.number(value) if INSIGHTS.number(value) is not None else default
        ),
        "er": SimpleNamespace(async_get=lambda _: registry),
        "DOMAIN": "aecc_battery",
        "Store": lambda *args: store,
        "EVENT_HOMEASSISTANT_STOP": "stop",
        "async_track_time_interval": lambda *args: lambda: None,
    }
    exec(compile(ast.Module(body=classes, type_ignores=[]), "sensor.py", "exec"), ns)  # noqa: S102 - execute trusted local adapter classes
    coord = SimpleNamespace(
        energy_dashboard_manager=SimpleNamespace(
            data={"energy_sources": [{"type": "solar", "config_entry_solar_forecast": ["solar", "solar"]}]}
        ),
        last_update_success=True,
        last_successful_update=NOW,
        device_info={},
        get_value=lambda key: {
            "ac_charging_power": 1200,
            "total_battery_output_power": 0,
            "grid_power": 1200,
            "average_battery_soc": 70,
        }.get(key),
        cosy_controller=None,
        agile_controller=None,
    )
    states = {}
    hass = SimpleNamespace(
        config=SimpleNamespace(time_zone="Europe/London"),
        config_entries=SimpleNamespace(async_get_entry=lambda key: SimpleNamespace(domain="test_solar", entry_id=key)),
        states=SimpleNamespace(get=states.get),
        bus=SimpleNamespace(async_listen_once=lambda *args: lambda: None),
    )
    return ns, coord, hass, store, states, clock


def test_forecast_adapter_calls_only_configured_providers_and_clears_failed_cache(monkeypatch):
    ns, coord, hass, _, _, _ = runtime()
    provider = AsyncMock(return_value={"wh_hours": {NOW.isoformat(): 1000}})
    platform = ModuleType("homeassistant.components.energy.websocket_api")
    platform.async_get_energy_platforms = AsyncMock(return_value={"test_solar": provider})
    monkeypatch.setitem(sys.modules, platform.__name__, platform)
    sensor = ns["AeccPlanningSolarForecastSensor"](coord, SimpleNamespace(entry_id="battery"))
    sensor.hass = hass
    asyncio.run(sensor.async_added_to_hass())
    provider.assert_awaited_once_with(hass, "solar")
    assert sensor.native_value == "available"
    assert sensor.extra_state_attributes["periods"][0]["kwh"] == 1
    provider.side_effect = RuntimeError("provider offline")
    asyncio.run(sensor._async_refresh())
    assert sensor.native_value == "provider_unavailable"
    assert coord.planning_solar_forecast["periods"] == []


def test_outcome_adapter_samples_once_per_poll_persists_and_reports_storage_failure():
    ns, coord, hass, store, states, clock = runtime()
    states["sensor.battery_agile_proposed_plan_current"] = SimpleNamespace(
        attributes={
            "status": "proposed",
            "date": "2026-09-17",
            "ready_by": "16:00",
            "target_soc": 90,
            "planning_time": NOW.isoformat(),
            "slots": [
                {
                    "start": NOW.isoformat(),
                    "end": (NOW + timedelta(minutes=30)).isoformat(),
                    "action": "charge",
                    "energy_kwh": 0.6,
                    "rate_gbp_per_kwh": 0.1,
                }
            ],
        }
    )
    sensor = ns["AeccDailyPlanOutcomesSensor"](coord, SimpleNamespace(entry_id="battery"))
    sensor.hass = hass
    asyncio.run(sensor.async_added_to_hass())
    sensor._handle_coordinator_update()  # Duplicate telemetry must not add energy.
    assert sensor.extra_state_attributes["days"][0]["observed_seconds"] == 0
    clock[0] += timedelta(seconds=30)
    coord.last_successful_update = clock[0]
    sensor._handle_coordinator_update()
    assert sensor.extra_state_attributes["days"][0]["ac_charge_kwh"] == 0.01
    asyncio.run(sensor._async_save())
    assert store.async_save.await_count == 1
    assert sensor.extra_state_attributes["storage_status"] == "ready"
    store.async_save.side_effect = OSError("disk full")
    asyncio.run(sensor._async_save())
    assert sensor.extra_state_attributes["storage_status"] == "save_failed"
    assert sensor.extra_state_attributes["days"][0]["ac_charge_kwh"] == 0.01
