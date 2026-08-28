"""Guarded Linksys channel recovery after sustained PS240 Wi-Fi loss."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import ClientSession

from .const import (
    WIFI_LOSS_RECOVERY_CHANNELS,
    WIFI_LOSS_RECOVERY_COOLDOWN_HOURS,
    WIFI_LOSS_RECOVERY_VERIFY_SECONDS,
)
from .linksys_jnap import (
    LinksysJnapAuthenticationError,
    LinksysJnapClient,
    LinksysJnapError,
    alternate_channel,
)

_LOGGER = logging.getLogger(__name__)


class WifiLossRecoveryController:
    """Toggle Linksys channel 6/11 once when the battery becomes unavailable."""

    def __init__(
        self,
        coordinator: Any,
        session: ClientSession,
        router_host: str,
        router_password: str,
    ) -> None:
        self.coordinator = coordinator
        self._client = (
            LinksysJnapClient(session, router_host, router_password)
            if router_host.strip() and router_password
            else None
        )
        self._state_callback: Callable[[], None] | None = None
        self._task: asyncio.Task[None] | None = None
        self._outage_active = False
        self._attempted_for_outage = False
        self._outage_started_at: datetime | None = None
        self._grace_period_ends_at: datetime | None = None
        self._recovered_event = asyncio.Event()
        self.status = "Off"
        self.reason = "Wi-Fi loss recovery is off."
        self.router_model: str | None = None
        self.current_channel: int | None = coordinator.wifi_loss_recovery_last_channel
        self.requested_channel: int | None = None
        self.last_result: str | None = None
        self.last_recovered_at: datetime | None = None

    @property
    def configured(self) -> bool:
        return self._client is not None

    @property
    def enabled(self) -> bool:
        return bool(self.coordinator.wifi_loss_recovery_enabled)

    @property
    def cooldown(self) -> timedelta:
        return timedelta(hours=WIFI_LOSS_RECOVERY_COOLDOWN_HOURS)

    @property
    def next_allowed_attempt_at(self) -> datetime | None:
        last_attempt = self.coordinator.wifi_loss_recovery_last_attempt_at
        return last_attempt + self.cooldown if last_attempt is not None else None

    def set_state_callback(self, callback: Callable[[], None] | None) -> None:
        """Register the switch entity's state writer."""
        self._state_callback = callback

    def _notify(self) -> None:
        if self._state_callback is not None:
            self._state_callback()

    def refresh_status(self) -> None:
        """Set an initial state after preferences and entities have loaded."""
        if self.current_channel is None:
            self.current_channel = self.coordinator.wifi_loss_recovery_last_channel
        if not self.configured:
            self.status = "Configuration required"
            self.reason = (
                "Add the Linksys router address and local administrator password "
                "in the integration options."
            )
        elif not self.enabled:
            self.status = "Off"
            self.reason = "Wi-Fi loss recovery is off."
        elif self.status == "Off":
            self.status = "Monitoring"
            self.reason = "Waiting for the PS240 to become unavailable after sustained poll failures."
        self._notify()

    async def async_enable(self) -> None:
        """Validate read-only router access before persisting the opt-in."""
        if self._client is None:
            self.refresh_status()
            raise LinksysJnapError("Linksys router credentials are not configured")
        self.status = "Checking router"
        self.reason = "Validating local Linksys access without changing settings."
        self._notify()
        try:
            await self._async_probe()
        except LinksysJnapAuthenticationError as exc:
            self.status = "Authentication failed"
            self.reason = str(exc)
            self._notify()
            raise
        except LinksysJnapError as exc:
            self.status = "Failed"
            self.reason = str(exc)
            self._notify()
            raise
        self.coordinator.wifi_loss_recovery_enabled = True
        await self.coordinator.async_save_runtime_preferences()
        self.status = "Monitoring"
        self.reason = "Waiting for the PS240 to become unavailable after sustained poll failures."
        self._notify()

    async def async_disable(self) -> None:
        """Disable recovery and cancel work that has not completed."""
        self.coordinator.wifi_loss_recovery_enabled = False
        await self.coordinator.async_save_runtime_preferences()
        task = self._task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._task = None
        self._grace_period_ends_at = None
        self.status = "Off"
        self.reason = "Wi-Fi loss recovery is off."
        self._notify()

    async def _async_probe(self) -> None:
        """Validate the router model and read only the safe channel number."""
        if self._client is None:
            raise LinksysJnapError("Linksys router credentials are not configured")
        device = await self._client.async_get_device_info()
        manufacturer = str(device.get("manufacturer", ""))
        if manufacturer.lower() != "linksys":
            raise LinksysJnapError("The configured router did not identify itself as Linksys")
        services = device.get("services") or []
        if not any("/jnap/wirelessap/WirelessAP4" in str(item) for item in services):
            raise LinksysJnapError("The Linksys router does not advertise WirelessAP4 control")
        self.router_model = str(device.get("modelNumber") or "Linksys")
        self.current_channel = await self._client.async_current_24ghz_channel()
        self.coordinator.wifi_loss_recovery_last_channel = self.current_channel

    def async_poll_failed(self, consecutive_failures: int, failure_tolerance: int) -> None:
        """Schedule one recovery when coordinator unavailability begins."""
        if consecutive_failures <= failure_tolerance:
            return
        if not self._outage_active:
            self._outage_active = True
            self._outage_started_at = datetime.now(UTC)
            self._recovered_event = asyncio.Event()
        if not self.enabled:
            self.status = "Off"
            self.reason = "The PS240 is unavailable, but Wi-Fi loss recovery is off."
            self._notify()
            return
        if not self.configured:
            self.refresh_status()
            return
        if self._attempted_for_outage:
            return
        if self._task is not None and not self._task.done():
            return

        now = datetime.now(UTC)
        next_allowed = self.next_allowed_attempt_at
        if next_allowed is not None and now < next_allowed:
            self._attempted_for_outage = True
            self.status = "Cooldown"
            self.reason = (
                "The PS240 is unavailable, but another router change is blocked "
                f"until {next_allowed.isoformat()}."
            )
            self._notify()
            return

        self._attempted_for_outage = True
        self._task = self.coordinator.hass.async_create_task(
            self._async_wait_then_recover(consecutive_failures)
        )

    def async_poll_recovered(self) -> None:
        """Reset the per-outage guard after valid battery telemetry returns."""
        if not self._outage_active:
            return
        self._recovered_event.set()
        self._outage_active = False
        self._attempted_for_outage = False
        self._outage_started_at = None
        self._grace_period_ends_at = None
        self.last_recovered_at = datetime.now(UTC)
        if self.enabled:
            self.status = "Recovered"
            self.reason = "Valid PS240 battery telemetry has resumed."
        else:
            self.status = "Off"
            self.reason = "Wi-Fi loss recovery is off."
        self._notify()

    async def async_grace_period_changed(self) -> None:
        """Recalculate an active grace wait after the user changes its duration."""
        if not self._outage_active or self.status != "Grace period":
            self._notify()
            return
        task = self._task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._task = None
        self._attempted_for_outage = False
        self.async_poll_failed(
            self.coordinator._consecutive_failures,
            self.coordinator._failure_tolerance,
        )

    async def _async_wait_then_recover(self, consecutive_failures: int) -> None:
        """Wait through the configured grace period, stopping on battery recovery."""
        started_at = self._outage_started_at or datetime.now(UTC)
        grace_minutes = max(
            0, int(self.coordinator.wifi_loss_recovery_grace_period_minutes)
        )
        self._grace_period_ends_at = started_at + timedelta(minutes=grace_minutes)
        remaining = (self._grace_period_ends_at - datetime.now(UTC)).total_seconds()
        if remaining > 0:
            self.status = "Grace period"
            self.reason = (
                "Waiting for the PS240 to recover before changing the router channel. "
                f"Automatic recovery is due at {self._grace_period_ends_at.isoformat()}."
            )
            self._notify()
            try:
                await asyncio.wait_for(self._recovered_event.wait(), timeout=remaining)
                return
            except TimeoutError:
                pass
        if not self._outage_active or not self.enabled:
            return
        self._grace_period_ends_at = None
        await self._async_recover(consecutive_failures)

    async def _async_recover(self, consecutive_failures: int) -> None:
        """Toggle 6/11 once and verify the router-reported channel."""
        if self._client is None:
            return
        self.status = "Changing channel"
        self.reason = (
            f"The PS240 is unavailable after {consecutive_failures} consecutive poll failures."
        )
        self.last_result = None
        self._notify()

        try:
            await self._async_probe()
            current = self.current_channel
            target = alternate_channel(current, WIFI_LOSS_RECOVERY_CHANNELS)
            self.requested_channel = target
            now = datetime.now(UTC)
            self.coordinator.wifi_loss_recovery_last_attempt_at = now
            await self.coordinator.async_save_runtime_preferences()

            write_error: LinksysJnapError | None = None
            try:
                await self._client.async_set_24ghz_channel(target)
            except LinksysJnapAuthenticationError:
                raise
            except LinksysJnapError as exc:
                # The radio can restart before returning the HTTP response.
                # Verification below establishes whether it applied the write.
                write_error = exc

            deadline = asyncio.get_running_loop().time() + WIFI_LOSS_RECOVERY_VERIFY_SECONDS
            while True:
                try:
                    actual = await self._client.async_current_24ghz_channel()
                except LinksysJnapError:
                    actual = None
                if actual == target:
                    self.current_channel = actual
                    self.coordinator.wifi_loss_recovery_last_channel = actual
                    await self.coordinator.async_save_runtime_preferences()
                    self.status = "Waiting for battery"
                    self.reason = (
                        f"Changed Linksys 2.4 GHz channel from {current} to {target}; "
                        "waiting for PS240 telemetry to resume."
                    )
                    self.last_result = "verified"
                    _LOGGER.warning(
                        "Wi-Fi loss recovery changed Linksys 2.4 GHz channel %s -> %s",
                        current,
                        target,
                    )
                    return
                if asyncio.get_running_loop().time() >= deadline:
                    detail = f": {write_error}" if write_error is not None else ""
                    raise LinksysJnapError(
                        f"Channel {target} was not verified within "
                        f"{WIFI_LOSS_RECOVERY_VERIFY_SECONDS} seconds{detail}"
                    )
                await asyncio.sleep(3)
        except LinksysJnapAuthenticationError as exc:
            self.status = "Authentication failed"
            self.reason = str(exc)
            self.last_result = "authentication_failed"
            _LOGGER.error("Wi-Fi loss recovery could not authenticate to the Linksys router")
        except LinksysJnapError as exc:
            self.status = "Failed"
            self.reason = str(exc)
            self.last_result = "failed"
            _LOGGER.error("Wi-Fi loss recovery failed: %s", exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.status = "Failed"
            self.reason = f"Unexpected router-control error ({type(exc).__name__})"
            self.last_result = "failed"
            _LOGGER.exception("Unexpected Wi-Fi loss recovery failure")
        finally:
            self._notify()

    async def async_shutdown(self) -> None:
        """Cancel controller-owned work while unloading the integration."""
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._task = None
        self._state_callback = None

    @property
    def state_attributes(self) -> dict[str, Any]:
        """Return safe entity attributes without router credentials or SSID."""
        last_attempt = self.coordinator.wifi_loss_recovery_last_attempt_at
        next_attempt = self.next_allowed_attempt_at
        return {
            "status": self.status,
            "reason": self.reason,
            "configured": self.configured,
            "router_model": self.router_model,
            "current_2_4ghz_channel": self.current_channel,
            "requested_channel": self.requested_channel,
            "allowed_channels": list(WIFI_LOSS_RECOVERY_CHANNELS),
            "trigger_after_consecutive_failures": self.coordinator._failure_tolerance + 1,
            "current_consecutive_failures": self.coordinator._consecutive_failures,
            "battery_available": self.coordinator.last_update_success,
            "last_attempt_at": last_attempt.isoformat() if last_attempt else None,
            "next_allowed_attempt_at": next_attempt.isoformat() if next_attempt else None,
            "cooldown_hours": WIFI_LOSS_RECOVERY_COOLDOWN_HOURS,
            "grace_period_minutes": int(
                self.coordinator.wifi_loss_recovery_grace_period_minutes
            ),
            "grace_period_ends_at": (
                self._grace_period_ends_at.isoformat()
                if self._grace_period_ends_at is not None
                else None
            ),
            "last_result": self.last_result,
            "last_battery_recovery_at": (
                self.last_recovered_at.isoformat() if self.last_recovered_at else None
            ),
            "policy": "One 6/11 channel toggle per outage after the battery becomes unavailable.",
        }
