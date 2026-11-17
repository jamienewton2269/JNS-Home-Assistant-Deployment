"""Create a Testing > Temperature Trends view from PRIVATE verified VM905 refs.

Never modify a live dashboard inside GitHub CI. The output is a candidate
object to be inserted by a root-approved, hash-guarded local operator tool.
"""
from __future__ import annotations

PATH = "temperature-trends"


def build_temperature_view(refs, *, include_custom=True):
    required=("hallway","fireplace","bathroom","honeywell_indoor",
              "honeywell_outdoor","honeywell_climate","plant")
    if any(k not in refs for k in required):
        raise ValueError("Unresolved sensor mapping")
    def series(entity, name, forecast=None):
        val={"entity":entity, "name":name}
        if forecast:val["forecast_entity"]=forecast
        return val
    house=[
        series("sensor.jns_hallway_house_temperature","Hallway (house authority)",
               "sensor.jns_hallway_thermal_forecast_60m"),
        series("sensor.jns_fireplace_temperature","Fireplace"),
        series(refs["bathroom"],"Bathroom (monitor only)"),
        series(refs["honeywell_indoor"],"Honeywell measured"),
        series("sensor.jns_honeywell_target_temperature","Honeywell setpoint"),
        series(refs["honeywell_outdoor"],"Outside"),
    ]
    plants=[series(e,"Plant plot "+str(i+1)) for i,e in enumerate(refs["plant"])]
    cards=[
      {"type":"entities","title":"Live house readings and protection",
       "show_header_toggle":False,
       "entities":[
         {"entity":"sensor.jns_hallway_house_temperature","name":"Authoritative house temperature"},
         {"entity":"sensor.jns_fireplace_temperature","name":"Fireplace temperature"},
         {"entity":"binary_sensor.jns_fireplace_heat_detected","name":"Fire lit (inferred)"},
         {"entity":"input_boolean.jns_fireplace_override_enabled","name":"Enable fireplace heating override"},
         {"entity":"binary_sensor.jns_fireplace_override_safe","name":"Fire override safety gate"},
         {"entity":"sensor.jns_hallway_thermal_forecast_60m","name":"Predicted hallway +60m"},
         {"entity":"sensor.jns_honeywell_target_temperature","name":"Honeywell setpoint"},
         {"entity":refs["bathroom"],"name":"Bathroom (display only)"},
       ]},
      {"type":"history-graph","title":"House and outside temperature · last 24 h",
       "hours_to_show":24,"refresh_interval":60,
       "entities":[x["entity"] for x in house]},
    ]
    if include_custom:
        cards.insert(1,{"type":"custom:jns-temperature-timeline-card",
                        "title":"House: history + validated 60-minute prediction",
                        "hours":24,"series":house})
    if plants:
        if include_custom:
            cards.append({"type":"custom:jns-temperature-timeline-card",
                          "title":"Plant plots: 7-day temperatures",
                          "hours":168,"series":plants})
        cards.append({"type":"history-graph","title":"Plant plots · last 7 days",
                      "hours_to_show":168,"refresh_interval":60,
                      "entities":[s["entity"] for s in plants]})
    else:
        cards.append({"type":"markdown","content":
            "Plant plot temperature entities are not currently registered on HA-General. "
            "Plant Manager VM903 remains unchanged; no values have been invented."})
    cards.append({"type":"markdown","content":
      "Dashed segments show **validated** future predictions; solid lines show Recorder "
      "history. When the hallway-specific thermal model is not ready, predictions "
      "remain unavailable and the fireplace heating override is blocked. "
      "Bathroom readings are displayed only; they do not control or train heating."})
    return {"title":"Temperature Trends","path":PATH,"icon":"mdi:chart-areaspline",
            "cards":cards}


def apply_in_memory(testing_dashboard, new_view):
    """No file I/O; verify all other existing views are preserved."""
    import copy
    if not isinstance(testing_dashboard,dict) or not isinstance(testing_dashboard.get("views"),list):
        raise ValueError("Testing dashboard invalid")
    views=testing_dashboard["views"]
    if any(x.get("path")==PATH for x in views):
        raise ValueError("Temperature Trends view already installed; refuse duplicate")
    updated=copy.deepcopy(testing_dashboard)
    updated["views"].append(new_view)
    if updated["views"][:-1] != testing_dashboard["views"]:
        raise AssertionError("Existing Testing tabs changed")
    return updated
