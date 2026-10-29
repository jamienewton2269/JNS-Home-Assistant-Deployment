"""Advisory-only VM905 bathroom precision learner; leaves Honeywell in control.

Requires sibling bathroom_reference.py and thermal.py, introduced only by an
approved custom-integration release. Independent persisted learning Store.
"""
from __future__ import annotations

from math import isfinite
from homeassistant.helpers.storage import Store
from .bathroom_reference import BATH_TEMP, BATH_RH, REFERENCE, BathroomLearningGate
from .thermal import ZoneLearner

EPOCH = "bathroom-precision-v1"


class BathroomAdvisory:
    def __init__(self, hass, entry):
        self.hass = hass
        self.store = Store(hass, 1, f"jns_heating_bathroom_zone_{entry.entry_id}")
        self.gate = BathroomLearningGate()
        self.learner = ZoneLearner()
        self.status = {"eligible": False, "state": "warming_up",
                       "reason": "Waiting for live bathroom measurements",
                       "source": BATH_TEMP, "source_epoch": EPOCH,
                       "temperature": None, "projected": None,
                       "advisory_only": True}

    async def async_setup(self):
        saved = await self.store.async_load() or {}
        # Do not read/write or migrate the existing whole-house learning Store.
        if saved.get("source_epoch") == EPOCH and isinstance(saved.get("samples"), list):
            self.learner = ZoneLearner(saved["samples"])

    def _sample(self, entity):
        state = self.hass.states.get(entity)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            val = float(state.state)
        except (ValueError, TypeError):
            return None
        if not isfinite(val):
            return None
        # last_reported advances on repeated state reports when supported.
        observed = getattr(state, "last_reported", None)
        if observed is None:
            observed = getattr(state, "last_updated", None)
        if observed is None:
            return None
        return val, observed

    async def update(self, *, now, indoor, outdoor, duty, forecast):
        temp = self._sample(BATH_TEMP)
        humid = self._sample(BATH_RH)
        expected = self._sample(REFERENCE)
        reason = "No fresh representative bathroom measurement"
        eligible = False
        temperature = None
        projected = None
        if temp is not None and humid is not None and expected is not None:
            observed = min(temp[1], humid[1])
            decision = self.gate.ingest(
                now=now, observed_at=observed,
                temperature=temp[0], humidity=humid[0],
                honeywell_temperature=expected[0])
            reason = decision.reason
            if decision.temperature_c is not None and outdoor is not None:
                self.learner.add(now, decision.temperature_c, outdoor, duty)
                temperature = decision.temperature_c
                eligible = True
                # Keep the provisional forecast entirely separate from the
                # legacy house-wide forecast entity.
                projected = self.learner.project(now, forecast, duty)
                self.store.async_delay_save(lambda: {
                    "source_epoch": EPOCH, "samples": self.learner.dump()}, 30)
        result = self.learner.status()
        if result.get("ready") is False and eligible:
            reason = reason + "; " + result.get("reason", "model not validated")
        self.status = {
            "eligible": eligible, "state": "eligible" if eligible else "excluded",
            "reason": reason, "source": BATH_TEMP, "source_epoch": EPOCH,
            "temperature": temperature, "projected": projected,
            "advisory_only": True, "learned": result,
            "humidity_entity": BATH_RH,
            "thermostat_unchanged": True}
        return self.status

    async def async_shutdown(self):
        await self.store.async_save({
            "source_epoch": EPOCH, "samples": self.learner.dump()})
