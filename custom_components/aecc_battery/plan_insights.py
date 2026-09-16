"""Pure, bounded observation and adaptive-planning helpers (no device writes)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isfinite
from statistics import quantiles
from typing import Any
from zoneinfo import ZoneInfo


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def timestamp(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return result.astimezone(UTC) if result.tzinfo else None


def learned_profile(samples: list[dict[str, Any]], timezone: str, target: datetime) -> tuple[dict[str, float], dict[str, Any]]:
    """Learn gross demand; reject gaps and require three comparable days per bucket."""
    zone = ZoneInfo(timezone)
    days: dict[tuple[str, str], list[float]] = {}
    ordered = sorted((s for s in samples if timestamp(s.get("at"))), key=lambda s: s["at"])
    for previous, following in zip(ordered, ordered[1:]):
        start, end = timestamp(previous["at"]), timestamp(following["at"])
        watts = number(previous.get("watts"))
        if start is None or end is None or watts is None or not 0 <= watts <= 50000 or not 0 < (end - start).total_seconds() <= 900:
            continue
        cursor = start
        while cursor < end:
            boundary = cursor.replace(minute=(cursor.minute // 30) * 30, second=0, microsecond=0) + timedelta(minutes=30)
            stop = min(end, boundary)
            local = cursor.astimezone(zone)
            if local.date() < target.astimezone(zone).date() and (local.weekday() >= 5) == (target.astimezone(zone).weekday() >= 5):
                key = (local.date().isoformat(), local.strftime("%H:%M"))
                total = days.setdefault(key, [0.0, 0.0])
                seconds = (stop - cursor).total_seconds()
                total[0] += watts * seconds / 3600000
                total[1] += seconds
            cursor = stop
    buckets: dict[str, list[float]] = {}
    for (_day, key), (energy, seconds) in days.items():
        if seconds >= 1710:  # At least 95% coverage; normalize DST repeated hours.
            buckets.setdefault(key, []).append(energy * 1800 / seconds)
    profile = {key: round(quantiles(values, n=4, method="inclusive")[2] * 1.10, 4)
               for key, values in buckets.items() if len(values) >= 3}
    ready = len(profile) == 48
    return (profile if ready else {}), {
        "demand_learning_status": "ready" if ready else "warming",
        "demand_learning_complete_buckets": len(profile), "demand_learning_required_buckets": 48,
        "demand_learning_minimum_days": 3, "demand_learning_basis": "weekday_weekend_75th_percentile_plus_10_percent",
    }


def forecast_net_profile(gross: dict[str, float], periods: list[dict[str, Any]], timezone: str, target: datetime) -> tuple[dict[str, float], dict[str, Any]]:
    """Credit half the forecast against gross demand only; never bank export or surplus PV."""
    zone = ZoneInfo(timezone)
    start = datetime.combine(target.astimezone(zone).date(), datetime.min.time(), tzinfo=zone).astimezone(UTC)
    end = (datetime.combine(target.astimezone(zone).date() + timedelta(days=1), datetime.min.time(), tzinfo=zone)).astimezone(UTC)
    parsed = [(timestamp(p.get("start")), timestamp(p.get("end")), number(p.get("kwh"))) for p in periods]
    valid = [(a, b, e) for a, b, e in parsed if a is not None and b is not None and e is not None and 0 <= e <= 100 and 0 < (b-a).total_seconds() <= 3600]
    if len(valid) != len(periods) or not valid:
        return dict(gross), {"solar_planning_status": "invalid_or_missing_forecast", "forecast_credit_kwh": 0.0}
    # Input periods are pre-aggregated across providers and must not overlap.
    valid.sort(key=lambda p: p[0])
    if any(a[1] > b[0] for a, b in zip(valid, valid[1:])):
        return dict(gross), {"solar_planning_status": "overlapping_forecast", "forecast_credit_kwh": 0.0}
    values: dict[str, list[float]] = {}
    credit = 0.0
    cursor = start
    while cursor < end:
        stop = min(end, cursor + timedelta(minutes=30))
        key = cursor.astimezone(zone).strftime("%H:%M")
        solar = sum(e * max(0.0, (min(stop,b)-max(cursor,a)).total_seconds()) / (b-a).total_seconds() for a,b,e in valid)
        used = min(gross.get(key, 0.0), solar * .50)
        credit += used
        values.setdefault(key, []).append(max(0.0, gross.get(key, 0.0) - used))
        cursor = stop
    # Repeated local times share the more conservative demand forecast.
    result = dict(gross)
    result.update({key:max(v) for key,v in values.items()})
    return result, {"solar_planning_status": "forecast_applied", "forecast_credit_kwh": round(credit,3), "forecast_credit_factor": .50}


class OutcomeLedger:
    """Persisted daily observed energy, coverage, and controller/target events."""

    def __init__(self, timezone: str, saved: dict[str, Any] | None = None) -> None:
        self.zone = ZoneInfo(timezone)
        self.days = (saved or {}).get("days", {})
        self.previous: dict[str, Any] | None = None  # Never integrate across a restart.

    def snapshot(self) -> dict[str, Any]:
        return {"days": self.days}

    def observe(self, sample: dict[str, Any]) -> None:
        now = timestamp(sample.get("at"))
        if now is None:
            return
        key = now.astimezone(self.zone).date().isoformat()
        record = self.days.setdefault(key, {"date":key, "tracking_started_at":now.isoformat(), "observed_seconds":0.0,
            "grid_charge_kwh":0.0, "battery_output_kwh":0.0, "priced_charge_kwh":0.0, "charge_cost_gbp":0.0,
            "solar_wait_minutes":0.0, "events":[], "targets":[], "plan_grid_charge_kwh":sample.get("plan_grid_charge_kwh"),
            "plan_captured_at":now.isoformat()})
        previous = self.previous
        self.previous = sample if sample.get("fresh") else None
        if previous:
            then = timestamp(previous.get("at"))
            delta = (now - then).total_seconds() if then else 0
            charge, output = number(previous.get("charge_w")), number(previous.get("output_w"))
            if sample.get("fresh") and 0 < delta <= 60 and charge is not None and output is not None:
                cursor = then
                while cursor < now:
                    midnight = datetime.combine(cursor.astimezone(self.zone).date() + timedelta(days=1), datetime.min.time(), tzinfo=self.zone).astimezone(UTC)
                    boundary = cursor.replace(minute=(cursor.minute//30)*30, second=0,microsecond=0)+timedelta(minutes=30)
                    stop = min(now, midnight, boundary)
                    seconds = (stop-cursor).total_seconds()
                    entry = self.days.get(cursor.astimezone(self.zone).date().isoformat(), record)
                    energy = max(0.0, charge)*seconds/3600000
                    entry["grid_charge_kwh"] += energy
                    entry["battery_output_kwh"] += max(0.0, output)*seconds/3600000
                    entry["observed_seconds"] += seconds
                    price = next((number(p.get("rate_gbp_per_kwh")) for p in sample.get("rates", []) if timestamp(p.get("start")) and timestamp(p.get("end")) and timestamp(p["start"]) <= cursor < timestamp(p["end"])), None)
                    if price is not None:
                        entry["priced_charge_kwh"] += energy
                        entry["charge_cost_gbp"] += energy * price
                    if previous.get("decision") == "Cosy Solar Wait":
                        entry["solar_wait_minutes"] += seconds/60
                    cursor = stop
                deadline = timestamp(previous.get("target_end"))
                target = number(previous.get("target_soc"))
                soc = number(sample.get("soc"))
                if deadline and then < deadline <= now and target is not None and soc is not None:
                    target_day = (deadline-timedelta(microseconds=1)).astimezone(self.zone).date().isoformat()
                    target_record = self.days.get(target_day, record)
                    if not any(t["at"] == deadline.isoformat() for t in target_record["targets"]):
                        target_record["targets"].append({"at":deadline.isoformat(),"target_soc":target,"observed_soc":soc,"achieved":soc >= target-.5})
        signature = f'{sample.get("control", "Unavailable")} · {sample.get("reason", "")}'
        if not record["events"] or record["events"][-1]["state"] != signature:
            record["events"].append({"at":now.isoformat(),"state":signature})
            record["events"] = record["events"][-12:]
        for old in sorted(self.days)[:-14]:
            del self.days[old]
