"""Provider-neutral solar timing context; forecasts never reduce battery targets."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any


def forecast_entries(preferences: Mapping[str, Any]) -> list[str]:
    """Deduplicate the providers explicitly selected in the Energy Dashboard."""
    entries = set()
    for source in preferences.get("energy_sources", []):
        if not isinstance(source, Mapping) or source.get("type") != "solar":
            continue
        configured = source.get("config_entry_solar_forecast") or []
        if isinstance(configured, str):
            configured = [configured]
        entries.update(value for value in configured if isinstance(value, str) and value)
    return sorted(entries)


def normalize_forecasts(payloads: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """Normalize HA Energy wh_hours buckets (Wh per local clock hour) to UTC kWh.

    Energy's frontend floors timestamps to the hour before summing them. Preserve
    missing hours as missing, and sum distinct configured installations only.
    """
    totals: dict[datetime, float] = {}
    for payload in payloads.values():
        hours = payload.get("wh_hours") if isinstance(payload, Mapping) else None
        if not isinstance(hours, Mapping) or not hours or len(hours) > 1000:
            return {"status": "invalid_forecast", "periods": []}
        for raw_time, value in hours.items():
            try:
                moment = datetime.fromisoformat(str(raw_time))
                wh = float(value)
                if moment.tzinfo is None or not isfinite(wh) or not 0 <= wh <= 100000:
                    raise ValueError
            except (ValueError, TypeError, OverflowError):
                return {"status": "invalid_forecast", "periods": []}
            start = moment.replace(minute=0, second=0, microsecond=0).astimezone(UTC)
            if now - timedelta(days=1) <= start <= now + timedelta(days=3):
                totals[start] = totals.get(start, 0.0) + wh / 1000
    periods = [
        {"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(), "kwh": round(energy, 6)}
        for start, energy in sorted(totals.items())
    ]
    return {
        "status": "available" if any(datetime.fromisoformat(p["end"]) > now for p in periods) else "no_future_forecast",
        "periods": periods,
        "retrieved_at": now.isoformat(),
        "provider_count": len(payloads),
        "basis": "energy_dashboard_wh_hours",
        "target_credit_kwh": 0.0,
    }
