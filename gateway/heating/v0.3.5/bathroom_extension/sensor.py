from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from .const import DOMAIN
from .entity import ZoneEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ReasonSensor(c), ResponseSensor(c), ConfidenceSensor(c), IndoorSensor(c), ProjectedSensor(c), BathroomSourceSensor(c), BathroomForecastSensor(c), BathroomQualitySensor(c)])


class ReasonSensor(ZoneEntity, SensorEntity):
    _attr_name = "Logic explanation"
    _attr_icon = "mdi:head-question-outline"
    @property
    def native_value(self): return self.coordinator.data.get("reason", "Starting")[:255]
    @property
    def extra_state_attributes(self): return {"full_explanation": self.coordinator.data.get("reason")}


class ResponseSensor(ZoneEntity, SensorEntity):
    _attr_name = "Heating response"
    _attr_icon = "mdi:radiator"
    @property
    def native_value(self): return self.coordinator.data.get("watch", {}).get("result", "Idle")[:255]
    @property
    def extra_state_attributes(self): return self.coordinator.data.get("watch", {})


class ConfidenceSensor(ZoneEntity, SensorEntity):
    _attr_name = "Thermal learning"
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    @property
    def native_value(self): return self.coordinator.data.get("learned", {}).get("reason", "Starting")
    @property
    def extra_state_attributes(self): return self.coordinator.data.get("learned", {})


class IndoorSensor(ZoneEntity, SensorEntity):
    _attr_name = "Measured temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    @property
    def native_value(self): return self.coordinator.data.get("indoor")


class ProjectedSensor(ZoneEntity, SensorEntity):
    _attr_name = "Projected temperature in 60 minutes"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    @property
    def native_value(self): return self.coordinator.data.get("projected")



class BathroomSourceSensor(ZoneEntity, SensorEntity):
    _attr_name = "Bathroom advisory precision temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    @property
    def native_value(self):
        return (self.coordinator.data.get("bathroom") or {}).get("temperature")
    @property
    def extra_state_attributes(self):
        r = self.coordinator.data.get("bathroom") or {}
        return {"advisory_only": True, "source_entity": r.get("source"),
                "source_epoch": r.get("source_epoch"), "eligibility_reason": r.get("reason")}


class BathroomForecastSensor(ZoneEntity, SensorEntity):
    _attr_name = "Bathroom advisory projected temperature in 60 minutes"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    @property
    def native_value(self):
        return (self.coordinator.data.get("bathroom") or {}).get("projected")
    @property
    def extra_state_attributes(self):
        r = self.coordinator.data.get("bathroom") or {}
        model = r.get("learned") or {}
        return {"advisory_only": True, "validated": model.get("ready", False),
                "quality_state": r.get("state"), "reason": r.get("reason"),
                "source_entity": r.get("source"), "source_epoch": r.get("source_epoch")}


class BathroomQualitySensor(ZoneEntity, SensorEntity):
    _attr_name = "Bathroom advisory learning quality"
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    @property
    def native_value(self):
        return (self.coordinator.data.get("bathroom") or {}).get("state","Starting")
    @property
    def extra_state_attributes(self):
        return self.coordinator.data.get("bathroom") or {}
