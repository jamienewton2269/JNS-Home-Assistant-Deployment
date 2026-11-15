#!/usr/bin/env python3
from pathlib import Path
import copy,datetime,hashlib,json,os,stat,sys,tempfile,yaml

ROOT=Path("/config")
AUTO=ROOT/"automations.yaml"
PKG=ROOT/"packages/jns_lux_priority_ladder.yaml"
ID="1791918795028"
DINING="light.livingroom_pendant"
TAG="JNS_LUX_DINING_TARGET_V1"

def req(ok,msg):
    if not ok: raise RuntimeError(msg)
def sha(b): return hashlib.sha256(b).hexdigest()
def atomic(path,data):
    st=path.stat()
    fd,tmp=tempfile.mkstemp(prefix=".jns-lux-dining-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.chown(tmp,st.st_uid,st.st_gid)
        os.chmod(tmp,stat.S_IMODE(st.st_mode))
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def patch_pkg(raw):
    d=yaml.safe_load(raw)
    req(isinstance(d,dict),"ladder package shape changed")
    ib=d.setdefault("input_boolean",{})
    inn=d.setdefault("input_number",{})
    if "jns_lux_include_dining" not in ib:
        ib["jns_lux_include_dining"]={
            "name":"Lux Priority - Dining Room enabled",
            "icon":"mdi:ceiling-light",
            "initial":True,
        }
    if "jns_lux_rank_dining" not in inn:
        inn["jns_lux_rank_dining"]={
            "name":"Lux Priority - Dining Room position",
            "min":1,"max":12,"step":1,"initial":9,"mode":"box"
        }
    return yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=180).encode()

def patch_auto(raw):
    d=yaml.safe_load(raw)
    req(isinstance(d,list),"automations root changed")
    hits=[a for a in d if str(a.get("id"))==ID]
    req(len(hits)==1,"Lux controller missing/duplicate")
    a=hits[0]
    req("JNS_LUX_PRIORITY_LADDER_V1" in str(a.get("description","")),"priority controller not current")
    actions=a.get("actions",a.get("action"))
    req(isinstance(actions,list) and actions and isinstance(actions[0].get("variables"),dict),"controller variables missing")
    vars0=actions[0]["variables"]
    template=str(vars0.get("all_eligible",""))
    req("light.0x5c0272fffe400903" in template,"existing Living Room target missing")
    req("light.snug_sofa_led" in template,"existing sofa slot missing")
    if DINING not in template:
        needle="  ('light.snug_sofa_led', 'input_boolean.jns_lux_include_sofa', 'input_number.jns_lux_rank_sofa')"
        repl="  ('light.livingroom_pendant', 'input_boolean.jns_lux_include_dining', 'input_number.jns_lux_rank_dining'),\n"+needle
        req(needle in template,"target list format drifted")
        template=template.replace(needle,repl)
        vars0["all_eligible"]=template

    # Ensure changes to the new helper immediately re-run controller.
    triggers=a.get("triggers",a.get("trigger"))
    state_list=next((t for t in triggers if isinstance(t,dict) and t.get("trigger")=="state" and isinstance(t.get("entity_id"),list)),None)
    req(state_list is not None,"state trigger list missing")
    for eid in ("input_boolean.jns_lux_include_dining","input_number.jns_lux_rank_dining"):
        if eid not in state_list["entity_id"]: state_list["entity_id"].append(eid)

    desc=str(a.get("description",""))
    if TAG not in desc:
        a["description"]=(desc+" "+TAG+
          ": adds dedicated Dining Room target light.livingroom_pendant at independent priority rank; "
          "existing Living Room target remains separate. Disabled legacy FluxLED sofa entity remains excluded by availability/toggle guards.").strip()

    blob=json.dumps(a,default=str)
    for must in ("JNS_LUX_WEATHER_DUSK_REPAIR_V2","input_boolean.jns_lux_include_dining",
                 "input_number.jns_lux_rank_dining","light.0x5c0272fffe400903","light.snug_sofa_led"):
        req(must in blob,"existing/new feature lost: "+must)
    return yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=180).encode()

def main():
    for p in (AUTO,PKG): req(p.is_file() and not p.is_symlink(),str(p)+" missing")
    old={AUTO:AUTO.read_bytes(),PKG:PKG.read_bytes()}
    new={AUTO:patch_auto(old[AUTO]),PKG:patch_pkg(old[PKG])}
    report={"dining_entity":DINING,"rank":9,"files":{str(p):{"before":sha(old[p]),"after":sha(new[p])} for p in old},
            "legacy_sofa_target_enabled":False}
    print("JNS_DINING_LUX_PLAN "+json.dumps(report,sort_keys=True),flush=True)
    if "--apply" not in sys.argv:return
    req(all(p.read_bytes()==old[p] for p in old),"concurrent config change")
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bk=ROOT/".jns-backups"/("lux-dining-"+stamp);bk.mkdir(parents=True,mode=0o700,exist_ok=False)
    for p in old:
        q=bk/p.name;q.write_bytes(old[p]);os.chmod(q,0o600);req(sha(q.read_bytes())==sha(old[p]),"backup failed")
    for p in new:atomic(p,new[p])
    req(all(p.read_bytes()==new[p] for p in new),"write verify failed")
    report["backup"]=str(bk)
    print("JNS_DINING_LUX_APPLIED "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("JNS_DINING_LUX_BLOCKED "+type(e).__name__+": "+str(e)[:500],flush=True)
        raise SystemExit(2)
