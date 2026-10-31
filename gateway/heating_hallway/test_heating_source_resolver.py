"""Synthetic registry fixtures only. Never open a production .storage file in CI."""
import unittest
from copy import deepcopy
from heating_source_resolver import (
    HALLWAY_DEVICE_ID, FIREPLACE_IEEE, ResolutionError, resolve,
    BATHROOM_TEMP, HONEYWELL_INDOOR, HONEYWELL_OUTDOOR, HONEYWELL_CLIMATE)
DEV={"data":{"devices":[
    {"id":HALLWAY_DEVICE_ID,"name":"Hallway Thermometer","identifiers":[["mqtt","hallway"]]},
    {"id":"fire-123","identifiers":[["mqtt","zigbee2mqtt_"+FIREPLACE_IEEE]]}]}}
REG={"data":{"entities":[
    {"entity_id":"sensor.hallway_temperature","device_id":HALLWAY_DEVICE_ID,"original_device_class":"temperature"},
    {"entity_id":"sensor.fireplace_temperature","device_id":"fire-123","device_class":"temperature"},
    *({"entity_id":s,"device_id":None} for s in
      (BATHROOM_TEMP,HONEYWELL_INDOOR,HONEYWELL_OUTDOOR,HONEYWELL_CLIMATE)),
    {"entity_id":"sensor.ha900_moisture2_temperature","device_id":None}
]}}

class ResolverTests(unittest.TestCase):
    def test_identity_is_unique(self):
        result=resolve(DEV,REG)
        self.assertEqual(result["hallway"],"sensor.hallway_temperature")
        self.assertEqual(result["fireplace"],"sensor.fireplace_temperature")
        self.assertEqual(result["plant"],["sensor.ha900_moisture2_temperature"])
    def test_refuses_missing_device(self):
        devices=deepcopy(DEV)
        devices["data"]["devices"].pop(0)
        with self.assertRaises(ResolutionError):resolve(devices,REG)
    def test_refuses_duplicate_temperature(self):
        entities=deepcopy(REG)
        entities["data"]["entities"].append({"entity_id":"sensor.hall_extra_temperature","device_id":HALLWAY_DEVICE_ID})
        with self.assertRaises(ResolutionError):resolve(DEV,entities)
    def test_refuses_non_temperature_fake(self):
        entities=deepcopy(REG)
        entities["data"]["entities"][0]["entity_id"]="sensor.hallway_humidity"
        with self.assertRaises(ResolutionError):resolve(DEV,entities)
    def test_refuses_unavailable_honeywell(self):
        entities=deepcopy(REG)
        entities["data"]["entities"]=[x for x in entities["data"]["entities"] if x["entity_id"]!=HONEYWELL_CLIMATE]
        with self.assertRaises(ResolutionError):resolve(DEV,entities)
    def test_disables_unverified_devices(self):
        entities=deepcopy(REG)
        entities["data"]["entities"][1]["disabled_by"]="user"
        with self.assertRaises(ResolutionError):resolve(DEV,entities)

if __name__=="__main__":unittest.main()
