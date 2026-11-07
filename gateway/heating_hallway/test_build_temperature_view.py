from copy import deepcopy
import unittest
from build_temperature_view import build_temperature_view,apply_in_memory
REFS={"hallway":"sensor.hall","fireplace":"sensor.fire","bathroom":"sensor.bathroom",
      "honeywell_indoor":"sensor.honeywell","honeywell_outdoor":"sensor.outside",
      "honeywell_climate":"climate.honeywell","plant":["sensor.plot1","sensor.plot2"]}

class ViewTests(unittest.TestCase):
    def test_preserves_testing_tabs(self):
        existing={"views":[{"path":"house-temperature","title":"House Temperature","cards":[{"type":"entities"}]},
                           {"path":"controls","cards":[]}]}
        result=apply_in_memory(existing,build_temperature_view(REFS))
        self.assertEqual(result["views"][:-1],existing["views"])
        self.assertEqual(len(existing["views"]),2)
        self.assertEqual(result["views"][-1]["path"],"temperature-trends")
    def test_fail_duplicate(self):
        existing={"views":[build_temperature_view(REFS)]}
        with self.assertRaises(ValueError):
            apply_in_memory(existing,build_temperature_view(REFS))
    def test_all_requested_sources_present(self):
        v=build_temperature_view(REFS)
        graph=[c for c in v["cards"] if c.get("type")=="custom:jns-temperature-timeline-card"][0]
        entities={s["entity"] for s in graph["series"]}
        self.assertEqual(entities,{
          "sensor.jns_hallway_house_temperature","sensor.jns_fireplace_temperature",
          "sensor.bathroom","sensor.honeywell",
          "sensor.jns_honeywell_target_temperature","sensor.outside"})
        self.assertEqual(graph["series"][0]["forecast_entity"],
                         "sensor.jns_hallway_thermal_forecast_60m")
        self.assertTrue(any(c.get("title")=="Plant plots: 7-day temperatures" for c in v["cards"]))
    def test_unavailable_plants_not_fabricated(self):
        vals=deepcopy(REFS);vals["plant"]=[]
        v=build_temperature_view(vals)
        self.assertTrue(any(c["type"]=="markdown" and "not currently registered" in c["content"]
                            for c in v["cards"] if c.get("type")=="markdown"))
        self.assertFalse(any(c.get("title")=="Plant plots: 7-day temperatures" for c in v["cards"]))
    def test_native_history_cards_present_if_custom_resource_missing(self):
        v=build_temperature_view(REFS,include_custom=False)
        self.assertFalse(any(c["type"].startswith("custom:") for c in v["cards"]))
        self.assertEqual(sum(c["type"]=="history-graph" for c in v["cards"]),2)
if __name__=="__main__":unittest.main()
