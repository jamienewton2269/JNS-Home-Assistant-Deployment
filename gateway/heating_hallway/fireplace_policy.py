"""Policy-only JNS hallway/fireplace heat suppression; never sends HA commands.

HA-General Honeywell remains the only heating actuator. Caller must supply
independent, quality-checked, *fresh* hallway and fireplace temperatures,
a hallway-source-epoch forecast, and current outdoor/weather forecast health.
"""
from dataclasses import dataclass

HALLWAY_MIN_C = 19.0
HALLWAY_PROJECTED_MIN_C = 18.5
FIREPLACE_MIN_C = 23.0
FIREPLACE_DELTA_C = 2.0
MAX_AGE_SECONDS = 1800


@dataclass(frozen=True)
class Inputs:
    hallway_c: float | None
    fireplace_c: float | None
    hallway_age_seconds: float | None
    fireplace_age_seconds: float | None
    # Sustained thermal differential is latched by a 15-min HA delay_on,
    # 30-min delay_off. This bool must *not* be a single instantaneous spike.
    fireplace_sustained: bool
    projected_hallway_60m_c: float | None
    prediction_validated: bool
    prediction_source_epoch: str
    weather_forecast_fresh: bool
    scheduled_target_c: float
    alarm_state: str
    manual_override: bool
    override_enabled: bool


@dataclass(frozen=True)
class Decision:
    target_c: float
    suppress_heating: bool
    reason: str


def decide(i: Inputs) -> Decision:
    """Return planned setpoint. Fail closed to the *existing* schedule.

    This is not direct boiler control. The Lyric's own room sensor may still
    prevent a heat call; full hallway-based actuation needs independent tests.
    """
    normal = Decision(i.scheduled_target_c, False, "original schedule preserved")
    if i.manual_override or not i.override_enabled:
        return Decision(normal.target_c, False, "manual/suppression disabled")
    if i.alarm_state != "disarmed":
        # Armed-home, armed-away and unknown cannot be overridden here.
        return Decision(normal.target_c, False, "alarm policy retains priority")
    if not i.fireplace_sustained:
        return Decision(normal.target_c, False, "no sustained fire evidence")
    for value, age in ((i.hallway_c, i.hallway_age_seconds),
                       (i.fireplace_c, i.fireplace_age_seconds)):
        if value is None or age is None or not (0 <= age <= MAX_AGE_SECONDS):
            return Decision(normal.target_c, False, "temperature missing/stale")
        if not (0 <= value <= 45):
            return Decision(normal.target_c, False, "implausible temperature")
    if i.fireplace_c < FIREPLACE_MIN_C or i.fireplace_c - i.hallway_c < FIREPLACE_DELTA_C:
        return Decision(normal.target_c, False, "fireplace differential insufficient")
    if i.hallway_c < HALLWAY_MIN_C:
        return Decision(normal.target_c, False, "hallway below minimum")
    if not (i.prediction_validated and i.prediction_source_epoch == "hallway-precision-v1"
            and i.weather_forecast_fresh):
        return Decision(normal.target_c, False, "hallway forecast or weather unvalidated")
    prediction = i.projected_hallway_60m_c
    if prediction is None or not (0 <= prediction <= 45):
        return Decision(normal.target_c, False, "hallway 60-min projection unavailable")
    if prediction < HALLWAY_PROJECTED_MIN_C:
        return Decision(normal.target_c, False, "cold hallway predicted; heating retained")
    # Never exceed scheduled target; 18 is setback, not irreversible heat disable.
    return Decision(min(i.scheduled_target_c, 18.0), True,
                    "sustained fireplace heat; hallway and weather forecast safe")


def testing_status(i: Inputs) -> dict:
    d = decide(i)
    return {"fireplace_override_active": d.suppress_heating,
            "setpoint_c": d.target_c,
            "protection_hallway_min_c": HALLWAY_MIN_C,
            "projection_horizon_minutes": 60,
            "source_epoch_required": "hallway-precision-v1",
            "reason": d.reason}
