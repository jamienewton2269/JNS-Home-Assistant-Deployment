"""Pure, advisory fireplace heat classifier. No HA service calls or thermostat writes.

Inputs must be fresh, timestamped, °C samples from independent sensors.
A sensor close to the fireplace is not a substitute for whole-house ambient.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

@dataclass(frozen=True)
class Reading:
    value: float
    at: datetime

@dataclass(frozen=True)
class FireplaceSignal:
    state: str  # likely_on, likely_off, insufficient_data
    delta_c: float | None
    confidence: str
    exclude_from_thermal_learning: bool

def classify(fireplace: Reading | None, house: Reading | None,
             previous_fireplace: Reading | None = None,
             now: datetime | None = None, max_age_minutes: int = 15,
             on_delta_c: float = 2.0, off_delta_c: float = 0.8,
             rising_c_per_10min: float = 0.6) -> FireplaceSignal:
    """Conservative signal only: rising fire-side warmth relative to house.

    One temperature pair can suggest a heat source, not prove combustion.
    Unavailable/stale data deliberately fails safe to unknown.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timezone-aware now required")
    for r in (fireplace, house):
        if r is None or r.at.tzinfo is None or not isfinite(r.value):
            return FireplaceSignal("insufficient_data", None, "none", True)
        age = (now-r.at).total_seconds()/60
        if not 0 <= age <= max_age_minutes or not -10 <= r.value <= 55:
            return FireplaceSignal("insufficient_data", None, "none", True)
    delta = fireplace.value-house.value
    rising = False
    if previous_fireplace and previous_fireplace.at.tzinfo is not None and isfinite(previous_fireplace.value):
        minutes = (fireplace.at-previous_fireplace.at).total_seconds()/60
        if 5 <= minutes <= 30:
            rising = (fireplace.value-previous_fireplace.value)*10/minutes >= rising_c_per_10min
    if delta >= on_delta_c and rising:
        return FireplaceSignal("likely_on", round(delta,2), "medium", True)
    if delta <= off_delta_c and not rising:
        return FireplaceSignal("likely_off", round(delta,2), "low", False)
    return FireplaceSignal("insufficient_data", round(delta,2), "none", True)
