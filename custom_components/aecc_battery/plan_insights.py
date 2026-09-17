"""Pure, bounded observation and adaptive-planning helpers (no device writes)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise
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
        result = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return result.astimezone(UTC) if result.tzinfo else None


def learned_profile(
    samples: list[dict[str, Any]], timezone: str, target: datetime
) -> tuple[dict[str, float], dict[str, Any]]:
    """Learn gross demand; reject gaps and require three comparable days per bucket."""
    zone = ZoneInfo(timezone)
    days: dict[tuple[str, str], list[float]] = {}
    ordered = sorted((s for s in samples if timestamp(s.get("at"))), key=lambda s: s["at"])
    for previous, following in pairwise(ordered):
        start, end = timestamp(previous["at"]), timestamp(following["at"])
        watts = number(previous.get("watts"))
        if (
            start is None
            or end is None
            or watts is None
            or not 0 <= watts <= 50000
            or not 0 < (end - start).total_seconds() <= 900
        ):
            continue
        cursor = start
        while cursor < end:
            boundary = cursor.replace(minute=(cursor.minute // 30) * 30, second=0, microsecond=0) + timedelta(
                minutes=30
            )
            stop = min(end, boundary)
            local = cursor.astimezone(zone)
            if local.date() < target.astimezone(zone).date() and (local.weekday() >= 5) == (
                target.astimezone(zone).weekday() >= 5
            ):
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
    profile = {
        key: round(quantiles(values, n=4, method="inclusive")[2] * 1.10, 4)
        for key, values in buckets.items()
        if len(values) >= 3
    }
    ready = len(profile) == 48
    return (profile if ready else {}), {
        "demand_learning_status": "ready" if ready else "warming",
        "demand_learning_complete_buckets": len(profile),
        "demand_learning_required_buckets": 48,
        "demand_learning_minimum_days": 3,
        "demand_learning_basis": "weekday_weekend_75th_percentile_plus_10_percent",
    }


def forecast_net_profile(
    gross: dict[str, float], periods: list[dict[str, Any]], timezone: str, target: datetime
) -> tuple[dict[str, float], dict[str, Any]]:
    """Credit half the forecast against gross demand only; never bank export or surplus PV."""
    zone = ZoneInfo(timezone)
    start = datetime.combine(target.astimezone(zone).date(), datetime.min.time(), tzinfo=zone).astimezone(UTC)
    end = (
        datetime.combine(target.astimezone(zone).date() + timedelta(days=1), datetime.min.time(), tzinfo=zone)
    ).astimezone(UTC)
    parsed = [(timestamp(p.get("start")), timestamp(p.get("end")), number(p.get("kwh"))) for p in periods]
    valid = [
        (a, b, e)
        for a, b, e in parsed
        if a is not None and b is not None and e is not None and 0 <= e <= 100 and 0 < (b - a).total_seconds() <= 3600
    ]
    if len(valid) != len(periods) or not valid:
        return dict(gross), {"solar_planning_status": "invalid_or_missing_forecast", "forecast_credit_kwh": 0.0}
    # Input periods are pre-aggregated across providers and must not overlap.
    valid.sort(key=lambda p: p[0])
    if any(a[1] > b[0] for a, b in pairwise(valid)):
        return dict(gross), {"solar_planning_status": "overlapping_forecast", "forecast_credit_kwh": 0.0}
    values: dict[str, list[float]] = {}
    credit = 0.0
    cursor = start
    while cursor < end:
        stop = min(end, cursor + timedelta(minutes=30))
        key = cursor.astimezone(zone).strftime("%H:%M")
        solar = sum(
            e * max(0.0, (min(stop, b) - max(cursor, a)).total_seconds()) / (b - a).total_seconds() for a, b, e in valid
        )
        used = min(gross.get(key, 0.0), solar * 0.50)
        credit += used
        values.setdefault(key, []).append(max(0.0, gross.get(key, 0.0) - used))
        cursor = stop
    # Repeated local times share the more conservative demand forecast.
    result = dict(gross)
    result.update({key: max(v) for key, v in values.items()})
    return result, {
        "solar_planning_status": "forecast_applied",
        "forecast_credit_kwh": round(credit, 3),
        "forecast_credit_factor": 0.50,
    }


class OutcomeLedger:
    """Bounded daily observations, frozen plans and explicit telemetry coverage."""

    def __init__(self, timezone: str, saved: dict[str, Any] | None = None) -> None:
        self.zone = ZoneInfo(timezone)
        raw = (saved or {}).get("days", {})
        self.days = (
            {key: value for key, value in raw.items() if isinstance(value, dict) and value.get("schema") == 2}
            if isinstance(raw, dict)
            else {}
        )
        self.previous: dict[str, Any] | None = None  # Never integrate across restart.

    def snapshot(self) -> dict[str, Any]:
        from copy import deepcopy

        return {"days": deepcopy(self.days)}

    def _day(self, now: datetime) -> dict[str, Any]:
        key = now.astimezone(self.zone).date().isoformat()
        return self.days.setdefault(
            key,
            {
                "schema": 2,
                "date": key,
                "tracking_started_at": now.isoformat(),
                "observed_seconds": 0.0,
                "grid_observed_seconds": 0.0,
                "ac_charge_kwh": 0.0,
                "grid_charge_kwh": 0.0,
                "battery_output_kwh": 0.0,
                "priced_charge_kwh": 0.0,
                "charge_cost_gbp": 0.0,
                "happy_hour_credit_gbp": 0.0,
                "solar_wait_minutes": 0.0,
                "interruptions": 0,
                "events": [],
                "targets": [],
                "plan_grid_charge_kwh": None,
                "plan_captured_at": None,
                "ac_at_plan_capture_kwh": 0.0,
            },
        )

    def observe(self, sample: dict[str, Any]) -> None:
        now = timestamp(sample.get("at"))
        if now is None:
            return
        record = self._day(now)
        previous = self.previous
        then = timestamp(previous.get("at")) if previous else None
        if then is not None and now <= then:
            return
        seconds = (now - then).total_seconds() if then else 0
        continuous = bool(previous and sample.get("fresh") and previous.get("fresh") and 0 < seconds <= 90)
        if continuous:
            charge, output = number(previous.get("charge_w")), number(previous.get("output_w"))
            grid = number(previous.get("grid_w"))
            if charge is not None and output is not None and 0 <= charge <= 10000 and 0 <= output <= 10000:
                cursor = then
                while cursor < now:
                    midnight = datetime.combine(
                        cursor.astimezone(self.zone).date() + timedelta(days=1), datetime.min.time(), tzinfo=self.zone
                    ).astimezone(UTC)
                    boundary = cursor.replace(minute=(cursor.minute // 30) * 30, second=0, microsecond=0) + timedelta(
                        minutes=30
                    )
                    stop = min(now, midnight, boundary)
                    duration = (stop - cursor).total_seconds()
                    entry = self._day(cursor)
                    entry["observed_seconds"] += duration
                    entry["ac_charge_kwh"] += charge * duration / 3600000
                    entry["battery_output_kwh"] += output * duration / 3600000
                    # AC charging may be supplied by another inverter's solar.
                    # Attribute at most the simultaneous measured site import.
                    if grid is not None:
                        energy = min(charge, max(0.0, grid)) * duration / 3600000
                        entry["grid_observed_seconds"] += duration
                        entry["grid_charge_kwh"] += energy
                        rate = next(
                            (
                                p
                                for p in previous.get("rates", []) + sample.get("rates", [])
                                if timestamp(p.get("start"))
                                and timestamp(p.get("end"))
                                and timestamp(p["start"]) <= cursor < timestamp(p["end"])
                            ),
                            None,
                        )
                        price = number(rate.get("rate_gbp_per_kwh")) if rate else None
                        if price is not None:
                            entry["priced_charge_kwh"] += energy
                            if rate.get("tariff_phase") == "free_energy":
                                entry["happy_hour_credit_gbp"] += energy * price
                            else:
                                entry["charge_cost_gbp"] += energy * price
                    if previous.get("solar_wait_active"):
                        entry["solar_wait_minutes"] += duration / 60
                    cursor = stop
        # Freeze the first valid plan observed that day; later replans must not
        # rewrite the comparison. Only the remainder after capture is comparable.
        planned = number(sample.get("plan_grid_charge_kwh"))
        if record["plan_captured_at"] is None and sample.get("fresh") and planned is not None:
            record.update(
                plan_captured_at=now.isoformat(),
                plan_grid_charge_kwh=planned,
                ac_at_plan_capture_kwh=record["ac_charge_kwh"],
            )
        for item in sample.get("targets", []):
            deadline, target = timestamp(item.get("at")), number(item.get("target_soc"))
            if deadline is None or deadline <= now or target is None or not 0 <= target <= 100:
                continue
            target_record = self._day(deadline - timedelta(microseconds=1))
            existing = next((t for t in target_record["targets"] if t["at"] == deadline.isoformat()), None)
            if existing is None:
                target_record["targets"].append({"at": deadline.isoformat(), "target_soc": target, "result": "pending"})
            elif existing["result"] == "pending":
                existing["target_soc"] = target
        soc = number(sample.get("soc"))
        for day in self.days.values():
            for target in day["targets"]:
                deadline = timestamp(target["at"])
                if target["result"] != "pending" or deadline is None or deadline > now:
                    continue
                known = continuous and then <= deadline and soc is not None and 0 <= soc <= 100
                target.update(
                    result=("achieved" if soc >= target["target_soc"] - 0.5 else "missed") if known else "unknown",
                    observed_soc=soc if known else None,
                    observed_at=now.isoformat() if known else None,
                    automation_on=bool(sample.get("enabled")),
                )
        status = str(sample.get("control") or "Unavailable")
        signature = [status, bool(sample.get("enabled")), bool(sample.get("fresh")), sample.get("mode")]
        if not record["events"] or record["events"][-1].get("signature") != signature:
            interrupted = status in ("Inhibited", "Fail-safe", "Restore pending") or not sample.get("fresh")
            record["events"].append(
                {
                    "at": now.isoformat(),
                    "state": status,
                    "reason": str(sample.get("reason") or "")[:400],
                    "signature": signature,
                    "interruption": interrupted,
                }
            )
            record["events"] = record["events"][-24:]
            record["interruptions"] += int(interrupted)
        record["last_observed_at"] = now.isoformat()
        self.previous = dict(sample) if sample.get("fresh") else None
        for old in sorted(self.days)[:-14]:
            del self.days[old]

    def summary(self, now: datetime | None = None) -> list[dict[str, Any]]:
        result = []
        now = now or max(
            (timestamp(d.get("last_observed_at")) or datetime.min.replace(tzinfo=UTC) for d in self.days.values()),
            default=datetime.now(UTC),
        )
        for day in sorted(self.days.values(), key=lambda d: d["date"], reverse=True):
            start = datetime.combine(
                datetime.fromisoformat(day["date"]).date(), datetime.min.time(), tzinfo=self.zone
            ).astimezone(UTC)
            end = datetime.combine(
                start.astimezone(self.zone).date() + timedelta(days=1), datetime.min.time(), tzinfo=self.zone
            ).astimezone(UTC)
            elapsed = max(0.0, (min(end, now) - start).total_seconds())
            result.append(
                {
                    **day,
                    "coverage_percent": round(min(100.0, day["observed_seconds"] / elapsed * 100), 1)
                    if elapsed
                    else 0.0,
                    "ac_since_plan_kwh": max(0.0, day["ac_charge_kwh"] - day["ac_at_plan_capture_kwh"]),
                }
            )
        return result
