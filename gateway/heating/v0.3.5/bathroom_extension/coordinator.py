from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import *
from .thermal import ZoneLearner
from .bathroom_runtime import BathroomAdvisory

_LOGGER = logging.getLogger(__name__)
ON_STATES = {"on", "heat", "heating", "fast", "tickover", "true", "1"}


class ZoneCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(hass, _LOGGER, name=entry.title, update_interval=timedelta(minutes=5))
        self.entry = entry
        self.cfg = {**DEFAULTS, **entry.data, **entry.options}
        self.store = Store(hass, 1, f"jns_heating_zone_{entry.entry_id}")
        self.learner = ZoneLearner()
        self.bathroom = BathroomAdvisory(hass, entry)
        self.watch = {"active": False, "stage": 0, "baseline": None, "deadline": None,
                      "fault": False, "manual": False, "result": "Idle"}
        self.reason = "Starting"
        self._forecast = []
        self._forecast_at = None

    async def _async_setup(self):
        saved = await self.store.async_load() or {}
        self.learner = ZoneLearner(saved.get("samples"))
        self.watch.update(saved.get("watch", {}))
        await self.bathroom.async_setup()

    def _number(self, entity_id):
        state = self.hass.states.get(entity_id) if entity_id else None
        try: return float(state.state)
        except (ValueError, TypeError, AttributeError): return None

    def _demand(self):
        source = self.cfg.get(CONF_COMMAND)
        if source:
            state = self.hass.states.get(source)
            return bool(state and state.state.lower() in ON_STATES)
        heater = self.hass.states.get(self.cfg[CONF_HEATER])
        if not heater: return False
        if heater.domain == "climate":
            return heater.attributes.get("hvac_action") == "heating"
        return heater.state == STATE_ON

    def _outdoor(self):
        value = self._number(self.cfg.get(CONF_OUTDOOR))
        if value is not None: return value, "local outdoor sensor"
        weather = self.hass.states.get(self.cfg.get(CONF_WEATHER))
        try: return float(weather.attributes["temperature"]), "weather entity"
        except (ValueError, TypeError, AttributeError, KeyError): return None, "unavailable"

    async def _async_update_data(self):
        now = dt_util.utcnow()
        indoor = self._number(self.cfg[CONF_TEMPERATURE])
        outdoor, outdoor_source = self._outdoor()
        demand = self._demand()
        await self._refresh_forecast(now)
        if indoor is not None and outdoor is not None:
            rate_entity = self.cfg.get(CONF_RATE)
            rate = self.hass.states.get(rate_entity) if rate_entity else None
            duty = .35 if rate and rate.state.lower() == "tickover" else float(demand)
            self.learner.add(now, indoor, outdoor, duty)
        await self._watch_response(now, indoor, demand)
        learned = self.learner.status()
        projected = self.learner.project(now, self._forecast, float(demand))
        bathroom = await self.bathroom.update(now=now, indoor=indoor, outdoor=outdoor,
                                              duty=float(demand), forecast=self._forecast)
        forecast_phrase = "forecast unavailable"
        if self._forecast:
            change = self._forecast[min(len(self._forecast)-1, 2)][1] - self._forecast[0][1]
            forecast_phrase = "outdoor forecast falling" if change < -0.5 else \
                              "outdoor forecast rising" if change > 0.5 else "outdoor forecast steady"
        state_word = "heating requested" if demand else "no heat requested"
        response = self.watch["result"]
        projection_phrase = f" Predicted in 60 minutes: {projected:.1f}°C." if projected is not None else ""
        self.reason = (f"{self.entry.title}: {state_word}; room {indoor:.1f}°C; outdoor source {outdoor_source}; "
                       f"{forecast_phrase}. {response}. Thermal model: {learned['reason']}.{projection_phrase}") if indoor is not None else \
                      f"{self.entry.title}: temperature sensor unavailable; control response cannot be verified."
        self.store.async_delay_save(lambda: {"samples": self.learner.dump(), "watch": self.watch}, 30)
        return {"indoor": indoor, "outdoor": outdoor, "demand": demand, "projected": projected,
                "learned": learned, "reason": self.reason, "watch": dict(self.watch),
                "bathroom": bathroom}

    async def _refresh_forecast(self, now):
        # JNS_FORECAST_RETRY_V2: 5-min failure retry, 15-min success refresh,
        # keep valid cached forecast for at most 90 minutes after last success.
        last_success = self._forecast_at
        last_attempt = getattr(self, "_forecast_attempt_at", None)
        if last_success and now - last_success < timedelta(minutes=15):
            return
        if last_attempt and now - last_attempt < timedelta(minutes=5):
            return
        self._forecast_attempt_at = now
        # Drop stale data, never pass a long-expired forecast to the learner.
        if last_success and now - last_success > timedelta(minutes=90):
            self._forecast = []
        configured = self.cfg.get(CONF_WEATHER)
        live = [s.entity_id for s in self.hass.states.async_all("weather")
                if s.state not in ("unknown", "unavailable")]
        if configured in live:
            weather = configured
        elif not configured and len(live) == 1:
            weather = live[0]
        else:
            _LOGGER.warning("JNS hourly forecast waiting for configured provider %s (live=%s)",
                            configured, len(live))
            return
        try:
            response = await self.hass.services.async_call(
                "weather", "get_forecasts", {"type": "hourly"},
                target={"entity_id": weather}, blocking=True, return_response=True)
            rows = (response or {}).get(weather, {}).get("forecast", [])
            forecast = [(datetime.fromisoformat(x["datetime"]), float(x["temperature"]))
                        for x in rows if x.get("datetime") and x.get("temperature") is not None][:12]
            if len(forecast) < 2:
                _LOGGER.warning("JNS hourly forecast insufficient data from %s", weather)
                return
            self._forecast = forecast
            self._forecast_at = now
            _LOGGER.info("JNS hourly forecast source: %s (%s points)", weather, len(forecast))
        except (ValueError, TypeError, KeyError, AttributeError, HomeAssistantError) as exc:
            _LOGGER.warning("JNS hourly forecast retry pending for %s: %s", weather, exc)

    async def async_start_manual_test(self):
        indoor = self._number(self.cfg[CONF_TEMPERATURE])
        if indoor is None: return
        self.watch.update(active=True, stage=0, baseline=indoor,
                          deadline=(dt_util.utcnow()+timedelta(minutes=self.cfg[CONF_RESPONSE_MINUTES])).isoformat(),
                          fault=False, manual=True, result="Manual response test started")
        await self._command_on()
        await self.async_request_refresh()

    def clear_fault(self):
        self.watch.update(active=False, stage=0, baseline=None, deadline=None,
                          fault=False, manual=False, result="Fault cleared; monitoring")
        self.async_set_updated_data({**(self.data or {}), "watch": dict(self.watch), "reason": self.reason})

    async def _watch_response(self, now, indoor, demand):
        w = self.watch
        if w.get("fault") and not w.get("manual"):
            w["result"] = "FAULT remains latched; clear it manually before another automatic response test"
            return
        if indoor is None:
            w["result"] = "Response check paused: temperature sensor unavailable"
            return
        # JNS_RESPONSE_RECOVERY_V1: clear only the obsolete unavailable-sensor message.
        if w.get("result") == "Response check paused: temperature sensor unavailable" and not w.get("active") and not w.get("fault"):
            w["result"] = "Temperature restored; monitoring"
        if demand and not w["active"]:
            w.update(active=True, stage=0, baseline=indoor,
                     deadline=(now+timedelta(minutes=self.cfg[CONF_RESPONSE_MINUTES])).isoformat(),
                     result=f"Heating response check started at {indoor:.1f}°C")
            return
        if not demand and not w.get("manual"):
            if w["active"]: w["result"] = "Heating call ended; response monitor reset"
            w.update(active=False, stage=0, baseline=None, deadline=None)
            return
        if not w["active"] or not w.get("deadline") or now < datetime.fromisoformat(w["deadline"]): return
        rise = indoor - float(w["baseline"])
        if rise >= float(self.cfg[CONF_MIN_RISE]):
            w.update(active=False, stage=0, fault=False, manual=False,
                     result=f"Heating response verified: temperature rose {rise:.2f}°C")
            return
        if w["stage"] == 0:
            changed = await self._increase_rate()
            w["stage"] = 1; w["baseline"] = indoor
            w["deadline"] = (now+timedelta(minutes=self.cfg[CONF_RESPONSE_MINUTES])).isoformat()
            w["result"] = "No confirmed rise; heating rate increased once" if changed else \
                          "No confirmed rise; selected controller has no safe rate increase, waiting before one ON retry"
        elif w["stage"] == 1:
            await self._command_on()
            w["stage"] = 2; w["baseline"] = indoor
            w["deadline"] = (now+timedelta(minutes=self.cfg[CONF_RESPONSE_MINUTES])).isoformat()
            w["result"] = "No confirmed rise after escalation; ON command resent once"
        else:
            w.update(active=False, fault=True, manual=False,
                     result="FAULT: no temperature response after escalation and one ON retry; automatic retries stopped")
            _LOGGER.error("%s", w["result"])
            await self.hass.services.async_call("persistent_notification", "create", {
                "title": f"JNS heating fault — {self.entry.title}",
                "message": (f"{self.entry.title} did not show the configured temperature rise after one rate "
                            "increase and one ON-command retry. Automatic retries have stopped. Check fuel, "
                            "power, RF/controller state and the temperature sensor before clearing the fault."),
                "notification_id": f"jns_heating_response_{self.entry.entry_id}"}, blocking=True)

    async def _increase_rate(self):
        entity = self.cfg.get(CONF_RATE)
        if entity:
            state = self.hass.states.get(entity)
            options = (state.attributes.get("options") or []) if state else []
            fast = next((x for x in options if x.lower() == "fast"), None)
            if fast:
                await self.hass.services.async_call(entity.split('.')[0], "select_option",
                    {"option": fast}, target={"entity_id": entity}, blocking=True)
                return True
            if entity.startswith("script."):
                await self.hass.services.async_call("script", entity.split('.', 1)[1],
                    {"mode": "FAST"}, blocking=True)
                return True
            if entity.startswith("button."):
                await self.hass.services.async_call("button", "press", {},
                    target={"entity_id": entity}, blocking=True)
                return True
        heater = self.hass.states.get(self.cfg[CONF_HEATER])
        if heater and heater.domain == "climate" and float(self.cfg[CONF_BOOST]) > 0:
            target = float(heater.attributes.get("temperature", heater.state))
            target = min(target + float(self.cfg[CONF_BOOST]), float(self.cfg[CONF_MAX_TARGET]))
            await self.hass.services.async_call("climate", "set_temperature", {"temperature": target},
                target={"entity_id": heater.entity_id}, blocking=True)
            return True
        return False

    async def _command_on(self):
        heater = self.hass.states.get(self.cfg[CONF_HEATER])
        if not heater: return
        if heater.domain == "climate":
            await self.hass.services.async_call("climate", "set_hvac_mode", {"hvac_mode": "heat"},
                target={"entity_id": heater.entity_id}, blocking=True)
        elif heater.domain == "script":
            await self.hass.services.async_call("script", heater.entity_id.split('.', 1)[1], {}, blocking=True)
        elif heater.domain == "button":
            await self.hass.services.async_call("button", "press", {},
                target={"entity_id": heater.entity_id}, blocking=True)
        else:
            await self.hass.services.async_call(heater.domain, "turn_on", {},
                target={"entity_id": heater.entity_id}, blocking=True)

    async def async_shutdown(self):
        await self.store.async_save({"samples": self.learner.dump(), "watch": self.watch})
        await self.bathroom.async_shutdown()
