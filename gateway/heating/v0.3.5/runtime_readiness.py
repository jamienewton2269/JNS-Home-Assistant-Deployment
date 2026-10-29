#!/usr/bin/env python3
"""JNS heating release readiness: read-only runtime, no service calls."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
CODE=r'''
import datetime,json,os,urllib.request
from pathlib import Path
interesting=[
"climate.thermostat_thermostat",
"sensor.thermostat_thermostat_indoor_temperature",
"sensor.thermostat_thermostat_outdoor_temperature",
"weather.ha_general",
"binary_sensor.lyric_home_heating_heating_call",
"binary_sensor.lyric_home_heating_heating_response_fault",
"sensor.lyric_home_heating_thermal_learning",
"sensor.lyric_home_heating_projected_temperature_in_60_minutes",
"sensor.jns_house_heating_logic",
]
result={"api_reachable":False,"entities":{},"hass_version":None}
token=os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
result["supervisor_token_available"]=bool(token)
if token:
 try:
  headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"}
  base="http://127.0.0.1:80/api"
  req=urllib.request.Request(base+"/config",headers=headers)
  with urllib.request.urlopen(req,timeout=8) as resp:
   cfg=json.load(resp)
  result["api_reachable"]=True
  result["hass_version"]=cfg.get("version")
  for entity in interesting:
   try:
    req=urllib.request.Request(base+"/states/"+entity,headers=headers)
    with urllib.request.urlopen(req,timeout=5) as resp:
     st=json.load(resp)
    attrs=st.get("attributes",{})
    allowed={k:attrs.get(k) for k in
       ("hvac_action","hvac_mode","temperature","current_temperature","preset_mode","mode",
        "fault","reason","ready","samples","next_update","available") if k in attrs}
    result["entities"][entity]={"state":st.get("state"),"last_updated":st.get("last_updated"),"attributes":allowed}
   except Exception as e:
    result["entities"][entity]={"error_type":type(e).__name__}
 except Exception as e:
  result["error_type"]=type(e).__name__
  result["http_status"]=getattr(e,"code",None)
if token:
 for candidate_base in ("http://127.0.0.1:80/api/","http://127.0.0.1:80/api/config",
                         "http://127.0.0.1:8123/api","http://homeassistant:8123/api"):
  try:
   req=urllib.request.Request(candidate_base,headers={"Authorization":"Bearer "+token})
   with urllib.request.urlopen(req,timeout=4) as resp:
    result.setdefault("candidate_endpoints",[]).append({"endpoint":candidate_base,"status":resp.status})
  except Exception as e:
   result.setdefault("candidate_endpoints",[]).append({"endpoint":candidate_base,
          "error":type(e).__name__,"http_status":getattr(e,"code",None)})
root=Path("/config/custom_components/jns_heating_zones")
try:
 import hashlib
 result["installed_version"]=json.loads((root/"manifest.json").read_text()).get("version")
 result["installed_thermal_sha"]=hashlib.sha256((root/"thermal.py").read_bytes()).hexdigest()
 result["config_entries"]=[]
 reg=json.loads((Path("/config/.storage/core.config_entries")).read_text())
 for e in reg.get("data",{}).get("entries",[]):
  if e.get("domain")=="jns_heating_zones":
   result["config_entries"].append({"entry_id":e.get("entry_id"),"disabled_by":e.get("disabled_by")})
except Exception as e:result["storage_error_type"]=type(e).__name__
print(json.dumps(result,sort_keys=True))
'''
cmd="exec(__import__('base64').b64decode('"+base64.b64encode(CODE.encode()).decode()+"'))"
res=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",cmd]))
until=time.monotonic()+100
while not res.get("exited"):
 if not isinstance(res.get("pid"),int) or time.monotonic()>until:raise RuntimeError("readiness probe timeout")
 time.sleep(1)
 res=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(res["pid"])]))
if res.get("exitcode")!=0:raise RuntimeError("readiness probe failed")
report=json.loads(res.get("out-data") or "{}")
print("JNS_HEATING_RELEASE_READINESS "+json.dumps(report,sort_keys=True))
