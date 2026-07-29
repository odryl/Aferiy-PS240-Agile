"""Regression checks for the local datalogger restart controls."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "aecc_battery"
CLIENT_SOURCE = (INTEGRATION / "tcp_client.py").read_text()
COORDINATOR_SOURCE = (INTEGRATION / "coordinator.py").read_text()
INIT_SOURCE = (INTEGRATION / "__init__.py").read_text()
SWITCH_SOURCE = (INTEGRATION / "switch.py").read_text()
BUTTON_SOURCE = (INTEGRATION / "button.py").read_text()


def test_restart_uses_local_device_management_parameter_32() -> None:
    restart_method = CLIENT_SOURCE.split("async def restart_datalogger", 1)[1].split(
        "# ── Low-level", 1
    )[0]

    assert '"Set": "DeviceManagement"' in restart_method
    assert '"CommandSource": "HA"' in restart_method
    assert '"DeviceManagementAddr": {"32": "1"}' in restart_method
    assert "await writer.drain()" in restart_method
    assert "dispatched = True" in restart_method
    assert "await self._manager.close()" in restart_method


def test_automatic_restart_is_opt_in_persisted_and_three_hourly() -> None:
    assert "_DATALOGGER_AUTO_RESTART_INTERVAL = timedelta(hours=3)" in COORDINATOR_SOURCE
    assert "self.auto_datalogger_restart_enabled: bool = False" in COORDINATOR_SOURCE
    assert 'data.get("auto_datalogger_restart_enabled", False)' in COORDINATOR_SOURCE
    assert '"auto_datalogger_restart_enabled": bool(' in COORDINATOR_SOURCE
    assert 'reason="automatic"' in COORDINATOR_SOURCE
    assert "task.cancel()" in COORDINATOR_SOURCE


def test_home_assistant_exposes_manual_button_and_automatic_switch() -> None:
    assert "Platform.SWITCH" in INIT_SOURCE
    assert "Platform.BUTTON" in INIT_SOURCE
    assert "AeccAutomaticDataloggerRestartSwitch" in SWITCH_SOURCE
    assert '_attr_name = "Automatic Data Logger Restart"' in SWITCH_SOURCE
    assert "AeccRestartDataloggerButton" in BUTTON_SOURCE
    assert '_attr_name = "Restart Data Logger"' in BUTTON_SOURCE
    assert 'reason="manual"' in BUTTON_SOURCE
    assert "await coordinator.async_shutdown()" in INIT_SOURCE
