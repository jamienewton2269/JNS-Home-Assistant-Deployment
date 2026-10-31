#!/usr/bin/env python3
"""Guarded Lux/weather repair for HA-General VM905.
Patches only:
  /config/automations.yaml automation 1791918795028
  /config/packages/jns_synthetic_lux_calibration.yaml
  /config/packages/outdoor_environment.yaml
Preserves current priority ladder and manual override logic.
"""
from pathlib import Path
import copy,datetime,hashlib,json,os,stat,sys,tempfile,yaml

ROOT=Path("/config")
AUTO=ROOT/"automations.yaml"
SYN=ROOT/"packages/jns_synthetic_lux_calibration.yaml"
ENV=ROOT/"packages/outdoor_environment.yaml"
ID="1791918795028"
TAG="JNS_LUX_WEATHER_DUSK_REPAIR_V2"
RAIN_STATES="['rainy','pouring','lightning-rainy','snowy-rainy']"
BAD_STATES="['unknown','unavailable','']"

def req(ok,msg):
    if not ok: raise RuntimeError(msg)
def sha(b): return hashlib.sha256(b).hexdigest()
def atomic(path,data):
    st=path.stat()
    fd,tmp=tempfile.mkstemp(prefix=".jns-lux-weather-repair-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.chown(tmp,st.st_uid,st.st_gid)
        os.chmod(tmp,stat.S_IMODE(st.st_mode))
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def weather_factor_template():
    return """{% set factors = namespace(v=[]) %}
{% for w in [weather_met_state|lower, weather_openmeteo_state|lower] %}
  {% if w not in ['unknown','unavailable',''] %}
    {% set f = 0.35 if w in ['rainy','pouring','lightning-rainy','snowy','snowy-rainy','fog','exceptional']
       else (0.55 if w in ['cloudy','lightning'] else (0.8 if w in ['partlycloudy','windy-variant'] else 1.0)) %}
    {% set factors.v = factors.v + [f] %}
  {% endif %}
{% endfor %}
{{ factors.v|min if factors.v|count > 0 else 1.0 }}"""

def patch_controller(raw):
    doc=yaml.safe_load(raw)
    req(isinstance(doc,list),"automations.yaml root changed")
    hits=[x for x in doc if str(x.get("id"))==ID]
    req(len(hits)==1,"Lux controller missing/duplicated")
    a=hits[0]
    req(a.get("alias")=="General - Shared Lux Progressive Control","unexpected Lux controller alias")
    req(a.get("mode")=="restart","unexpected controller mode")
    actions=a.get("actions",a.get("action"))
    req(isinstance(actions,list) and len(actions)>=2,"unexpected controller actions")
    vars0=actions[0].get("variables")
    req(isinstance(vars0,dict) and "decision_lux" in vars0 and "all_eligible" in vars0,"controller variables drifted")
    req("JNS_LUX_PRIORITY_LADDER_V1" in str(a.get("description","")),"priority ladder tag missing")

    # Preserve all unrelated variables while replacing only input/model variables.
    rebuilt={}
    for k,v in vars0.items():
        if k in {"raining","weather_entity","weather_state","sensor_fresh","fallback_mode","decision_lux",
                 "base_decision_lux","weather_met_state","weather_openmeteo_state","weather_factor",
                 "minutes_to_sunset","dusk_lock","dusk_cap_lux"}:
            continue
        # insert repaired model immediately after avg_lux for readability/order
        rebuilt[k]=v
        if k=="avg_lux":
            rebuilt["weather_met_state"]="{{ states('weather.forecast_home') }}"
            rebuilt["weather_openmeteo_state"]="{{ states('weather.ha_general') }}"
            rebuilt["weather_state"]="""{% set good = [weather_met_state, weather_openmeteo_state]
  | reject('in',['unknown','unavailable','']) | list %}
{{ good | join('+') if good|count > 0 else 'unavailable' }}"""
            rebuilt["weather_factor"]=weather_factor_template()
            rebuilt["raining"]="{{ is_state('binary_sensor.outdoor_raining','on') }}"
            rebuilt["sensor_fresh"]="""{{ has_value('sensor.0xa4c1383917c90309_illuminance')
  and (as_timestamp(now()) - as_timestamp(states.sensor['0xa4c1383917c90309_illuminance'].last_updated,0)) <= 300
  and (states('sensor.0xa4c1383917c90309_illuminance') | float(0)) > 0 }}"""
            rebuilt["fallback_mode"]="""{{ 'LIVE LUX' if sensor_fresh|bool
  else ('WEATHER CONSENSUS FALLBACK'
        if weather_met_state not in ['unknown','unavailable','']
           or weather_openmeteo_state not in ['unknown','unavailable','']
        else 'SUN/TIME FALLBACK') }}"""
            rebuilt["minutes_to_sunset"]="""{% set ns = state_attr('sun.sun','next_setting') %}
{{ ((as_timestamp(as_datetime(ns),0) - as_timestamp(now())) / 60) if ns else 9999 }}"""
            rebuilt["dusk_lock"]="""{{ is_state('sun.sun','below_horizon')
  or (minutes_to_sunset|float(9999) >= 0 and minutes_to_sunset|float(9999) <= 120) }}"""
            rebuilt["dusk_cap_lux"]="""{% set base = states('input_number.general_outdoor_lighting_on_lux')|float(2500) %}
{% set mins = minutes_to_sunset|float(9999) %}
{% if is_state('sun.sun','below_horizon') %}100
{% elif mins <= 0 %}100
{% elif mins < 120 %}{{ [100, base * (mins / 120)] | max }}
{% else %}99999{% endif %}"""
            rebuilt["base_decision_lux"]="""{% if sensor_fresh|bool %}
  {{ [raw_lux|float, avg_lux|float] | min if raining|bool else avg_lux|float }}
{% else %}
  {% set elevation = state_attr('sun.sun','elevation') | float(-10) %}
  {% set sun_lux = [0, elevation] | max * 700 %}
  {{ (sun_lux * (weather_factor|float(1.0))
      * (states('input_number.jns_synthetic_lux_factor')|float(0.30))) | round(0) }}
{% endif %}"""
            rebuilt["decision_lux"]="""{% set base = base_decision_lux|float(99999) %}
{% if dusk_lock|bool %}
  {{ [base, dusk_cap_lux|float(99999)] | min }}
{% else %}
  {{ base }}
{% endif %}"""
    req("base_decision_lux" in rebuilt and "decision_lux" in rebuilt,"model insertion failed")
    actions[0]["variables"]=rebuilt

    # Top-level safe_off variable must obey same stale/dusk rule.
    rebuilt["safe_off"]="""{{ is_state('binary_sensor.jns_lux_bright_enough_for_off','on')
  and sensor_fresh|bool
  and not dusk_lock|bool
  and not raining|bool
  and (decision_lux|float(0)) >=
      ((states('input_number.general_outdoor_lighting_on_lux')|float(2500))
       + (states('input_number.general_lighting_lux_hysteresis')|float(400))) }}"""

    # Per-light safe_off: preserve reverse priority ladder but forbid stale/dusk/rain OFF.
    repeat=actions[1].get("repeat")
    req(isinstance(repeat,dict),"repeat block missing")
    seq=repeat.get("sequence")
    varstep=next((x for x in seq if isinstance(x,dict) and isinstance(x.get("variables"),dict)),None)
    req(varstep is not None and "safe_off" in varstep["variables"],"per-light safe_off missing")
    varstep["variables"]["safe_off"]="""{{ is_state('binary_sensor.jns_lux_priority_bright_stable','on')
  and sensor_fresh|bool
  and not dusk_lock|bool
  and not raining|bool
  and is_state(e,'on')
  and decision_lux|float >=
      (start_lux|float + states('input_number.general_lighting_lux_hysteresis')|float(400)) }}"""

    # Trigger immediately on both weather providers as well as existing triggers.
    triggers=a.get("triggers",a.get("trigger"))
    req(isinstance(triggers,list),"triggers missing")
    state_list=next((t for t in triggers if isinstance(t,dict) and t.get("trigger")=="state" and isinstance(t.get("entity_id"),list)),None)
    req(state_list is not None,"main state trigger missing")
    for eid in ["weather.forecast_home","weather.ha_general"]:
        if eid not in state_list["entity_id"]: state_list["entity_id"].append(eid)

    desc=str(a.get("description",""))
    if TAG not in desc:
        a["description"]=(desc+" "+TAG+
          ": live lux stale after 5 min; MET + Open-Meteo use conservative weather consensus; "
          "physical/weather rain fallback; west-facing lux influence capped through final 120 min before sunset; "
          "stale/dusk/night/rain can never authorize automatic OFF.").strip()

    # Verify current ladder/manual logic survived.
    outblob=json.dumps(a,default=str)
    for must in ["JNS_LUX_PRIORITY_LADDER_V1","input_text.jns_lux_off_tonight_entities",
                 "input_boolean.jns_lux_manual_hold_all","input_number.jns_lux_ladder_stage_gap"]:
        req(must in outblob,"existing controller feature lost: "+must)
    return yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=180).encode()

def find_template_entity(doc,section,name=None,uid=None):
    t=doc.get("template")
    req(isinstance(t,list),"template section missing")
    for block in t:
        if not isinstance(block,dict): continue
        arr=block.get(section)
        if not isinstance(arr,list): continue
        for item in arr:
            if not isinstance(item,dict): continue
            if (uid and item.get("unique_id")==uid) or (name and item.get("name")==name):
                return item
    raise RuntimeError("template entity missing: "+str(uid or name))

def patch_synthetic(raw):
    d=yaml.safe_load(raw)
    sens=find_template_entity(d,"sensor",uid="jns_lighting_effective_lux")
    sens["state"]="""{% set raw = states('sensor.0xa4c1383917c90309_illuminance') | float(0) %}
{% set valid = has_value('sensor.0xa4c1383917c90309_illuminance')
  and (as_timestamp(now())-as_timestamp(states.sensor['0xa4c1383917c90309_illuminance'].last_updated,0)) <= 300
  and raw > 0 %}
{% if valid %}
  {% set avg = states('sensor.0xa4c1383917c90309_outdoor_lux_10_minute_average') | float(raw) %}
  {{ ([raw,avg]|min if is_state('binary_sensor.outdoor_raining','on') else avg) | round(0) }}
{% else %}
  {% set el = [0, state_attr('sun.sun','elevation')|float(-10)]|max %}
  {% set factors = namespace(v=[]) %}
  {% for w in [states('weather.forecast_home')|lower, states('weather.ha_general')|lower] %}
    {% if w not in ['unknown','unavailable',''] %}
      {% set f = 0.35 if w in ['rainy','pouring','lightning-rainy','snowy','snowy-rainy','fog','exceptional']
         else (0.55 if w in ['cloudy','lightning'] else (0.8 if w in ['partlycloudy','windy-variant'] else 1.0)) %}
      {% set factors.v = factors.v + [f] %}
    {% endif %}
  {% endfor %}
  {% set wf = factors.v|min if factors.v|count > 0 else 1.0 %}
  {{ (el*700*wf*(states('input_number.jns_synthetic_lux_factor')|float(0.30))) | round(0) }}
{% endif %}"""
    attrs=sens.setdefault("attributes",{})
    attrs["source"]="""{% set raw = states('sensor.0xa4c1383917c90309_illuminance') | float(0) %}
{% set valid = has_value('sensor.0xa4c1383917c90309_illuminance')
  and (as_timestamp(now()) - as_timestamp(states.sensor['0xa4c1383917c90309_illuminance'].last_updated,0)) <= 300
  and raw > 0 %}
{% if valid %}LIVE LUX
{% elif states('weather.forecast_home') not in ['unknown','unavailable','']
   or states('weather.ha_general') not in ['unknown','unavailable',''] %}WEATHER CONSENSUS FALLBACK
{% else %}SUN/TIME FALLBACK{% endif %}"""
    attrs["met_weather"]="{{ states('weather.forecast_home') }}"
    attrs["open_meteo_weather"]="{{ states('weather.ha_general') }}"

    bright=find_template_entity(d,"binary_sensor",uid="jns_lux_bright_enough_for_off")
    bright["state"]="""{% set s = states.sensor['0xa4c1383917c90309_illuminance']
     if states.sensor['0xa4c1383917c90309_illuminance'] is defined else none %}
{% set fresh = s is not none and has_value('sensor.0xa4c1383917c90309_illuminance')
   and (as_timestamp(now())-as_timestamp(s.last_updated,0)) <= 300
   and states('sensor.0xa4c1383917c90309_illuminance')|float(0) > 0 %}
{% set ns = state_attr('sun.sun','next_setting') %}
{% set mins = ((as_timestamp(as_datetime(ns),0)-as_timestamp(now()))/60) if ns else 9999 %}
{% set dusk = is_state('sun.sun','below_horizon') or (mins >= 0 and mins <= 120) %}
{{ fresh and not dusk and not is_state('binary_sensor.outdoor_raining','on')
   and (states('sensor.jns_lighting_effective_lux') | float(-1)) >=
       ((states('input_number.general_outdoor_lighting_on_lux')|float(2500))
        + (states('input_number.general_lighting_lux_hysteresis')|float(400))) }}"""
    # Preserve 20-minute delay_on.
    req(str(bright.get("delay_on"))!="None","bright-stable delay lost")
    return yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=180).encode()

def patch_environment(raw):
    d=yaml.safe_load(raw)
    rain=find_template_entity(d,"binary_sensor",uid="general_outdoor_raining")
    rain["state"]="""{% set physical = states('sensor.general_garden_rainwater') %}
{% set met = states('weather.forecast_home')|lower %}
{% set om = states('weather.ha_general')|lower %}
{% set rainy = ['rainy','pouring','lightning-rainy','snowy-rainy'] %}
{{ physical == 'raining' or met in rainy or om in rainy }}"""
    rain["availability"]="""{{ states('sensor.general_garden_rainwater') not in ['unknown','unavailable','']
  or states('weather.forecast_home') not in ['unknown','unavailable','']
  or states('weather.ha_general') not in ['unknown','unavailable',''] }}"""
    return yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=180).encode()

def main():
    for p in (AUTO,SYN,ENV): req(p.is_file() and not p.is_symlink(),str(p)+" unavailable")
    old={p:p.read_bytes() for p in (AUTO,SYN,ENV)}
    new={AUTO:patch_controller(old[AUTO]),SYN:patch_synthetic(old[SYN]),ENV:patch_environment(old[ENV])}
    report={
      "automation_id":ID,"tag":TAG,"lux_stale_seconds":300,"dusk_window_minutes":120,
      "weather_sources":["weather.forecast_home","weather.ha_general"],
      "weather_policy":"minimum/conservative factor",
      "rain_sources":["sensor.general_garden_rainwater","weather.forecast_home","weather.ha_general"],
      "files":{str(p):{"before":sha(old[p]),"after":sha(new[p])} for p in old}
    }
    print("JNS_LUX_REPAIR_PLAN "+json.dumps(report,sort_keys=True),flush=True)
    if "--apply" not in sys.argv:return
    req(all(p.read_bytes()==old[p] for p in old),"concurrent config change")
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bkdir=ROOT/".jns-backups"/("lux-weather-dusk-"+stamp)
    bkdir.mkdir(parents=True,mode=0o700,exist_ok=False)
    for p in old:
        bp=bkdir/p.name; bp.write_bytes(old[p]); os.chmod(bp,0o600)
        req(sha(bp.read_bytes())==sha(old[p]),"backup verify failed "+p.name)
    for p in old: atomic(p,new[p])
    req(all(p.read_bytes()==new[p] for p in new),"post-write verify failed")
    report["backup"]=str(bkdir)
    print("JNS_LUX_REPAIR_APPLIED "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("JNS_LUX_REPAIR_BLOCKED "+type(e).__name__+": "+str(e)[:500],flush=True)
        raise SystemExit(2)
