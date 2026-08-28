"""Switch platform for opt-in AECC datalogger automation."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .agile import agile_control_mode_for_state, bounded_agile_command_window
from .const import (
    AGILE_MAX_SYSTEM_CHARGE_POWER_W,
    CONF_AGILE_PLANNER_ENABLED,
    DEFAULT_AGILE_PLANNER_ENABLED,
    DOMAIN,
    MODE_SELF_CONSUMPTION,
    OCTOPUS_AGILE_TARIFF_PRESET,
    OVERNIGHT_CHARGE_MODE_DISABLED,
)
from .coordinator import AeccBatteryCoordinator

_LOGGER = logging.getLogger(__name__)
_AGILE_CONTROLLER_REVISION = 1
_AGILE_CONFIRM_POLLS = 2


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AeccBatteryCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            AeccAutomaticDataloggerRestartSwitch(coordinator, config_entry),
            AeccAgileAutomaticControlSwitch(coordinator, config_entry),
        ]
    )


class AeccAgileAutomaticControlSwitch(
    CoordinatorEntity[AeccBatteryCoordinator], SwitchEntity
):
    """Opt-in executor for the guarded Agile operating-state recommendation."""

    _attr_has_entity_name = True
    _attr_name = "Agile Automated Control"
    _attr_icon = "mdi:battery-sync-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AeccBatteryCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_agile_automatic_control"
        self._enabled = False
        self._owns_control = False
        self._active_mode = "Self-Gen/Zero Export"
        self._active_slot_start: str | None = None
        self._active_slot_end: str | None = None
        self._status = "Off"
        self._reason = "Automatic Agile control is off. Shadow planning remains active."
        self._last_command: str | None = None
        self._last_command_at: datetime | None = None
        self._last_command_result: str | None = None
        self._candidate_key: str | None = None
        self._candidate_confirmations = 0
        self._candidate_poll_at: datetime | None = None
        self._evaluation_task: asyncio.Task[None] | None = None
        self._evaluation_lock = asyncio.Lock()
        self._shutting_down = False

    @property
    def device_info(self) -> DeviceInfo:
        return self.coordinator.device_info

    @property
    def is_on(self) -> bool:
        return self._enabled

    @property
    def available(self) -> bool:
        # It must always be possible to turn automation off and leave a
        # persisted recovery request during an outage.
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "controller_revision": _AGILE_CONTROLLER_REVISION,
            "beta": True,
            "status": self._status,
            "reason": self._reason,
            "active_mode": self._active_mode,
            "active_slot_start": self._active_slot_start,
            "active_slot_end": self._active_slot_end,
            "last_command": self._last_command,
            "last_command_at": (
                self._last_command_at.isoformat() if self._last_command_at else None
            ),
            "last_command_result": self._last_command_result,
            "confirmation_count": self._candidate_confirmations,
            "confirmation_required": _AGILE_CONFIRM_POLLS,
            "pending_self_gen_restore": self.coordinator.agile_control_pending_restore,
            "failsafe_mode": "Self-Gen/Zero Export",
            "command_policy": "Charge, bounded Idle, or CT-controlled Self-Gen only; never fixed Discharge or Feed.",
            "restart_policy": "Control always starts Off; interrupted custom commands restore Self-Gen after reconnect.",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.agile_controller = self
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._async_state_changed)
        )

    async def async_will_remove_from_hass(self) -> None:
        await self.async_shutdown()
        if self.coordinator.agile_controller is self:
            self.coordinator.agile_controller = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        if (
            not self._enabled
            and self._status == "Restore pending"
            and not self.coordinator.agile_control_pending_restore
        ):
            self._status = "Off"
            self._reason = "Interrupted Agile control was restored to Self-Gen after reconnect."
            self._owns_control = False
            self._active_mode = "Self-Gen/Zero Export"
            self._active_slot_start = None
            self._active_slot_end = None
        self._schedule_evaluation()
        super()._handle_coordinator_update()

    def _shadow_entity_id(self) -> str | None:
        return er.async_get(self.hass).async_get_entity_id(
            "sensor",
            DOMAIN,
            f"{self._config_entry.entry_id}_agile_shadow_operating_state",
        )

    @callback
    def _async_state_changed(self, event: Event) -> None:
        if event.data.get("entity_id") == self._shadow_entity_id():
            self._schedule_evaluation()

    @callback
    def _schedule_evaluation(self) -> None:
        if not self._enabled or self._shutting_down:
            return
        if self._evaluation_task is not None and not self._evaluation_task.done():
            return
        self._evaluation_task = self.hass.async_create_task(self._async_evaluate())

    def _interlock_reason(self) -> str | None:
        if not self._config_entry.options.get(
            CONF_AGILE_PLANNER_ENABLED,
            DEFAULT_AGILE_PLANNER_ENABLED,
        ):
            return "The Agile planner is disabled in integration options."
        if self.coordinator.smart_tariff_preset != OCTOPUS_AGILE_TARIFF_PRESET:
            return "The tariff preset is not Octopus Agile."
        if self.coordinator.overnight_charging_mode != OVERNIGHT_CHARGE_MODE_DISABLED:
            return "The fixed-window overnight scheduler must be Off."
        if self.coordinator.storage_topology_incomplete:
            return "The configured battery topology is incomplete."
        if self.coordinator._consecutive_failures:
            return "A fresh failure-free telemetry poll is required."
        last_success = self.coordinator.last_successful_update
        if not self.coordinator.last_update_success or last_success is None:
            return "The battery connection is unavailable."
        update_interval = self.coordinator.update_interval or timedelta(seconds=30)
        stale_after = min(300.0, max(90.0, update_interval.total_seconds() * 3))
        if (datetime.now(UTC) - last_success).total_seconds() > stale_after:
            return "Battery telemetry is stale."
        return None

    def _shadow_decision(self) -> tuple[str | None, dict[str, Any]]:
        entity_id = self._shadow_entity_id()
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None:
            return None, {}
        return state.state, dict(state.attributes)

    def _confirmed(self, mode: str, slot_start: str | None) -> bool:
        key = f"{mode}:{slot_start or 'current'}"
        poll_at = self.coordinator.last_successful_update
        if key != self._candidate_key:
            self._candidate_key = key
            self._candidate_confirmations = 0
            self._candidate_poll_at = None
        if poll_at is not None and poll_at != self._candidate_poll_at:
            self._candidate_confirmations += 1
            self._candidate_poll_at = poll_at
        return self._candidate_confirmations >= _AGILE_CONFIRM_POLLS

    def _clear_confirmation(self) -> None:
        self._candidate_key = None
        self._candidate_confirmations = 0
        self._candidate_poll_at = None

    async def _async_restore_self_gen(self, reason: str) -> bool:
        self._clear_confirmation()
        if not self._owns_control and not self.coordinator.agile_control_pending_restore:
            self._active_mode = "Self-Gen/Zero Export"
            self._active_slot_start = None
            self._active_slot_end = None
            return True
        if self._interlock_reason() in (
            "The battery connection is unavailable.",
            "Battery telemetry is stale.",
            "A fresh failure-free telemetry poll is required.",
        ):
            self._status = "Restore pending"
            self._reason = f"{reason} Self-Gen will be restored after reconnection."
            self._last_command_result = "deferred_until_reconnect"
            return False
        restore_exception: str | None = None
        try:
            success = await self.coordinator.async_restore_self_consumption()
        except Exception as exc:
            _LOGGER.exception("Guarded Agile Self-Gen restore failed unexpectedly")
            success = False
            restore_exception = type(exc).__name__
        self._last_command = "restore_self_gen"
        self._last_command_at = datetime.now(UTC)
        self._last_command_result = (
            f"exception: {restore_exception}"
            if restore_exception is not None
            else "verified" if success else "failed"
        )
        if success:
            self._owns_control = False
            self._active_mode = "Self-Gen/Zero Export"
            self._active_slot_start = None
            self._active_slot_end = None
            await self.coordinator.async_set_agile_control_pending_restore(False)
        else:
            self._status = "Restore pending"
            self._reason = f"{reason} The restore was not confirmed and will be retried."
        return success

    async def _async_apply_mode(
        self,
        mode: str,
        attributes: dict[str, Any],
        state: str,
    ) -> None:
        local_zone = ZoneInfo(self.hass.config.time_zone)
        now_local = datetime.now(UTC).astimezone(local_zone)
        window = bounded_agile_command_window(mode, attributes, now_local)
        if window is None:
            await self._async_restore_self_gen(
                "The recommended custom-command window is missing, unsafe, or almost over."
            )
            self._status = "Inhibited"
            self._reason = "No safe bounded command window is available."
            return
        start, end = window
        slot_key = start.astimezone(UTC).isoformat()
        if self._active_mode == mode and self._active_slot_start == slot_key:
            self._status = "Active"
            self._reason = f"Executing {state} within its bounded half-hour window."
            return
        if not self._confirmed(mode, slot_key):
            self._status = "Confirming"
            self._reason = (
                f"Waiting for {_AGILE_CONFIRM_POLLS} fresh telemetry polls before starting {state}."
            )
            return

        power = 0
        charge_soc: int | None = None
        if mode == "Charge":
            try:
                requested_power = int(attributes.get("planned_slot_power_limit_w") or 0)
            except (TypeError, ValueError):
                requested_power = 0
            power = max(200, min(requested_power, AGILE_MAX_SYSTEM_CHARGE_POWER_W))
            try:
                charge_soc = int(float(attributes.get("target_soc", 100)))
            except (TypeError, ValueError):
                charge_soc = 100

        recovery_armed = await self.coordinator.async_set_agile_control_pending_restore(True)
        if not recovery_armed:
            self._status = "Inhibited"
            self._reason = (
                "The restart-recovery marker could not be persisted; no battery command was sent."
            )
            self._last_command_result = "recovery_marker_failed"
            return
        command_exception: str | None = None
        try:
            success = await self.coordinator.async_set_battery_control(
                mode,
                power,
                charge_soc=charge_soc,
                slot_start=start.strftime("%H:%M"),
                slot_end=end.strftime("%H:%M"),
                operation_prefix="agile_control",
            )
        except Exception as exc:
            _LOGGER.exception("Guarded Agile command failed unexpectedly")
            success = False
            command_exception = type(exc).__name__
        self._last_command = f"{mode.lower()} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
        self._last_command_at = datetime.now(UTC)
        self._last_command_result = (
            f"exception: {command_exception}"
            if command_exception is not None
            else "verified" if success else "failed"
        )
        if not success:
            self._owns_control = True
            await self._async_restore_self_gen("The Agile command was not confirmed.")
            return
        self._owns_control = True
        self._active_mode = mode
        self._active_slot_start = slot_key
        self._active_slot_end = end.astimezone(UTC).isoformat()
        self._status = "Active"
        self._reason = f"Executing {state}; the device command is limited to this slot."

    async def _async_evaluate(self) -> None:
        async with self._evaluation_lock:
            if not self._enabled or self._shutting_down:
                return
            interlock = self._interlock_reason()
            if interlock is not None:
                await self._async_restore_self_gen(f"Control interlock: {interlock}")
                self._status = "Fail-safe"
                self._reason = interlock
                self.async_write_ha_state()
                return

            state, attributes = self._shadow_decision()
            mode = agile_control_mode_for_state(
                state,
                attributes.get("recommended_operating_mode"),
            )
            if mode is None:
                await self._async_restore_self_gen("A validated operating decision is unavailable.")
                self._status = "Fail-safe"
                self._reason = "A validated Agile operating decision is unavailable."
                self.async_write_ha_state()
                return

            if mode == "Self-Gen/Zero Export":
                restored = await self._async_restore_self_gen(
                    f"{state}: {attributes.get('reason', 'safe default selected')}."
                )
                self._status = "Active" if restored else self._status
                if restored:
                    self._reason = f"{state}: {attributes.get('reason', 'Self-Gen selected')}"
            else:
                await self._async_apply_mode(str(mode), attributes, state)
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        async with self._evaluation_lock:
            if self._enabled:
                return
            interlock = self._interlock_reason()
            if interlock is not None:
                self._status = "Inhibited"
                self._reason = interlock
                self.async_write_ha_state()
                return
            current_mode = self.coordinator.commanded_operating_mode
            if (
                current_mode is None
                and self.coordinator.commanded_work_mode != MODE_SELF_CONSUMPTION
            ):
                current_mode = self.coordinator.commanded_direction or "Custom / Manual"
            if current_mode not in (None, "Self-Gen/Zero Export"):
                self._status = "Inhibited"
                self._reason = (
                    f"Operating Mode is {current_mode}; select Self-Gen/Zero Export before enabling Agile control."
                )
                self.async_write_ha_state()
                return
            self._enabled = True
            self.coordinator.agile_control_enabled = True
            self._status = "Armed"
            self._reason = "Waiting for a confirmed guarded Agile decision."
            _LOGGER.warning("Guarded beta Agile automated control enabled")
        await self._async_evaluate()

    async def async_disable(self, reason: str) -> None:
        async with self._evaluation_lock:
            was_enabled = self._enabled
            self._enabled = False
            self.coordinator.agile_control_enabled = False
            await self._async_restore_self_gen(f"Agile control disabled: {reason}.")
            self._status = (
                "Off"
                if not self.coordinator.agile_control_pending_restore
                else "Restore pending"
            )
            if not self.coordinator.agile_control_pending_restore:
                self._reason = f"Automatic Agile control is off: {reason}."
            if was_enabled:
                _LOGGER.warning("Guarded beta Agile automated control disabled: %s", reason)
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_disable("user disabled the toggle")

    async def async_shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        await self.async_disable("integration is unloading")
        task = self._evaluation_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._evaluation_task = None


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
