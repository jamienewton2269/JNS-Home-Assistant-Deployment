#!/usr/bin/env python3
"""Guarded HA-General Lux reception/fallback OFF repair. Dry-run by default."""
from pathlib import Path
import os,sys,json,yaml,hashlib,datetime,shutil,tempfile
ROOT=Path("/config")
A=ROOT/"automations.yaml"
S=ROOT/"packages/jns_synthetic_lux_calibration.yaml"
ID="1791918795028"
TAG="JNS_LUX_REPORT_AND_DAYLIGHT_OFF_20261102"
def chk(x,msg):
    if not x: raise RuntimeError(msg)
def sha(x): return hashlib.sha256(x).hexdigest()
def patch_auto(raw):
    d=yaml.safe_load(raw)
    hits=[a for a in d if str(a.get("id"))==ID]
    chk(len(hits)==1,"Lux automation not unique")
    a=hits[0]
    chk("General - Shared Lux Progressive Control" in a.get("alias",""),"unexpected automation")
    acts=a.get("actions",a.get("action"))
    chk(isinstance(acts,list) and len(acts)>1,"unexpected controller action layout")
    v=acts[0].get("variables")
    chk(isinstance(v,dict),"missing controller variables")
    chk("sensor_fresh" in v or "live_lux_fresh" in v,"missing existing freshness logic")
    for k in ("sensor_fresh","live_lux_age_seconds"):
        if k in v:
            v[k]=v[k].replace(".last_updated",".last_reported")
    # Only grant OFF in fallback when weather source is genuinely current and
    # sun is well above the horizon, beyond dusk lock, and forecast lux is high.
    fallback="""{% set w = ['weather.ha_general','weather.forecast_home'] %}
{% set ok = namespace(valid=false) %}
{% for id in w %}
  {% set s=states[id.split('.')[0]][id.split('.')[1]] if states[id.split('.')[0]][id.split('.')[1]] is defined else none %}
  {% if s is not none and s.state not in ['unknown','unavailable','']
       and (as_timestamp(now())-as_timestamp(s.last_updated,0)) <= 1200 %}
    {% set ok.valid=true %}
  {% endif %}
{% endfor %}
{{ ok.valid and not dusk_lock|bool
   and not raining|bool
   and state_attr('sun.sun','elevation')|float(-90) >= 8
   and decision_lux|float(0) >=
       states('input_number.general_outdoor_lighting_on_lux')|float(2500)
       + states('input_number.general_lighting_lux_hysteresis')|float(400) + 300 }}"""
    rebuilt={}
    for k,value in v.items():
        if k=="safe_off": rebuilt["weather_fallback_safe"]=fallback
        rebuilt[k]=value
    if "weather_fallback_safe" not in rebuilt: rebuilt["weather_fallback_safe"]=fallback
    for k in ("safe_off",):
        if k in rebuilt:
            s=rebuilt[k]
            if "sensor_fresh|bool" in s: s=s.replace("and sensor_fresh|bool","and (sensor_fresh|bool or weather_fallback_safe|bool)")
            elif "live_lux_fresh|bool" in s: s=s.replace("and live_lux_fresh|bool","and (live_lux_fresh|bool or weather_fallback_safe|bool)")
            else: raise RuntimeError("top safe_off freshness guard changed")
            rebuilt[k]=s
    acts[0]["variables"]=rebuilt
    seq=acts[1]["repeat"]["sequence"]
    positions=[step["variables"] for step in seq if isinstance(step,dict) and isinstance(step.get("variables"),dict) and "safe_off" in step["variables"]]
    chk(len(positions)==1,"per-light safe_off not unique")
    p=positions[0]; old=p["safe_off"]
    if "sensor_fresh|bool" in old: new=old.replace("and sensor_fresh|bool","and (sensor_fresh|bool or weather_fallback_safe|bool)")
    elif "live_lux_fresh|bool" in old: new=old.replace("and live_lux_fresh|bool","and (live_lux_fresh|bool or weather_fallback_safe|bool)")
    else: raise RuntimeError("per-light safe_off freshness guard changed")
    chk(new!=old,"no safe_off adjustment made")
    p["safe_off"]=new
    chk(TAG not in a.get("description",""),"already installed")
    a["description"]=str(a.get("description","")).strip()+" "+TAG+": last_reported for fresh-state detection, current-weather daylight fallback may authorize OFF, retains 20-minute stability, per-light hysteresis, dusk, rain, manual guards."
    return yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=180).encode()
def patch_syn(raw):
    d=yaml.safe_load(raw)
    t=d.get("template",[])
    sensors=[item for group in t for item in group.get("sensor",[]) if item.get("unique_id")=="jns_lighting_effective_lux"]
    bright=[item for group in t for item in group.get("binary_sensor",[]) if item.get("unique_id")=="jns_lux_bright_enough_for_off"]
    chk(len(sensors)==1 and len(bright)==1,"unexpected synthetic package")
    for key in ("state",):
        sensors[0][key]=sensors[0][key].replace(".last_updated",".last_reported")
    attr=sensors[0].get("attributes",{})
    for k,v in attr.items():
        if isinstance(v,str): attr[k]=v.replace(".last_updated",".last_reported")
    state=bright[0]["state"].replace(".last_updated",".last_reported")
    chk("fresh and not dusk" in state,"bright enough original guard changed")
    fallback="""{% set w = namespace(ok=false) %}
{% for id in ['weather.ha_general','weather.forecast_home'] %}
  {% set s=states[id.split('.')[0]][id.split('.')[1]] if states[id.split('.')[0]][id.split('.')[1]] is defined else none %}
  {% if s is not none and s.state not in ['unknown','unavailable','']
     and (as_timestamp(now())-as_timestamp(s.last_updated,0)) <= 1200 %}
    {% set w.ok=true %}
  {% endif %}
{% endfor %}
{% set fallback = w.ok and state_attr('sun.sun','elevation')|float(-90)>=8
  and states('sensor.jns_lighting_effective_lux')|float(0) >=
    states('input_number.general_outdoor_lighting_on_lux')|float(2500)
    + states('input_number.general_lighting_lux_hysteresis')|float(400)+300 %}
"""
    state=fallback+state.replace("fresh and not dusk","(fresh or fallback) and not dusk")
    bright[0]["state"]=state
    chk("delay_on" in bright[0],"20 minute hold missing")
    return yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=180).encode()
def main():
    chk(A.is_file() and S.is_file(),"configuration files missing")
    before={A:A.read_bytes(),S:S.read_bytes()}
    after={A:patch_auto(before[A]),S:patch_syn(before[S])}
    report={"target":"HA-General VM905","tag":TAG,"files":{str(p):{"before":sha(before[p]),"after":sha(after[p])} for p in before}}
    print("LUX_OFF_PLAN "+json.dumps(report),flush=True)
    if "--apply" not in sys.argv:return
    chk(all(p.read_bytes()==before[p] for p in before),"concurrent edit")
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup=ROOT/".jns-backups"/("lux-daylight-off-"+stamp)
    backup.mkdir(parents=True,exist_ok=False)
    for p,b in before.items():
        (backup/p.name).write_bytes(b)
        chk(sha((backup/p.name).read_bytes())==sha(b),"backup corrupt")
    for p,b in after.items():
        stat=p.stat()
        fd,tmp=tempfile.mkstemp(dir=str(p.parent),prefix=".jns-lux-")
        with os.fdopen(fd,"wb") as f:f.write(b);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,stat.st_mode);os.chown(tmp,stat.st_uid,stat.st_gid);os.replace(tmp,p)
    report["backup"]=str(backup)
    print("LUX_OFF_APPLIED "+json.dumps(report),flush=True)
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("LUX_OFF_BLOCKED "+repr(exc),flush=True)
        sys.exit(2)
