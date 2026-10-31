#!/usr/bin/env python3
import base64,json,shlex,subprocess,time
SRC=r'''
from pathlib import Path
import json,re,yaml,sqlite3,datetime
P=Path("/config")
def load(n,k):
    try:return json.loads((P/".storage"/n).read_text())["data"][k]
    except Exception:return []
ents=load("core.entity_registry","entities")
byid={e.get("entity_id"):e for e in ents}
cfg=load("core.config_entries","entries")

# Controller YAML
autos=yaml.safe_load((P/"automations.yaml").read_text())
ctl=next((a for a in autos if str(a.get("id"))=="1791918795028"),None)
assert ctl is not None,"main Lux controller missing"
blob=yaml.safe_dump(ctl,sort_keys=False,allow_unicode=True,width=180)

# Discover all referenced entities from controller + key Lux packages.
refs=set(re.findall(r"(?:sensor|binary_sensor|input_number|input_boolean|light|switch|weather|sun|automation)\.[A-Za-z0-9_]+",blob))
for fp in sorted((P/"packages").glob("*.yaml")):
    if re.search(r"lux|lighting|dusk",fp.name,re.I):
        try:t=fp.read_text()
        except:continue
        refs.update(re.findall(r"(?:sensor|binary_sensor|input_number|input_boolean|light|switch|weather|sun|automation)\.[A-Za-z0-9_]+",t))

# Important expected inputs.
expected=[
"sensor.0xa4c1383917c90309_illuminance",
"sensor.0xa4c1383917c90309_outdoor_lux_10_minute_average",
"sensor.jns_lighting_effective_lux",
"binary_sensor.outdoor_raining",
"binary_sensor.jns_lux_priority_bright_stable",
"binary_sensor.jns_lux_bright_enough_for_off",
"input_number.general_outdoor_lighting_on_lux",
"input_number.general_lighting_lux_hysteresis",
"input_number.general_lux_full_brightness_at",
"input_number.general_lux_relay_on_lux",
"input_number.jns_synthetic_lux_factor",
"input_boolean.jns_lux_ladder_initialized",
"sun.sun"
]
for e in expected: refs.add(e)

# Recorder latest states and update ages.
db=P/"home-assistant_v2.db"
states={}
if db.exists():
 c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=4);cur=c.cursor()
 for eid in sorted(refs):
  try:
   cur.execute("""SELECT s.state,s.last_updated_ts,s.attributes_id FROM states s
     JOIN states_meta m ON s.metadata_id=m.metadata_id
     WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 1""",(eid,))
   row=cur.fetchone()
   if row:
    st,ts,aid=row
    states[eid]={"state":st,"last_updated_utc":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if ts else None,
                 "age_seconds":(datetime.datetime.now(datetime.timezone.utc).timestamp()-ts) if ts else None}
  except Exception: pass
 c.close()

# Weather entities/integrations actually registered.
weather=[e.get("entity_id") for e in ents if str(e.get("entity_id","")).startswith("weather.") and not e.get("disabled_by")]
integrations=[{"domain":e.get("domain"),"title":e.get("title"),"disabled":e.get("disabled_by")} for e in cfg
              if e.get("domain") in ("open_meteo","met","mqtt","sun")]

# Lights/switches selected by ladder helper names.
names=["hall","front","worktop","snug","radiator","tripod","living","sofa"]
ladder={}
for n in names:
 inc="input_boolean.jns_lux_include_"+n
 rank="input_number.jns_lux_rank_"+n
 ladder[n]={"enabled":states.get(inc,{}).get("state"),"rank":states.get(rank,{}).get("state")}

# Controller health rules.
desc=str(ctl.get("description",""))
vars_blob=json.dumps(ctl.get("actions",ctl.get("action")),default=str)
checks={
 "controller_registered": byid.get("automation.general_shared_lux_progressive_control") is not None,
 "controller_registry_enabled": (byid.get("automation.general_shared_lux_progressive_control") or {}).get("disabled_by") is None,
 "controller_mode_restart": ctl.get("mode")=="restart",
 "stale_lux_patch_present": "JNS_LUX_STALE_DUSK_V1" in desc,
 "live_lux_freshness_logic": "live_lux_fresh" in vars_blob and "300" in vars_blob,
 "dusk_weighting_logic": "minutes_to_sunset" in vars_blob and "dusk_cap_lux" in vars_blob,
 "stale_blocks_auto_off": "live_lux_fresh" in vars_blob and "safe_off" in vars_blob,
 "rain_blocks_auto_off": "raining" in vars_blob and "safe_off" in vars_blob,
 "priority_ladder_initialized": states.get("input_boolean.jns_lux_ladder_initialized",{}).get("state")=="on",
}
raw=states.get("sensor.0xa4c1383917c90309_illuminance",{})
checks["raw_lux_available"]=raw.get("state") not in (None,"unknown","unavailable")
checks["raw_lux_fresh_now"]=(raw.get("age_seconds") is not None and raw["age_seconds"]<=300)

# Recent controller execution timestamps.
for eid in ["automation.general_shared_lux_progressive_control","binary_sensor.jns_lux_priority_bright_stable",
            "sensor.jns_lighting_effective_lux","sensor.0xa4c1383917c90309_illuminance",
            "sensor.0xa4c1383917c90309_outdoor_lux_10_minute_average","binary_sensor.outdoor_raining","sun.sun"]:
    if eid in refs and eid not in states: states[eid]={"state":"NO_RECORDER_STATE"}

obj={
 "checks":checks,
 "controller":{"id":ctl.get("id"),"alias":ctl.get("alias"),"description":desc,"mode":ctl.get("mode")},
 "core_entities":{e:states.get(e,{"state":"NOT_FOUND"}) for e in expected},
 "weather_entities":weather,
 "integrations":integrations,
 "ladder":ladder,
 "referenced_entity_count":len(refs),
 "referenced_missing_or_disabled":[e for e in sorted(refs) if (e not in byid and not e.startswith("sun.")) or (e in byid and byid[e].get("disabled_by") is not None)],
}
print("JNS_LUX_FULL_AUDIT="+json.dumps(obj,sort_keys=True,default=str),flush=True)
'''
enc=base64.b64encode(SRC.encode()).decode()
code="exec(__import__('base64').b64decode("+repr(enc)+"))"
def ssh(argv):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],
                  capture_output=True,text=True,timeout=40)
 if p.returncode: raise RuntimeError(p.stderr[-500:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code])
pid=d.get("pid")
for _ in range(80):
 if d.get("exited"):break
 if not isinstance(pid,int): raise RuntimeError("QGA missing initial pid")
 time.sleep(.5)
 d=ssh(["qm","guest","exec-status","905",str(pid)])
print(d.get("out-data") or "",flush=True)
if d.get("exitcode")!=0: raise SystemExit(d.get("exitcode") or 2)
