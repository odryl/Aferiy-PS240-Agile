"""Minimal Linksys JNAP client used by guarded Wi-Fi loss recovery."""

from __future__ import annotations

import asyncio
import base64
import copy
from typing import Any

from aiohttp import ClientError, ClientSession

GET_DEVICE_INFO = "http://cisco.com/jnap/core/GetDeviceInfo"
GET_RADIO_INFO = "http://cisco.com/jnap/wirelessap/GetRadioInfo3"
SET_RADIO_SETTINGS = "http://cisco.com/jnap/wirelessap/SetRadioSettings3"

_WRITABLE_RADIO_SETTINGS = {
    "broadcastSSID",
    "channel",
    "channelWidth",
    "isEnabled",
    "mode",
    "security",
    "ssid",
    "wpaPersonalSettings",
    "wpa2PersonalSettings",
    "wpa3PersonalSettings",
}


class LinksysJnapError(RuntimeError):
    """Raised when a Linksys JNAP request cannot be completed safely."""


class LinksysJnapAuthenticationError(LinksysJnapError):
    """Raised when the local router administrator password is rejected."""


def is_24ghz_radio(radio: dict[str, Any]) -> bool:
    """Identify a 2.4 GHz radio across Linksys firmware variants."""
    label = " ".join(
        str(radio.get(key, "")) for key in ("band", "radioID", "name")
    ).lower()
    compact = label.replace(" ", "")
    return any(marker in compact for marker in ("2.4ghz", "2.4g", "2ghz"))


def alternate_channel(current: int, allowed: tuple[int, int] = (6, 11)) -> int:
    """Return the other guarded channel, rejecting unexpected starting state."""
    if current == allowed[0]:
        return allowed[1]
    if current == allowed[1]:
        return allowed[0]
    raise LinksysJnapError(
        f"The current 2.4 GHz channel is {current}, not {allowed[0]} or {allowed[1]}"
    )


def build_set_radio_request(
    radio_output: dict[str, Any],
    target_radio: dict[str, Any],
    channel: int,
) -> dict[str, Any]:
    """Copy current writable settings and change only the channel."""
    settings = target_radio.get("settings")
    if not isinstance(settings, dict):
        raise LinksysJnapError("The 2.4 GHz radio has no writable settings object")
    radio_id = target_radio.get("radioID")
    if not radio_id:
        raise LinksysJnapError("The 2.4 GHz radio has no radio ID")

    required = {"isEnabled", "mode", "ssid", "broadcastSSID", "channelWidth"}
    missing = sorted(required - settings.keys())
    if missing:
        raise LinksysJnapError(
            "The router returned an unfamiliar radio schema; missing "
            + ", ".join(missing)
        )

    writable_settings = {
        key: copy.deepcopy(value)
        for key, value in settings.items()
        if key in _WRITABLE_RADIO_SETTINGS
    }
    writable_settings["channel"] = int(channel)
    request: dict[str, Any] = {
        "radios": [{"radioID": radio_id, "settings": writable_settings}]
    }
    for key in ("isBandSteeringEnabled", "bandSteeringMode"):
        if key in radio_output:
            request[key] = copy.deepcopy(radio_output[key])
    return request


class LinksysJnapClient:
    """Call the local JNAP endpoint through Home Assistant's HTTP session."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        password: str,
        *,
        timeout: float = 8.0,
    ) -> None:
        clean_host = host.strip().removeprefix("https://").removeprefix("http://")
        self._session = session
        self._endpoint = f"https://{clean_host.rstrip('/')}/JNAP/"
        self._timeout = timeout
        credentials = base64.b64encode(f"admin:{password}".encode()).decode("ascii")
        self._authorization = f"Basic {credentials}"

    async def _async_call(
        self,
        action: str,
        request_data: dict[str, Any],
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers = {
            "Cache-Control": "no-cache",
            "Content-Type": "application/json; charset=UTF-8",
            "X-JNAP-Action": action,
        }
        if authenticated:
            headers["X-JNAP-Authorization"] = self._authorization
        try:
            async with asyncio.timeout(self._timeout):
                async with self._session.post(
                    self._endpoint,
                    headers=headers,
                    json=request_data,
                    ssl=False,
                ) as response:
                    if response.status != 200:
                        # Never include response bodies: authenticated radio
                        # responses can contain the Wi-Fi passphrase.
                        raise LinksysJnapError(
                            f"Linksys router returned HTTP {response.status}"
                        )
                    result = await response.json(content_type=None)
        except TimeoutError as exc:
            raise LinksysJnapError("Linksys router request timed out") from exc
        except ClientError as exc:
            raise LinksysJnapError(
                f"Could not reach the Linksys router ({type(exc).__name__})"
            ) from exc
        except ValueError as exc:
            raise LinksysJnapError("Linksys router returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise LinksysJnapError("Linksys router returned an invalid response")
        if result.get("result") == "_ErrorUnauthorized":
            raise LinksysJnapAuthenticationError(
                "The local Linksys router administrator password was rejected"
            )
        if result.get("result") != "OK":
            # Result names are safe; omit the rest of the response defensively.
            raise LinksysJnapError(
                f"Linksys JNAP action failed ({result.get('result', 'unknown')})"
            )
        output = result.get("output", {})
        if not isinstance(output, dict):
            raise LinksysJnapError("Linksys router returned invalid action output")
        return output

    async def async_get_device_info(self) -> dict[str, Any]:
        """Return non-authenticated router identity and capabilities."""
        return await self._async_call(GET_DEVICE_INFO, {}, authenticated=False)

    async def async_get_radio_info(self) -> dict[str, Any]:
        """Return authenticated radio information; callers must not log it."""
        return await self._async_call(GET_RADIO_INFO, {})

    async def async_set_24ghz_channel(self, channel: int) -> tuple[int, int]:
        """Change only the 2.4 GHz channel and return (previous, requested)."""
        radio_output = await self.async_get_radio_info()
        radios = radio_output.get("radios")
        if not isinstance(radios, list):
            raise LinksysJnapError("Linksys radio information has no radios list")
        targets = [radio for radio in radios if is_24ghz_radio(radio)]
        if len(targets) != 1:
            raise LinksysJnapError(
                f"Expected one 2.4 GHz radio but found {len(targets)}"
            )
        target = targets[0]
        current = target.get("settings", {}).get("channel")
        if not isinstance(current, int):
            raise LinksysJnapError("The current 2.4 GHz channel is not available")
        if current == channel:
            return current, channel
        request = build_set_radio_request(radio_output, target, channel)
        await self._async_call(SET_RADIO_SETTINGS, request)
        return current, channel

    async def async_current_24ghz_channel(self) -> int:
        """Read the current channel without returning sensitive radio fields."""
        radio_output = await self.async_get_radio_info()
        radios = radio_output.get("radios")
        if not isinstance(radios, list):
            raise LinksysJnapError("Linksys radio information has no radios list")
        targets = [radio for radio in radios if is_24ghz_radio(radio)]
        if len(targets) != 1:
            raise LinksysJnapError(
                f"Expected one 2.4 GHz radio but found {len(targets)}"
            )
        channel = targets[0].get("settings", {}).get("channel")
        if not isinstance(channel, int):
            raise LinksysJnapError("The current 2.4 GHz channel is not available")
        return channel
