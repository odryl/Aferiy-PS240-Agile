"""Switch platform for opt-in AECC datalogger automation."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AeccBatteryCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AeccBatteryCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([AeccAutomaticDataloggerRestartSwitch(coordinator, config_entry)])


class AeccAutomaticDataloggerRestartSwitch(
    CoordinatorEntity[AeccBatteryCoordinator], SwitchEntity
):
    """Enable a local datalogger restart every three hours."""

    _attr_has_entity_name = True
    _attr_name = "Automatic Data Logger Restart"
    _attr_icon = "mdi:timer-refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AeccBatteryCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}_automatic_datalogger_restart"

    @property
    def device_info(self) -> DeviceInfo:
        return self.coordinator.device_info

    @property
    def is_on(self) -> bool:
        return self.coordinator.auto_datalogger_restart_enabled

    @property
    def available(self) -> bool:
        # Keep the toggle available while the logger is rebooting so the user
        # can always disable future scheduled restarts.
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        next_restart = self.coordinator.next_datalogger_restart_at
        last_restart = self.coordinator.last_datalogger_restart_at
        return {
            "interval_hours": 3,
            "next_restart_at": next_restart.isoformat() if next_restart else None,
            "last_restart_at": last_restart.isoformat() if last_restart else None,
            "last_restart_reason": self.coordinator.last_datalogger_restart_reason,
            "last_restart_dispatched": (
                self.coordinator.last_datalogger_restart_dispatched
            ),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_auto_datalogger_restart_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_auto_datalogger_restart_enabled(False)
        self.async_write_ha_state()
