#!/usr/bin/env python3
"""Guarded HA-General Lux stale-sensor + west-facing dusk patch.
Changes ONLY automation id 1791918795028 in /config/automations.yaml.
Dry-run by default; --apply writes atomically and creates a verified backup.
"""
from pathlib import Path
import copy,datetime,hashlib,json,os,re,stat,sys,tempfile,yaml

ROOT=Path("/config")
AUTO=ROOT/"automations.yaml"
ID="1791918795028"
TAG="JNS_LUX_STALE_DUSK_V1"
RAW="sensor.0xa4c1383917c90309_illuminance"

def require(ok,msg):
    if not ok: raise RuntimeError(msg)
def sha(b): return hashlib.sha256(b).hexdigest()
def atomic(path,data):
    st=path.stat()
    fd,tmp=tempfile.mkstemp(prefix=".jns-lux-stale-dusk-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.chown(tmp,st.st_uid,st.st_gid)
        os.chmod(tmp,stat.S_IMODE(st.st_mode))
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def patch_controller(raw):
    doc=yaml.safe_load(raw)
    require(isinstance(doc,list),"automations.yaml root changed")
    hits=[x for x in doc if str(x.get("id"))==ID]
    require(len(hits)==1,"shared Lux controller missing/duplicated")
    a=copy.deepcopy(hits[0])
    require("General - Shared Lux Progressive Control" in str(a.get("alias","")),"wrong Lux automation")
    require(TAG not in str(a),"stale/dusk patch already installed")
    require(isinstance(a.get("actions"),list) and len(a["actions"])>=2,"unexpected Lux action layout")
    require(isinstance(a["actions"][0].get("variables"),dict),"Lux controller variables missing")
    controls=a["actions"][0]["variables"]
    require("decision_lux" in controls,"decision_lux missing")
    require("raining" in controls,"raining missing")
    original_decision=controls["decision_lux"]

    rebuilt={}
    for k,v in controls.items():
        if k!="decision_lux":
            rebuilt[k]=v
            continue
        rebuilt["base_decision_lux"]=original_decision
        rebuilt["live_lux_age_seconds"]=(
            "{% set s = states.sensor['0xa4c1383917c90309_illuminance'] "
            "if states.sensor['0xa4c1383917c90309_illuminance'] is defined else none %}\n"
            "{{ (as_timestamp(now()) - as_timestamp(s.last_updated,0)) if s is not none else 999999 }}"
        )
        rebuilt["live_lux_fresh"]=(
            "{{ has_value('sensor.0xa4c1383917c90309_illuminance') "
            "and live_lux_age_seconds|float(999999) <= 300 }}"
        )
        rebuilt["minutes_to_sunset"]=(
            "{% set ns = state_attr('sun.sun','next_setting') %}\n"
            "{{ ((as_timestamp(as_datetime(ns),0) - as_timestamp(now())) / 60) if ns else 9999 }}"
        )
        rebuilt["dusk_lock"]=(
            "{{ is_state('sun.sun','below_horizon') or "
            "(minutes_to_sunset|float(9999) >= 0 and minutes_to_sunset|float(9999) <= 120) }}"
        )
        rebuilt["dusk_cap_lux"]=(
            "{% set base = states('input_number.general_outdoor_lighting_on_lux')|float(2500) %}\n"
            "{% set mins = minutes_to_sunset|float(9999) %}\n"
            "{% if is_state('sun.sun','below_horizon') %}100"
            "{% elif mins <= 0 %}100"
            "{% elif mins < 120 %}{{ [100, base * (mins / 120)] | max }}"
            "{% else %}99999{% endif %}"
        )
        rebuilt["decision_lux"]=(
            "{% set base = base_decision_lux|float(99999) %}\n"
            "{% if dusk_lock|bool %}"
            "{{ [base, dusk_cap_lux|float(99999)] | min }}"
            "{% else %}{{ base }}{% endif %}"
        )
    a["actions"][0]["variables"]=rebuilt

    repeat=a["actions"][1].get("repeat")
    require(isinstance(repeat,dict),"Lux repeat block missing")
    seq=repeat.get("sequence")
    require(isinstance(seq,list) and seq,"Lux repeat sequence missing")
    varstep=next((x for x in seq if isinstance(x,dict) and isinstance(x.get("variables"),dict)),None)
    require(varstep is not None,"per-light variable step missing")
    v=varstep["variables"]
    require("safe_off" in v,"per-light safe_off missing")
    require("jns_lux_priority_bright_stable" in str(v["safe_off"]),"unexpected safe_off guard")
    v["safe_off"]=(
        "{{ is_state('binary_sensor.jns_lux_priority_bright_stable','on') "
        "and live_lux_fresh|bool "
        "and not dusk_lock|bool "
        "and not raining|bool "
        "and is_state(e,'on') "
        "and decision_lux|float >= (start_lux|float + "
        "states('input_number.general_lighting_lux_hysteresis')|float(400)) }}"
    )

    desc=str(a.get("description","")).strip()
    a["description"]=(desc+" "+TAG+
        ": raw lux >5 min old cannot authorize OFF; within 120 min of sunset "
        "decision lux is capped progressively toward darkness; after sunset automatic OFF remains blocked.").strip()

    # Replace exactly one YAML block and verify unrelated automations are byte-semantic unchanged.
    text=raw.decode("utf-8")
    pat=r"(?m)^- id: ['\"]?"+re.escape(ID)+r"['\"]?[ \t]*$"
    mm=list(re.finditer(pat,text))
    require(len(mm)==1,"cannot isolate Lux automation YAML")
    start=mm[0].start()
    nxt=re.search(r"(?m)^- id:",text[mm[0].end():])
    end=mm[0].end()+nxt.start() if nxt else len(text)
    block=yaml.safe_dump([a],sort_keys=False,allow_unicode=True,width=160)
    modified=(text[:start]+block+text[end:]).encode()
    newdoc=yaml.safe_load(modified)
    old_other=[x for x in doc if str(x.get("id"))!=ID]
    new_other=[x for x in newdoc if str(x.get("id"))!=ID]
    require(old_other==new_other,"unrelated automations changed")
    require([x for x in newdoc if str(x.get("id"))==ID]==[a],"patched controller semantic mismatch")
    return modified

def main():
    require(AUTO.is_file() and not AUTO.is_symlink(),"automations.yaml unavailable/symlink")
    old=AUTO.read_bytes()
    new=patch_controller(old)
    report={
        "target_vm":905,
        "automation_id":ID,
        "before_sha256":sha(old),
        "after_sha256":sha(new),
        "raw_lux_entity":RAW,
        "stale_seconds":300,
        "dusk_window_minutes":120,
        "automatic_off_blocked_when_stale":True,
        "automatic_off_blocked_during_dusk_and_night":True,
        "unrelated_automations_modified":False,
    }
    print("JNS_LUX_STALE_DUSK_PLAN "+json.dumps(report,sort_keys=True),flush=True)
    if "--apply" not in sys.argv: return
    require(AUTO.read_bytes()==old,"concurrent automations.yaml change")
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup=ROOT/".jns-backups"/("lux-stale-dusk-"+stamp)
    backup.mkdir(parents=True,mode=0o700,exist_ok=False)
    bp=backup/"automations.yaml"
    bp.write_bytes(old); os.chmod(bp,0o600)
    require(sha(bp.read_bytes())==sha(old),"backup verification failed")
    atomic(AUTO,new)
    require(AUTO.read_bytes()==new,"post-write verification failed")
    report["backup"]=str(backup)
    print("JNS_LUX_STALE_DUSK_APPLIED "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    try: main()
    except Exception as e:
        print("JNS_LUX_STALE_DUSK_BLOCKED "+type(e).__name__+": "+str(e)[:400],flush=True)
        raise SystemExit(2)
