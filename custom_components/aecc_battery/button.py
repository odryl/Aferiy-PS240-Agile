"""Button platform for AECC datalogger actions."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
    async_add_entities([AeccRestartDataloggerButton(coordinator, config_entry)])


class AeccRestartDataloggerButton(
    CoordinatorEntity[AeccBatteryCoordinator], ButtonEntity
):
    """Restart the Wi-Fi/BLE datalogger immediately over local TCP."""

    _attr_has_entity_name = True
    _attr_name = "Restart Data Logger"
    _attr_icon = "mdi:restart-alert"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AeccBatteryCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}_restart_datalogger"

    @property
    def device_info(self) -> DeviceInfo:
        return self.coordinator.device_info

    @property
    def available(self) -> bool:
        # Allow a recovery attempt even when recent telemetry is unavailable.
        return True

    async def async_press(self) -> None:
        if not await self.coordinator.async_restart_datalogger(reason="manual"):
            raise HomeAssistantError(
                "The data logger restart command could not be sent over local Wi-Fi"
            )
