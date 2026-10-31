"""Candidate Hallway-only precision thermal learner, NOT installed.

Intended destination:
  /config/custom_components/jns_heating_zones/hallway_runtime.py
Requires a separately validated future v0.3.7 integration coordinator+sensor
change and a new, root-authorized, six-file-or-larger release. It will not
reuse bathroom or quantized Honeywell samples.
"""
from __future__ import annotations

from datetime import timedelta
from math import isfinite
from homeassistant.helpers.storage import Store
from .thermal import ZoneLearner

EPOCH="hallway-precision-v1"
HALLWAY="sensor.jns_hallway_house_temperature"
FIRE="sensor.jns_fireplace_temperature"
FIRE_DETECTED="binary_sensor.jns_fireplace_heat_detected"


class HallwayAdvisory:
    def __init__(self,hass,entry):
        self.hass=hass
        self.store=Store(hass,1,f"jns_heating_hallway_zone_{entry.entry_id}")
        self.learner=ZoneLearner()
        self.last_accepted=None
        self.result={"source_epoch":EPOCH,"validated":False,
                     "weather_forecast_fresh":False,"projected":None,
                     "reason":"Awaiting fresh hallway readings",
                     "source_entity":HALLWAY,"control_outputs":False}

    async def async_setup(self):
        saved=await self.store.async_load() or {}
        if saved.get("source_epoch")==EPOCH and isinstance(saved.get("samples"),list):
            self.learner=ZoneLearner(saved["samples"])

    def _hallway(self,now):
        state=self.hass.states.get(HALLWAY)
        if state is None or state.state in ("unknown","unavailable"):
            return None
        if state.attributes.get("source_epoch")!=EPOCH:
            return None
        try:
            value=float(state.state)
            observed=getattr(state,"last_reported",None) or state.last_updated
            age=(now-observed).total_seconds()
            if not (isfinite(value) and 0<=value<=40 and 0<=age<=1800):
                return None
            return value
        except (ValueError,TypeError,AttributeError,OverflowError):
            return None

    def _fire_influenced(self,now,temperature):
        status=self.hass.states.get(FIRE_DETECTED)
        if status is None or status.state!="off":
            return True # never learn if fire detector is missing/unknown/ON
        fire=self.hass.states.get(FIRE)
        if fire is None or fire.state in ("unknown","unavailable"):
            return True
        try:
            f=float(fire.state)
            observed=getattr(fire,"last_reported",None) or fire.last_updated
            age=(now-observed).total_seconds()
            if not (isfinite(f) and 0<=age<=1800):
                return True
            # Exclude first 15 minutes before delayed fire detection latches.
            return f>=23 and f-temperature>=1.5
        except (ValueError,TypeError,AttributeError,OverflowError):
            return True

    async def update(self,*,now,outdoor,duty,forecast,forecast_at):
        hallway=self._hallway(now)
        fire=self._fire_influenced(now,hallway) if hallway is not None else True
        weather_ok=bool(forecast and forecast_at and
                        timedelta(seconds=0)<=now-forecast_at<=timedelta(minutes=90))
        quality = (hallway is not None and not fire and outdoor is not None
                   and isfinite(outdoor) and -30<=outdoor<=45
                   and duty is not None and isfinite(duty) and 0<=duty<=1)
        if quality:
            # IMPORTANT: do not collect 5-minute duplicate values from an
            # unchanged Zigbee retained report as independent observations.
            source=self.hass.states.get(HALLWAY)
            observed=getattr(source,"last_reported",None) or source.last_updated
            if self.last_accepted is None or observed>self.last_accepted:
                self.learner.add(now,hallway,outdoor,duty)
                self.last_accepted=observed
                self.store.async_delay_save(
                    lambda: {"source_epoch":EPOCH,
                             "samples":self.learner.dump()},30)
        model=self.learner.status()
        ready=bool(quality and weather_ok and model.get("ready"))
        projection=self.learner.project(now,forecast,duty) if ready else None
        if projection is None:ready=False
        self.result={
            "source_epoch":EPOCH,"source_entity":HALLWAY,
            "validated":ready,"weather_forecast_fresh":weather_ok,
            "projected":projection if ready else None,
            "reason":("Validated" if ready else
                      "Fire influence excluded" if fire else
                      "Source or outdoor weather not fresh" if not quality or not weather_ok else
                      model.get("reason","Learning")),
            "learner":model,"control_outputs":False}
        return self.result

    async def async_shutdown(self):
        await self.store.async_save({"source_epoch":EPOCH,
                                    "samples":self.learner.dump()})
