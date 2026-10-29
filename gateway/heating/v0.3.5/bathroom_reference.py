"""JNS Heating provisional bathroom thermal reference (advisory, no heater writes).

The bathroom sensor is fine-grained, but a shower can make it a terrible
reference for whole-house heating. This filter only emits a learning input
after stable, bounded, humidity-screened observations. Other outputs are
explicitly unavailable, not interpolated or fabricated. No Home Assistant
imports or file writes; coordinator integration requires a separate guarded
release and a new learning Store / sensor-source epoch.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

BATH_TEMP = "sensor.0xa4c1382471d2ed23_temperature"
BATH_RH = "sensor.0xa4c1382471d2ed23_humidity"
REFERENCE = "sensor.thermostat_thermostat_indoor_temperature"

@dataclass(frozen=True)
class ProvisionalReading:
    temperature_c: float | None
    status: str
    reason: str
    epoch: str = "bathroom-precision-v1"
    advisory_only: bool = True

class BathroomLearningGate:
    """Live-only, deliberately conservative candidate for future VM905 integration.

    Ingest fresh reports with the true Zigbee/HA observed_at timestamp. Calling
    ingest every five minutes using an old retained state MUST NOT qualify it.
    """

    MIN_STABLE = 3
    MIN_STABLE_SPAN = timedelta(minutes=10)
    QUARANTINE = timedelta(minutes=30)
    MAX_AGE = timedelta(minutes=15)
    MAX_GAP = timedelta(minutes=20)
    MAX_TEMP = 27.0
    MAX_THERMOSTAT_DELTA = 2.0
    MAX_FAST_TEMP_RISE = 0.65    # degrees over 10 minutes
    MAX_FAST_HUMIDITY_RISE = 8.0 # %RH over 15 minutes
    MAX_ABS_HUMIDITY = 75.0

    def __init__(self):
        self.previous = None
        self.stable_since = None
        self.stable_count = 0
        self.quarantine_until = None

    def _block(self, now, reason, quarantine=False):
        self.stable_count = 0
        self.stable_since = None
        if quarantine:
            end = now + self.QUARANTINE
            if self.quarantine_until is None or self.quarantine_until < end:
                self.quarantine_until = end
        return ProvisionalReading(None, "excluded", reason)

    def ingest(self, *, now: datetime, observed_at: datetime, temperature: float,
               humidity: float, honeywell_temperature: float):
        if now.tzinfo is None or observed_at.tzinfo is None:
            return self._block(now, "timezone missing")
        if not all(isinstance(x, (float, int)) and isfinite(x) for x in
                   (temperature, humidity, honeywell_temperature)):
            return self._block(now, "missing/nonfinite measurement", quarantine=True)
        age = now - observed_at
        if not timedelta(0) <= age <= self.MAX_AGE:
            return self._block(now, "Zigbee observation stale or in future")
        if not (5 <= humidity <= 100 and -10 <= honeywell_temperature <= 40):
            return self._block(now, "humidity or house reference invalid", quarantine=True)
        if not (0 <= temperature <= self.MAX_TEMP):
            return self._block(now, "bathroom measurement out of room range", quarantine=True)
        if abs(temperature-honeywell_temperature) > self.MAX_THERMOSTAT_DELTA:
            return self._block(now, "bathroom differs substantially from house", quarantine=True)

        if self.previous is not None:
            previous_t, previous_temp, previous_rh = self.previous
            dt = observed_at - previous_t
            if dt <= timedelta(0):
                return ProvisionalReading(None, "excluded", "observation not newer")
            if dt > self.MAX_GAP:
                self.stable_since = None
                self.stable_count = 0
            if dt <= timedelta(minutes=10) and temperature-previous_temp >= self.MAX_FAST_TEMP_RISE:
                self.previous = (observed_at, temperature, humidity)
                return self._block(now, "shower-like rapid temperature rise", quarantine=True)
            if dt <= timedelta(minutes=15) and humidity-previous_rh >= self.MAX_FAST_HUMIDITY_RISE:
                self.previous = (observed_at, temperature, humidity)
                return self._block(now, "shower-like humidity rise", quarantine=True)

        self.previous = (observed_at, temperature, humidity)
        if humidity >= self.MAX_ABS_HUMIDITY:
            return self._block(now, "bathroom humidity high", quarantine=True)
        if self.quarantine_until is not None:
            if now < self.quarantine_until:
                return self._block(now, "shower recovery quarantine")
            self.quarantine_until = None
        if self.stable_since is None:
            self.stable_since = observed_at
        self.stable_count += 1
        if self.stable_count < self.MIN_STABLE or observed_at-self.stable_since < self.MIN_STABLE_SPAN:
            return ProvisionalReading(None, "warming_up", "awaiting stable precision readings")
        return ProvisionalReading(float(temperature), "eligible",
            "quality-gated bathroom observation; not direct whole-house control")
