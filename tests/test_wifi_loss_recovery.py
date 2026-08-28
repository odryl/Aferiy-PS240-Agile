"""Regression checks for guarded Linksys Wi-Fi loss recovery."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "aecc_battery"

# The CI regression-test environment intentionally installs only pytest, while
# Home Assistant supplies aiohttp at runtime. Stub just the imported types so
# the pure request-building helpers remain testable without adding HA's stack.
if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")
    aiohttp_stub.ClientError = type("ClientError", (Exception,), {})
    aiohttp_stub.ClientSession = type("ClientSession", (), {})
    sys.modules["aiohttp"] = aiohttp_stub

spec = importlib.util.spec_from_file_location(
    "linksys_jnap_under_test",
    INTEGRATION / "linksys_jnap.py",
)
assert spec is not None and spec.loader is not None
linksys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linksys)


def test_channel_alternation_is_limited_to_six_and_eleven() -> None:
    assert linksys.alternate_channel(6) == 11
    assert linksys.alternate_channel(11) == 6
    with pytest.raises(linksys.LinksysJnapError):
        linksys.alternate_channel(1)


def test_set_payload_preserves_radio_settings_and_changes_only_channel() -> None:
    output = {
        "isBandSteeringEnabled": False,
        "bandSteeringMode": "Basic",
    }
    radio = {
        "radioID": "RADIO_2.4GHz",
        "supportedChannels": [1, 6, 11],
        "settings": {
            "isEnabled": True,
            "mode": "802.11bgnax",
            "ssid": "split-network",
            "broadcastSSID": True,
            "channelWidth": "20MHz",
            "channel": 6,
            "security": "WPA2-Personal",
            "wpaPersonalSettings": {"passphrase": "kept-in-memory"},
            "readOnlyField": "not-sent",
        },
    }
    request = linksys.build_set_radio_request(output, radio, 11)
    settings = request["radios"][0]["settings"]
    assert settings["channel"] == 11
    assert settings["ssid"] == "split-network"
    assert settings["wpaPersonalSettings"]["passphrase"] == "kept-in-memory"
    assert "readOnlyField" not in settings
    assert request["isBandSteeringEnabled"] is False
    assert radio["settings"]["channel"] == 6


def test_wifi_recovery_is_opt_in_unavailability_triggered_and_cooled_down() -> None:
    coordinator = (INTEGRATION / "coordinator.py").read_text()
    controller = (INTEGRATION / "wifi_recovery.py").read_text()
    switch = (INTEGRATION / "switch.py").read_text()
    assert "consecutive_failures <= failure_tolerance" in controller
    assert "_attempted_for_outage" in controller
    assert "WIFI_LOSS_RECOVERY_COOLDOWN_HOURS" in controller
    assert 'self.status = "Grace period"' in controller
    assert "await asyncio.wait_for(self._recovered_event.wait()" in controller
    assert "async_grace_period_changed" in controller
    assert "wifi_loss_recovery_enabled: bool = False" in coordinator
    assert 'data.get("wifi_loss_recovery_enabled", False)' in coordinator
    assert 'data.get("wifi_loss_recovery_grace_period_minutes")' in coordinator
    assert "AeccWifiLossRecoverySwitch" in switch
    assert '_attr_name = "Wi-Fi Loss Recovery"' in switch


def test_wifi_recovery_grace_period_is_a_persisted_number_entity() -> None:
    number = (INTEGRATION / "number.py").read_text()
    constants = (INTEGRATION / "const.py").read_text()
    assert "AeccWifiRecoveryGracePeriod" in number
    assert '_attr_name = "Wi-Fi Recovery Grace Period"' in number
    assert "WIFI_LOSS_RECOVERY_MAX_GRACE_MINUTES = 60" in constants
    assert "async_save_runtime_preferences" in number


def test_card_exposes_status_but_never_router_credentials() -> None:
    card = (
        INTEGRATION / "frontend" / "aferiy-wifi-recovery-card.js"
    ).read_text()
    assert "aferiy-wifi-recovery-card" in card
    assert "_wifi_loss_recovery" in card
    assert "current_2_4ghz_channel" in card
    assert "trigger_after_consecutive_failures" in card
    assert "_wifi_recovery_grace_period" in card
    assert '"number", "set_value"' in card
    assert "grace_period_ends_at" in card
    assert "this._findGraceNumber(recovery)" in card
    assert "password" not in card.lower()
