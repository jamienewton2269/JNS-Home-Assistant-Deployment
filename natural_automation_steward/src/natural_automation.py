#!/usr/bin/env python3
import json, hashlib, os, subprocess, time, threading, uuid
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import sys
sys.path.insert(0,"/opt/real-progress")
from real_progress import ProgressModel, JobTracker
from steward.store import StewardStore
from steward.writer import apply_automation, ApplyError

VMID=int(os.environ.get('NA_VMID','905'))
ROOT=Path("/opt/natural-automation")
DATA=ROOT/"data"; DATA.mkdir(parents=True,exist_ok=True)
AUDIT=DATA/"changes.jsonl"
ALIASES=DATA/"aliases.json"
REMOVALS=DATA/"removal_proposals.json"
HOUSEKEEPING=DATA/"housekeeping.json"
PROGRESS_STATS=DATA/"progress_stats.json"
STEWARD=StewardStore(DATA/"steward.db")
ENABLE_APPLY=os.environ.get("NA_ENABLE_APPLY","0")=="1"
AUDIT_LOCK=threading.Lock()
REMOVAL_LOCK=threading.Lock()
HOUSEKEEPING_LOCK=threading.Lock()
PROGRESS_MODEL=ProgressModel(PROGRESS_STATS,defaults={
    "Parsing language":0.05,
    "Reading Home Assistant inventory and automations":3.0,
    "Resolving target device":0.08,
    "Scanning existing automations":0.05,
    "Evaluating conflicts and coverage":0.03,
    "Writing audit record":0.03,
},stall_multiplier=3.0,stall_min_seconds=5.0)
JOB_TRACKER=JobTracker(PROGRESS_MODEL)

def qga_python(code, timeout=40):
    p=subprocess.run(["qm","guest","exec",str(VMID),"--","docker","exec","homeassistant",
        "python3","-c",code],capture_output=True,text=True,timeout=timeout,check=True)
    r=json.loads(p.stdout)
    if r.get("exitcode")!=0: raise RuntimeError(r.get("err-data") or "guest command failed")
    return r.get("out-data","")

def audit(event, **extra):
    with AUDIT_LOCK:
        prev=None
        if AUDIT.exists():
            lines=[x for x in AUDIT.read_text().splitlines() if x.strip()]
            if lines: prev=json.loads(lines[-1]).get("entry_hash")
        e={"ts":time.time(),"event":event,"previous_hash":prev,**extra}
        raw=json.dumps(e,sort_keys=True,separators=(",",":"))
        e["entry_hash"]=hashlib.sha256(raw.encode()).hexdigest()
        with AUDIT.open("a") as f: f.write(json.dumps(e,sort_keys=True)+"\n")
def load_aliases():
    if not ALIASES.exists(): return {}
    try: return json.loads(ALIASES.read_text())
    except Exception: return {}

def save_alias(phrase, entity_id):
    a=load_aliases(); a[" ".join(phrase.lower().split())]=entity_id
    ALIASES.write_text(json.dumps(a,indent=2,sort_keys=True))
    audit("alias_confirmed",phrase=phrase,entity_id=entity_id)

def ha_snapshot():
    code="""import json,yaml,os
autos=[]
for f in ['/config/automations.yaml','/config/natural_automation.yaml']:
    if not os.path.exists(f): continue
    raw=yaml.safe_load(open(f)) or []
    for x in raw:
        if isinstance(x,dict):
            x=dict(x); x['_source']=os.path.basename(f); autos.append(x)
print(json.dumps({'automations':autos},separators=(',',':'),default=str))"""
    try:
        live=json.loads(qga_python(code))
        live_ok=True
        live_warning=None
    except Exception as exc:
        live={'automations':[]}
        live_ok=False
        live_warning=f"{type(exc).__name__}: {exc}"
    fixture=DATA/"device_fixture.json"
    if fixture.exists():
        meta=json.loads(fixture.read_text())
        return {'entities':meta.get('entities',[]),'devices':meta.get('devices',[]),'areas':meta.get('areas',[]),
                'automations':live.get('automations',[]),'live_automation_available':live_ok,'live_warning':live_warning}
    return {'entities':[],'devices':[],'areas':[],'automations':live.get('automations',[]),
            'live_automation_available':live_ok,'live_warning':live_warning}

def inventory():
    snap=ha_snapshot()
    return {'entities':snap['entities'],'devices':snap['devices'],'areas':snap['areas']}

def automations():
    return ha_snapshot()['automations']

def controller_role(cfg):
    s=json.dumps(cfg).lower()
    on=('turn_on' in s); off=('turn_off' in s)
    if on and not off: return 'on'
    if off and not on: return 'off'
    return 'mixed'

def friendly(entity):
    return (entity.get("name") or entity.get("original_name") or entity.get("entity_id") or "")

def candidates(phrase, inv=None):
    inv=inv or inventory(); aliases=load_aliases(); key=" ".join(phrase.lower().split())
    if key in aliases:
        eid=aliases[key]
        return [{"entity_id":eid,"name":eid,"score":1.0}]
    p=phrase.lower()
    compact="".join(ch for ch in p if ch.isalnum())
    devices={d.get("id"):d for d in inv["devices"]}
    out=[]
    for e in inv["entities"]:
        eid=e.get("entity_id",""); n=friendly(e)
        if eid.split(".",1)[0] not in ("switch","light","fan","input_boolean"): continue
        base=eid.split(".",1)[-1].replace("_"," ")
        dev=devices.get(e.get("device_id")) or {}
        devname=dev.get("name_by_user") or dev.get("name") or ""
        labels=[n,base,devname]
        score=max(SequenceMatcher(None,p,str(x).lower()).ratio() for x in labels if x)
        for x in labels:
            c="".join(ch for ch in str(x).lower() if ch.isalnum())
            if c and (c in compact or compact in c): score=max(score,0.92)
            elif "waterfeature" in c and "waterfeature" in compact: score=max(score,0.96)
        out.append({"entity_id":eid,"name":n or devname or eid,"score":round(score,3)})
    return sorted(out,key=lambda x:x["score"],reverse=True)[:5]
def entity_details(inv, entity_id):
    e=next((x for x in inv["entities"] if x.get("entity_id")==entity_id),None) or {}
    devices={d.get("id"):d for d in inv["devices"]}
    areas={a.get("id"):a.get("name") for a in inv["areas"]}
    dev=devices.get(e.get("device_id")) or {}
    area_id=e.get("area_id") or dev.get("area_id")
    return {
        "entity_id":entity_id,
        "domain":entity_id.split(".",1)[0] if "." in entity_id else "",
        "name":friendly(e) or dev.get("name_by_user") or dev.get("name") or entity_id,
        "area":areas.get(area_id) if area_id else None,
    }

def infer_role(details):
    text=(details.get("name","")+" "+details.get("entity_id","").replace("_"," ")).lower()
    domain=details.get("domain","")
    if any(x in text for x in ("extractor","extract fan","vent fan")): return "fan"
    if any(x in text for x in ("pump","water feature","pond pump")): return "pump"
    if any(x in text for x in ("heater","radiator","heating")) and "light" not in text: return "heater"
    if any(x in text for x in ("light","lamp","bulb","pendant","ceiling","sconce","strip","downlight","spotlight")): return "light"
    if domain=="fan": return "fan"
    if domain=="light": return "light"
    if domain=="switch": return "switch"
    return domain

def multi_candidates(category, inv, first_entity_id=None):
    wanted_role={"lights":"light","light":"light","switches":"switch","switch":"switch","fans":"fan","fan":"fan"}.get(category)
    first=entity_details(inv,first_entity_id) if first_entity_id else None
    if first: wanted_role=infer_role(first)
    out=[]
    for e in inv["entities"]:
        eid=e.get("entity_id","")
        if "." not in eid: continue
        domain=eid.split(".",1)[0]
        if domain not in ("light","switch","fan","input_boolean"): continue
        d=entity_details(inv,eid)
        role=infer_role(d)
        if wanted_role and role!=wanted_role: continue
        d["role"]=role
        score=1.0
        reason=f"same inferred {role} role"
        if domain==role: score+=0.25
        if first and first.get("area") and d.get("area")==first.get("area"):
            score+=2.0; reason=f"same {role} role and same area ({d['area']})"
        d["score"]=score; d["match_reason"]=reason
        out.append(d)
    out.sort(key=lambda x:(-x["score"],(x.get("area") or ""),x["name"].lower()))
    return out[:40]

def config_mentions_target(cfg, entity_id, inv):
    blob=json.dumps(cfg).lower()
    if entity_id.lower() in blob: return True
    # UI device actions often store registry entity UUID rather than entity_id.
    er=next((e for e in inv["entities"] if e.get("entity_id")==entity_id),None)
    if er and str(er.get("id","")).lower() in blob: return True
    if er and er.get("device_id") and str(er["device_id"]).lower() in blob: return True
    return False

def analyse(text, progress=None):
    if progress: progress("Parsing language")
    low=" ".join(text.lower().split()).strip()
    if not low:
        return {"action":"error","error":"Nothing was entered.","suggestion":"Describe what you want Home Assistant to do in ordinary language."}

    aliases=load_aliases()
    remembered_phrase=next((a for a in sorted(aliases,key=len,reverse=True) if a in low),None)
    if remembered_phrase:
        target=remembered_phrase
    else:
        target=low
        for prefix in ("please ","can you ","could you ","i want you to ","i would like you to "):
            if target.startswith(prefix): target=target[len(prefix):]
        for prefix in ("set the ","set ","run the ","run ","turn the ","turn ","switch the ","switch "):
            if target.startswith(prefix): target=target[len(prefix):]; break
        stops=(" to run "," from "," on at "," off at "," on from "," off from "," every "," everyday"," daily"," at "," when "," until "," till ")
        cut=len(target)
        for marker in stops:
            pos=target.find(marker)
            if pos>0: cut=min(cut,pos)
        target=target[:cut].strip(" ,.!?")

    if not target:
        return {"action":"error","error":"I could not identify the device or thing you want to control.",
                "suggestion":"Try naming the device, for example: turn the garden water feature off at bedtime."}

    timing=[]
    for word in ("sunrise","sunset","bedtime","midnight","noon"):
        if word in low: timing.append(word)
    import re
    timing += re.findall(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b",low)
    if progress: progress("Reading Home Assistant inventory and automations")
    snap=ha_snapshot()
    inv={"entities":snap["entities"],"devices":snap["devices"],"areas":snap["areas"]}
    if progress: progress("Resolving target device")
    multi_category=next((x for x in ("lights","switches","fans") if x in low),None)
    multi_requested=bool(multi_category and re.search(r"\b(all|multiple|several|these|those)\b",low))
    if multi_requested:
        cs=multi_candidates(multi_category,inv)
        logic=[
            f'Detected a multiple-device request for {multi_category}.',
            f'Found {len(cs)} compatible {multi_category} in the static test inventory.',
            'Select one or more devices. After the first selection, the list is re-ranked by matching semantic role and area.',
        ]
        if snap.get("live_automation_available"):
            logic.append('HA Lite automation inspection is available for this test.')
        else:
            logic.append('HA Lite automation inspection is temporarily unavailable; device-language testing is continuing from the static fixture only.')
        logic.append('No Home Assistant changes have been made.')
        audit("multi_device_selection",request=text,category=multi_category,candidates=len(cs),logic=logic)
        return {"action":"select_devices","selection_mode":"multiple","request":text,
                "category":multi_category,"target_phrase":multi_category,
                "candidates":cs,"logic":logic}
    cs=candidates(target, inv)
    if not cs: return {"action":"clarify","target_phrase":target,"candidates":[]}
    remembered=load_aliases().get(" ".join(target.lower().split()))
    if not remembered and (len(cs)>1 and (cs[0]["score"]<0.78 or cs[0]["score"]-cs[1]["score"]<0.12)):
        audit("clarify",request=text,target_phrase=target,candidates=cs)
        return {"action":"clarify","target_phrase":target,"candidates":cs}
    chosen=cs[0]
    if progress: progress("Scanning existing automations")
    ctrls=[]
    for a in snap["automations"]:
        if config_mentions_target(a,chosen["entity_id"],inv):
            ctrls.append({"id":str(a.get("id","")),"alias":a.get("alias","Unnamed"),
                          "source":a.get("_source","unknown"),"role":controller_role(a),"config":a})
    if progress: progress("Evaluating conflicts and coverage")
    roles=[c["role"] for c in ctrls]
    managed=any(c["source"]=="natural_automation.yaml" for c in ctrls)
    if managed and "on" in roles and "off" in roles:
        action="covered_with_legacy_fallback"
    else:
        action="conflict" if len(ctrls)>1 else ("modify" if len(ctrls)==1 else "create")
    logic=[
        f'Interpreted target phrase as "{target}".',
        f'Resolved it to {chosen["entity_id"]} with confidence {chosen["score"]}.',
        f'Inspected {len(ctrls)} existing controller(s) that reference the target.',
    ]
    if timing:
        logic.append('Detected timing language: ' + ', '.join(dict.fromkeys(timing)) + '.')
    if remembered:
        logic.append('Used the remembered human alias for this device.')
    if action=="covered_with_legacy_fallback":
        logic.append('Found both ON and OFF coverage, including a Natural Automation managed rule; legacy OFF remains as fallback.')
    elif action=="conflict":
        logic.append('Multiple independent controllers exist, so no new automation is proposed.')
    elif action=="modify":
        logic.append('One existing controller exists; modification should be reviewed instead of creating a duplicate.')
    else:
        logic.append('No existing controller was found; a new standard Home Assistant automation could be proposed.')
    logic.append('Home Assistant write gate is disabled.' if not ENABLE_APPLY else 'Controlled apply gate is enabled.')
    result={"action":action,"request":text,"target_phrase":target,"target":chosen,
            "controllers":ctrls,"apply_enabled":ENABLE_APPLY,"logic":logic}
    if progress: progress("Writing audit record")
    audit("analyse",request=text,target=chosen,action=action,logic=logic,
          controllers=[{"id":c["id"],"alias":c["alias"],"source":c["source"],"role":c["role"]} for c in ctrls])
    return result

def planned_stages_for_text(text):
    low=" ".join(str(text).lower().split())
    import re
    multi_category=next((x for x in ("lights","switches","fans") if x in low),None)
    multi_requested=bool(multi_category and re.search(r"\b(all|multiple|several|these|those)\b",low))
    base=["Parsing language","Reading Home Assistant inventory and automations","Resolving target device"]
    if multi_requested:
        return base
    return base+["Scanning existing automations","Evaluating conflicts and coverage","Writing audit record"]

def start_analysis_job(text):
    job_id=JOB_TRACKER.start(
        planned_stages_for_text(text),
        metadata={"request":text,"consumer":"Natural Automation"},
    )
    def worker():
        try:
            result=analyse(text, lambda stage:JOB_TRACKER.stage(job_id,stage))
            JOB_TRACKER.finish(job_id,result=result)
        except Exception as exc:
            message=f"{type(exc).__name__}: {exc}"
            audit("error",request=text,error=message)
            JOB_TRACKER.fail(job_id,message)
    threading.Thread(target=worker,daemon=True,name=f"na-{job_id[:8]}").start()
    return job_id

def job_view(job_id):
    return JOB_TRACKER.view(job_id)

def refine_multi_candidates(category, first_entity_id):
    snap=ha_snapshot()
    inv={"entities":snap["entities"],"devices":snap["devices"],"areas":snap["areas"]}
    first=entity_details(inv,first_entity_id)
    return {
        "ok":True,
        "first":first,
        "candidates":multi_candidates(category,inv,first_entity_id),
        "logic":[
            f'First selected device: {first["name"]} ({first_entity_id}).',
            f'Re-ranked remaining choices to the inferred {infer_role(first)} role.',
            (f'Prioritised devices in the same area: {first["area"]}.' if first.get("area") else 'No Home Assistant area is assigned to the first device, so semantic role matching is used.'),
        ],
    }

def interpret_change_request(request_text, category):
    low=" ".join(request_text.lower().split())
    intent={
        "target_role": category.rstrip("s") if category else None,
        "operation": "inspect_or_adjust",
        "source_reference": None,
        "metric": None,
        "trigger_relationship": None,
        "requested_direction": None,
        "threshold_effect": None,
        "condition_context": None,
        "magnitude": None,
        "assumptions": [],
        "unresolved": [],
    }

    if "low light" in low or "light level" in low or "lux" in low:
        intent["metric"]="illuminance / light level"
    if "rain sensor" in low:
        intent["source_reference"]="outdoor rain sensor"
    elif "outdoor sensor" in low:
        intent["source_reference"]="outdoor sensor"

    if any(x in low for x in ("turn on","come on","comes on")):
        intent["operation"]="adjust_turn_on_logic" if any(x in low for x in ("adjust","change","earlier","later")) else "inspect_turn_on_logic"

    if any(x in low for x in ("low light","below","dark","dull")):
        intent["trigger_relationship"]="turn on when light level falls below a threshold"

    if "earlier" in low:
        intent["requested_direction"]="earlier"
        if intent["trigger_relationship"]:
            intent["threshold_effect"]="raise the illuminance threshold so the rule becomes true while it is still slightly brighter"
            intent["assumptions"].append("This threshold direction is valid only if the existing rule turns lights on when illuminance falls below a numeric threshold.")
    elif "later" in low:
        intent["requested_direction"]="later"
        if intent["trigger_relationship"]:
            intent["threshold_effect"]="lower the illuminance threshold so the rule becomes true only when it is darker"
            intent["assumptions"].append("This threshold direction is valid only if the existing rule turns lights on when illuminance falls below a numeric threshold.")

    if "dull day" in low or "dull days" in low:
        intent["condition_context"]="dull day"
    elif "cloudy" in low or "overcast" in low:
        intent["condition_context"]="cloudy / overcast"

    if any(x in low for x in ("a little","slightly","bit earlier","bit later")):
        intent["magnitude"]="small adjustment requested; exact numeric amount not specified"

    if not intent["source_reference"]:
        intent["unresolved"].append("Which Home Assistant sensor supplies the light-level reading.")
    else:
        intent["unresolved"].append(f'Confirm which entity corresponds to "{intent["source_reference"]}".')
    if intent["metric"] and intent["operation"]=="adjust_turn_on_logic":
        intent["unresolved"].append("The current numeric light-level threshold.")
    if intent["magnitude"]:
        intent["unresolved"].append("The exact threshold change to apply.")
    intent["unresolved"].append("Whether the selected devices share one controller or use separate automations.")

    return intent

def confirm_multi_selection(request_text, category, selected):
    selected=[str(x) for x in selected if x]
    if not selected: raise ValueError("Select at least one device.")
    snap=ha_snapshot()
    inv={"entities":snap["entities"],"devices":snap["devices"],"areas":snap["areas"]}
    valid={e.get("entity_id") for e in inv["entities"]}
    missing=[x for x in selected if x not in valid]
    if missing: raise ValueError("One or more selected devices no longer exist: "+", ".join(missing))
    details=[entity_details(inv,x) for x in selected]
    intent=interpret_change_request(request_text,category)
    logic=[
        f'Confirmed a multiple-device selection containing {len(selected)} device(s).',
        'Selected devices: '+", ".join(d["name"] for d in details)+'.',
        f'Interpreted requested operation as {intent["operation"].replace("_"," ")}.',
    ]
    if intent.get("metric"):
        logic.append('Detected control metric: '+intent["metric"]+'.')
    if intent.get("source_reference"):
        logic.append('Detected source reference: '+intent["source_reference"]+'.')
    if intent.get("requested_direction"):
        logic.append('Requested direction: '+intent["requested_direction"]+'.')
    if intent.get("threshold_effect"):
        logic.append('Conditional threshold interpretation: '+intent["threshold_effect"]+'.')
    if intent.get("condition_context"):
        logic.append('Context condition: '+intent["condition_context"]+'.')
    logic.append('Unresolved items are shown separately and must be confirmed before any proposal can be considered executable.')
    logic.append('No Home Assistant changes have been made.')
    audit("multi_selection_confirmed",request=request_text,category=category,selected=selected,intent=intent,logic=logic)
    return {"ok":True,"action":"multi_selection_confirmed","request":request_text,
            "category":category,"selected":details,"intent":intent,"logic":logic}

def _walk_entity_refs(value, refs):
    if isinstance(value,dict):
        for k,v in value.items():
            if k=="entity_id":
                if isinstance(v,str): refs.add(v)
                elif isinstance(v,list):
                    refs.update(str(x) for x in v if isinstance(x,str))
            _walk_entity_refs(v,refs)
    elif isinstance(value,list):
        for v in value: _walk_entity_refs(v,refs)

def automation_entity_refs(cfg):
    refs=set()
    _walk_entity_refs(cfg,refs)
    return sorted(refs)

def canonical_automation(cfg):
    clean={k:v for k,v in cfg.items() if k not in ("id","alias","description","_source")}
    return json.dumps(clean,sort_keys=True,separators=(",",":"),default=str)

def scan_housekeeping(snapshot=None):
    snap=snapshot or ha_snapshot()
    autos=snap.get("automations",[])
    existing={e.get("entity_id") for e in snap.get("entities",[]) if e.get("entity_id")}
    suggestions=[]
    now=time.time()

    # Exact duplicate functional logic.
    by_hash={}
    for a in autos:
        h=hashlib.sha256(canonical_automation(a).encode()).hexdigest()
        by_hash.setdefault(h,[]).append(a)
    for h,group in by_hash.items():
        if len(group)<2: continue
        names=[x.get("alias","Unnamed") for x in group]
        for a in group[1:]:
            suggestions.append({
                "suggestion_id":uuid.uuid4().hex,
                "created":now,
                "kind":"duplicate_logic",
                "confidence":"high",
                "controller_id":str(a.get("id","")),
                "source":a.get("_source","unknown"),
                "alias":a.get("alias","Unnamed"),
                "reason":"This automation is functionally identical to another automation after ignoring ID/name/description.",
                "evidence":{"matching_automations":names,"logic_hash":h},
                "recommended_action":"Review and consider removing the duplicate if it is not intentionally retained as a fallback.",
                "status":"suggested",
            })

    # Multiple controllers with the same target + same role.
    groups={}
    for a in autos:
        refs=[r for r in automation_entity_refs(a) if r.startswith(("light.","switch.","fan.","input_boolean."))]
        role=controller_role(a)
        for ref in refs:
            groups.setdefault((ref,role),[]).append(a)
    for (ref,role),group in groups.items():
        if len(group)<2: continue
        names=[x.get("alias","Unnamed") for x in group]
        for a in group:
            suggestions.append({
                "suggestion_id":uuid.uuid4().hex,
                "created":now,
                "kind":"multiple_same_role_controllers",
                "confidence":"medium",
                "controller_id":str(a.get("id","")),
                "source":a.get("_source","unknown"),
                "alias":a.get("alias","Unnamed"),
                "reason":f"{len(group)} automations reference {ref} with the same inferred role ({role}).",
                "evidence":{"target":ref,"role":role,"controllers":names},
                "recommended_action":"Review whether these routines overlap, are obsolete, or represent intentional layered behaviour.",
                "status":"suggested",
            })

    # References to missing controllable entities.
    for a in autos:
        missing=[r for r in automation_entity_refs(a)
                 if r.startswith(("light.","switch.","fan.")) and r not in existing]
        if missing:
            suggestions.append({
                "suggestion_id":uuid.uuid4().hex,
                "created":now,
                "kind":"missing_target_entity",
                "confidence":"high",
                "controller_id":str(a.get("id","")),
                "source":a.get("_source","unknown"),
                "alias":a.get("alias","Unnamed"),
                "reason":"This automation references one or more controllable entities not present in the current test inventory.",
                "evidence":{"missing_entities":missing},
                "recommended_action":"Confirm the entity was removed/renamed. If so, repair or retire the automation.",
                "status":"suggested",
            })

    # Deduplicate identical suggestion/controller/kind pairs.
    unique={}
    for s in suggestions:
        key=(s["kind"],s["controller_id"],s["source"],json.dumps(s["evidence"],sort_keys=True))
        unique[key]=s
    result=list(unique.values())
    previous=load_housekeeping()
    old_by_fp={x.get("fingerprint"):x for x in previous if x.get("fingerprint")}
    for s in result:
        fp=hashlib.sha256(json.dumps({
            "kind":s["kind"],"controller_id":s["controller_id"],"source":s["source"],"evidence":s["evidence"]
        },sort_keys=True,separators=(",",":")).encode()).hexdigest()
        s["fingerprint"]=fp
        old=old_by_fp.get(fp)
        if old:
            s["suggestion_id"]=old.get("suggestion_id",s["suggestion_id"])
            s["status"]=old.get("status",s["status"])
            for key in ("review_note","reviewed","removal_proposal_id"):
                if key in old: s[key]=old[key]
    with HOUSEKEEPING_LOCK:
        tmp=HOUSEKEEPING.with_suffix(".tmp")
        tmp.write_text(json.dumps(result,indent=2,sort_keys=True))
        os.replace(tmp,HOUSEKEEPING)
    audit("housekeeping_scan",suggestions=len(result),
          counts={k:sum(1 for s in result if s["kind"]==k) for k in sorted({s["kind"] for s in result})},
          live_automation_available=snap.get("live_automation_available",False))
    return result

def load_housekeeping():
    with HOUSEKEEPING_LOCK:
        if not HOUSEKEEPING.exists(): return []
        try: return json.loads(HOUSEKEEPING.read_text())
        except Exception: return []

def review_housekeeping(suggestion_id, decision):
    items=load_housekeeping()
    item=next((x for x in items if x.get("suggestion_id")==suggestion_id),None)
    if not item: raise ValueError("Housekeeping suggestion not found.")
    if decision=="keep":
        item["status"]="kept"
        item["review_note"]="Admin chose to keep this automation."
    elif decision=="dismiss":
        item["status"]="dismissed"
        item["review_note"]="Suggestion dismissed; no Home Assistant change made."
    elif decision=="propose_removal":
        proposal=propose_removal(item.get("controller_id",""),item.get("source",""),item.get("alias",""))
        item["status"]="removal_proposed"
        item["removal_proposal_id"]=proposal.get("proposal_id")
        item["review_note"]="Removal proposal created for separate admin approval."
    else:
        raise ValueError("Decision must be keep, dismiss, or propose_removal.")
    item["reviewed"]=time.time()
    with HOUSEKEEPING_LOCK:
        tmp=HOUSEKEEPING.with_suffix(".tmp")
        tmp.write_text(json.dumps(items,indent=2,sort_keys=True))
        os.replace(tmp,HOUSEKEEPING)
    audit("housekeeping_review",suggestion_id=suggestion_id,decision=decision,
          status=item["status"],controller_id=item.get("controller_id"),
          alias=item.get("alias"),source=item.get("source"),logic=[item.get("review_note","")])
    return item

def load_removals():
    with REMOVAL_LOCK:
        if not REMOVALS.exists(): return []
        try: return json.loads(REMOVALS.read_text())
        except Exception: return []

def save_removals(items):
    with REMOVAL_LOCK:
        tmp=REMOVALS.with_suffix(".tmp")
        tmp.write_text(json.dumps(items,indent=2,sort_keys=True))
        os.replace(tmp,REMOVALS)

def propose_removal(controller_id, source, alias):
    snap=ha_snapshot()
    found=next((a for a in snap["automations"] if str(a.get("id",""))==str(controller_id) and a.get("_source")==source),None)
    if not found: raise ValueError("That automation is no longer present; refresh and analyse again.")
    existing=next((x for x in load_removals() if x.get("controller_id")==controller_id and x.get("source")==source and x.get("status") in ("pending_review","approved_waiting_write_gate")),None)
    if existing:
        return {"ok":True,"proposal_id":existing["proposal_id"],"status":existing["status"],"logic":existing["logic"]}
    proposal_id=uuid.uuid4().hex
    logic=[
        f'Removal proposed for "{alias or found.get("alias","Unnamed")}".',
        f'Automation ID: {controller_id}; source: {source}.',
        'The proposal is pending admin review.',
        'No automation has been deleted or disabled.',
    ]
    item={"proposal_id":proposal_id,"created":time.time(),"status":"pending_review",
          "controller_id":controller_id,"source":source,"alias":alias or found.get("alias","Unnamed"),
          "logic":logic}
    items=load_removals(); items.append(item); save_removals(items)
    audit("removal_proposal",**item,write_gate=ENABLE_APPLY)
    return {"ok":True,"proposal_id":proposal_id,"status":"pending_review","logic":logic}

def review_removal(proposal_id, decision):
    items=load_removals()
    item=next((x for x in items if x.get("proposal_id")==proposal_id),None)
    if not item: raise ValueError("Removal proposal not found.")
    if item.get("status")!="pending_review": return item
    if decision=="approve":
        item["status"]="approved_waiting_write_gate"
        item["review_logic"]=[
            "Admin approved this automation for removal.",
            "The Home Assistant write gate is still disabled.",
            "No deletion has occurred; the proposal is queued for a later controlled apply step.",
        ]
    elif decision=="reject":
        item["status"]="rejected"
        item["review_logic"]=["Admin rejected this removal proposal. No change was made."]
    else:
        raise ValueError("Decision must be approve or reject.")
    item["reviewed"]=time.time()
    save_removals(items)
    audit("removal_review",proposal_id=proposal_id,decision=decision,status=item["status"],
          controller_id=item["controller_id"],source=item["source"],alias=item["alias"],
          logic=item.get("review_logic",[]),write_gate=ENABLE_APPLY)
    return item

HTML="""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Natural Automation</title><style>
:root{--vy-bg:#05080c;--vy-panel:#0b1118;--vy-line:#203448;--vy-text:#e8f4ff;--vy-muted:#8da3b5;--vy-blue:#5bbcff;--vy-green:#83e6b4;--vy-amber:#ffc857;--vy-red:#ff6b6b}
body{font-family:system-ui;margin:0;background:var(--vy-bg);color:var(--vy-text)}.w{max-width:1500px;margin:28px auto;padding:0 18px}
.layout{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(380px,.8fr);gap:18px;align-items:start}
.maincol,.admincol{min-width:0}.admincol{position:sticky;top:18px;max-height:calc(100vh - 36px);overflow:auto}
@media(max-width:1050px){.layout{grid-template-columns:1fr}.admincol{position:static;max-height:none}}
.card{background:#191919;border:1px solid #333;border-radius:14px;padding:20px;margin:16px 0}
.admincard{background:#151515;border:1px solid #2f3b47;border-radius:14px;padding:16px;margin:12px 0}
.adminhead{display:flex;justify-content:space-between;gap:10px;align-items:center;position:sticky;top:0;background:#111;padding:6px 0 10px;z-index:2}
.adminhead h2{margin:0}.badge{font-size:.8rem;border:1px solid #555;border-radius:999px;padding:4px 8px;color:#bbb}
.audit-event{border-top:1px solid #2d2d2d;padding:10px 0}.audit-event:first-child{border-top:0}
textarea{width:100%;box-sizing:border-box;min-height:110px;background:#0e0e0e;color:#eee;border:1px solid #444;border-radius:10px;padding:12px}
button{padding:10px 14px;border-radius:9px;border:0;margin:8px 8px 0 0}.muted{color:#aaa}pre{white-space:pre-wrap;background:#0d0d0d;padding:14px;border-radius:10px;overflow:auto}
.cand{display:block;width:100%;text-align:left;background:#292929;color:#eee;border:1px solid #444}
.error{border:2px solid #d84b4b;background:#2a1111;color:#ffdede}.error h3{margin-top:0;color:#ff8f8f}
.progress{border:1px solid var(--vy-line);background:var(--vy-panel)}.progress h3{margin:0 0 8px}.stage{padding:5px 0}.done{color:var(--vy-green)}.active{color:var(--vy-blue);font-weight:700}.stage-time{color:var(--vy-muted);margin-left:8px}.remove{background:#4b2626;color:#ffdede;border:1px solid #7b3b3b;font-size:.9rem;padding:6px 9px;margin-left:8px}.progressbar{height:18px;background:var(--vy-bg);border:1px solid var(--vy-line);border-radius:999px;overflow:hidden;margin:12px 0 8px}.progressfill{height:100%;width:0%;background:linear-gradient(90deg,var(--vy-blue),var(--vy-green));transition:width .18s linear}.progressmeta{display:flex;justify-content:space-between;gap:10px;font-size:.9rem;color:var(--vy-muted);flex-wrap:wrap}.progresspct{font-weight:700;color:var(--vy-text)}.progressstate{font-size:.78rem;letter-spacing:.08em;color:var(--vy-blue)}.state-stalled{border-color:var(--vy-amber)}.state-stalled .progressfill{background:var(--vy-amber)}.state-stalled .progressstate{color:var(--vy-amber)}.state-error{border-color:var(--vy-red)}.state-error .progressfill{background:var(--vy-red)}.state-error .progressstate{color:var(--vy-red)}.state-done .progressstate{color:var(--vy-green)}.stallnote{margin-top:10px;padding:10px 12px;border:1px solid var(--vy-amber);border-radius:9px;color:#ffe8a6;background:#211a08}
.hidden{display:none}.request-title{border-left:4px solid #6da8df}.request-title .label{font-size:.82rem;text-transform:uppercase;letter-spacing:.08em;color:#8fa8bd}.request-title h2{margin:.35rem 0 0;font-size:1.15rem;line-height:1.45}.multi-row{display:flex;align-items:flex-start;gap:10px;padding:9px;border:1px solid #383838;border-radius:9px;margin:7px 0;background:#222}.multi-row input{margin-top:4px}.multi-meta{color:#aaa;font-size:.88rem}.primary{background:#eee;color:#111}.multi-actions{margin-top:14px}
</style></head><body><div class=w><h1>Natural Automation</h1><p class=muted>Node B · HA-General VM905 · Natural Automation + Steward</p>
<div class=layout>
<div class=maincol>
<div class=card><textarea id=q placeholder="Type the next Home Assistant request..."></textarea><br><button onclick=go()>Analyse</button></div>
<div class="card request-title hidden" id=reqcard><div class=label>Current request</div><h2 id=reqtext></h2></div>
<div class=card id=o>Ready for a request.</div>
</div>
<div class=admincol>
<div class=adminhead><h2>Testing / Admin</h2><span class=badge id=adminstatus>loading</span></div>
<div class=admincard><button onclick=refreshInlineAdmin()>Refresh</button><button onclick=inlineHousekeepingScan()>Housekeeping scan</button><p class=muted>Live HA-General view. Controlled automation writes enabled; repair/configuration writes remain gated.</p></div>
<div class=admincard><h3>Housekeeping</h3><div id=inlinehousekeeping>Loading…</div></div>
<div class=admincard><h3>Removal queue</h3><div id=inlineremovals>Loading…</div></div>
<div class=admincard><h3>Recent reasoning / audit</h3><div id=inlineaudit>Loading…</div></div>
</div>
</div></div><script>
async function post(u,b){let r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});let d={};try{d=await r.json()}catch(e){d={error:'The server returned an unreadable response.'}}d._http_ok=r.ok;d._status=r.status;return d}
function esc(v){return String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}
async function inlineHouseReview(id,decision){
  await post('/api/admin/housekeeping-review',{suggestion_id:id,decision:decision});
  await refreshInlineAdmin()
}
async function inlineRemovalReview(id,decision){
  await post('/api/admin/removal-review',{proposal_id:id,decision:decision});
  await refreshInlineAdmin()
}
async function inlineHousekeepingScan(){
  document.getElementById('adminstatus').textContent='scanning…';
  await post('/api/admin/housekeeping-scan',{});
  await refreshInlineAdmin()
}
async function refreshInlineAdmin(){
  try{
    let r=await fetch('/api/admin/log'),d=await r.json();
    if(!r.ok)throw new Error(d.error||'Admin data unavailable');
    document.getElementById('adminstatus').textContent=(d.apply_enabled?'write enabled':'write gate closed');
    let h=document.getElementById('inlinehousekeeping'),q=document.getElementById('inlineremovals'),a=document.getElementById('inlineaudit');
    let hs=d.housekeeping||[];
    h.innerHTML=hs.length?hs.slice(0,8).map(x=>'<div class="audit-event"><b>'+esc(x.alias)+'</b><div class="muted">'+esc(x.confidence)+' · '+esc(x.kind.replaceAll('_',' '))+'</div><p>'+esc(x.reason)+'</p><div class="muted">'+esc(x.status.replaceAll('_',' '))+'</div>'+(x.status==='suggested'?'<button onclick="inlineHouseReview(\\\''+x.suggestion_id+'\\\',\\\'propose_removal\\\')">Propose cleanup</button><button onclick="inlineHouseReview(\\\''+x.suggestion_id+'\\\',\\\'keep\\\')">Keep</button><button onclick="inlineHouseReview(\\\''+x.suggestion_id+'\\\',\\\'dismiss\\\')">Dismiss</button>':'')+'</div>').join(''):'<span class="muted">No housekeeping suggestions.</span>';
    let rs=d.removals||[];
    q.innerHTML=rs.length?rs.slice().reverse().slice(0,8).map(x=>'<div class="audit-event"><b>'+esc(x.alias)+'</b><div class="muted">'+esc(x.controller_id)+' · '+esc(x.source)+'</div><div>'+esc(x.status.replaceAll('_',' '))+'</div>'+(x.status==='pending_review'?'<button onclick="inlineRemovalReview(\\\''+x.proposal_id+'\\\',\\\'approve\\\')">Approve later removal</button><button onclick="inlineRemovalReview(\\\''+x.proposal_id+'\\\',\\\'reject\\\')">Reject</button>':'')+'</div>').join(''):'<span class="muted">No removal proposals.</span>';
    let ev=d.events||[];
    a.innerHTML=ev.slice(0,12).map(e=>'<div class="audit-event"><b>'+new Date((e.ts||0)*1000).toLocaleTimeString()+' · '+esc(e.event||'event')+'</b>'+(e.logic?'<ol>'+e.logic.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ol>':'')+'<details><summary>Machine record</summary><pre>'+esc(JSON.stringify(e,null,2))+'</pre></details></div>').join('')||'<span class="muted">No events yet.</span>';
  }catch(e){
    document.getElementById('adminstatus').textContent='admin view error';
    document.getElementById('inlineaudit').innerHTML='<div class="error">'+esc(e)+'</div>';
  }
}
let activeRequest='';
let multiState=null;
function setCurrentRequest(text){
  activeRequest=text;
  document.getElementById('reqtext').textContent=text||'(blank request)';
  document.getElementById('reqcard').classList.remove('hidden');
}
async function analyseText(t,newSubmission){
  if(newSubmission){
    setCurrentRequest(t);
    document.getElementById('q').value='';
    document.getElementById('q').focus();
  }
  try{
    let start=await post('/api/analyse-start',{text:t});
    if(!start._http_ok){show(start);return}
    await watchJob(start.job_id)
  }catch(e){show({action:'error',error:'Could not contact Natural Automation.',suggestion:String(e)})}
}
async function go(){
  let t=document.getElementById('q').value.trim();
  await analyseText(t,true)
}
async function watchJob(id){
  while(true){
    let r=await fetch('/api/job?id='+encodeURIComponent(id)),j=await r.json();
    if(!r.ok){show({action:'error',error:j.error||'Analysis job was lost.'});return}
    renderProgress(j);
    if(j.status==='done'){show(j.result);return}
    if(j.status==='error'){show({action:'error',error:j.error,suggestion:'Nothing has been changed in Home Assistant.'});return}
    await new Promise(x=>setTimeout(x,250))
  }
}
function renderProgress(j){
  let p=j.progress||{},pct=Number(p.percent||0),eta=p.eta_seconds,state=String(p.state||j.status||'running');
  let o=document.getElementById('o');o.className='card progress state-'+state;
  let etaText=(eta===null||eta===undefined)?'ETA unavailable':('ETA '+Number(eta).toFixed(1)+'s');
  let h='<h3>Processing request <span class="progressstate">'+esc(state.toUpperCase())+'</span></h3>'+
    '<div class="progressbar" aria-label="Measured processing progress"><div class="progressfill" style="width:'+pct.toFixed(1)+'%"></div></div>'+
    '<div class="progressmeta"><span class="progresspct">'+pct.toFixed(1)+'%</span><span>Elapsed '+Number(j.elapsed||0).toFixed(1)+'s</span><span>'+etaText+'</span><span>'+esc(j.stage||'Queued')+'</span></div>'+
    '<p class="muted">Measured from genuine backend stages and learned stage durations. No cosmetic progress is generated.</p>'+
    (p.stall_reason?'<div class="stallnote">'+esc(p.stall_reason)+'</div>':'');
  for(let i=0;i<j.stages.length;i++){
    let s=j.stages[i],active=(i===j.stages.length-1&&j.status==='running');
    h+='<div class="stage '+(active?'active':'done')+'">'+(active?'→ ':'✓ ')+esc(s.name)+'<span class="stage-time">'+Number(s.duration||0).toFixed(1)+'s</span></div>'
  }
  o.innerHTML=h
}
async function proposeRemoval(c,button){
  button.disabled=true;button.textContent='Recording proposal...';
  let d=await post('/api/propose-remove',{controller_id:c.id,source:c.source,alias:c.alias});
  if(d.ok){button.textContent='Removal proposed · pending review'}else{button.disabled=false;button.textContent='Propose removal';alert(d.error||'Could not record proposal')}
}
function renderMultiCandidates(candidates){
  let list=document.getElementById('multilist');
  if(!list||!multiState)return;
  list.innerHTML='';
  candidates.forEach(c=>{
    let row=document.createElement('label');row.className='multi-row';
    let cb=document.createElement('input');cb.type='checkbox';cb.value=c.entity_id;
    cb.checked=multiState.selected.has(c.entity_id);
    cb.onchange=async()=>{
      if(cb.checked)multiState.selected.add(c.entity_id);else multiState.selected.delete(c.entity_id);
      if(cb.checked&&!multiState.refined){
        multiState.refined=true;
        let d=await post('/api/refine-candidates',{category:multiState.category,first_entity_id:c.entity_id});
        if(d.ok){
          let current=new Map(d.candidates.map(x=>[x.entity_id,x]));
          for(let old of multiState.candidates){if(multiState.selected.has(old.entity_id)&&!current.has(old.entity_id))d.candidates.unshift(old)}
          multiState.candidates=d.candidates;
          document.getElementById('multihint').textContent=d.logic.join(' ');
          renderMultiCandidates(d.candidates)
        }
      }
      document.getElementById('multicount').textContent=multiState.selected.size+' selected'
    };
    let body=document.createElement('div');
    body.innerHTML='<b>'+c.name+'</b><div class="multi-meta">'+c.entity_id+(c.area?' · '+c.area:'')+(c.match_reason?' · '+c.match_reason:'')+'</div>';
    row.appendChild(cb);row.appendChild(body);list.appendChild(row)
  })
}
async function confirmMulti(){
  if(!multiState||multiState.selected.size===0){alert('Select at least one device.');return}
  let d=await post('/api/confirm-multi',{request:activeRequest,category:multiState.category,selected:Array.from(multiState.selected)});
  if(d.ok)show(d);else show({action:'error',error:d.error||'Could not confirm the selected devices.'})
}
function showMulti(d){
  multiState={category:d.category,candidates:d.candidates,selected:new Set(),refined:false};
  let o=document.getElementById('o');o.className='card';
  o.innerHTML='<h3>Select devices</h3><p>This request appears to apply to multiple '+d.category+'. Tick every device that should be included.</p>'+
    '<p id="multihint" class="muted">After the first selection, the remaining list will be re-ranked using that device\\\'s domain and Home Assistant area.</p>'+
    '<div id="multilist"></div><div class="multi-actions"><span id="multicount">0 selected</span><br><button class="primary" onclick="confirmMulti()">Use selected devices</button></div>';
  renderMultiCandidates(d.candidates)
}
function show(d){
  let o=document.getElementById('o');o.className='card';
  if((d._http_ok===false)||d.error||d.action==='error'){o.className='card error';o.innerHTML='<h3>ERROR - request not understood</h3><p><b>'+(d.error||'Unknown error')+'</b></p>'+(d.suggestion?'<p>'+d.suggestion+'</p>':'')+'<p class="muted">Nothing has been changed in Home Assistant.</p>';return}
  if(d.action==='select_devices'){showMulti(d);return}
  if(d.action==='multi_selection_confirmed'){let h='<h3>MULTIPLE DEVICES CONFIRMED</h3><p>'+d.selected.length+' device(s) selected:</p><ul>'+d.selected.map(x=>'<li><b>'+x.name+'</b> · '+x.entity_id+(x.area?' · '+x.area:'')+'</li>').join('')+'</ul>';if(d.intent){h+='<h4>Structured intent</h4><ul>'+(d.intent.operation?'<li><b>Operation:</b> '+d.intent.operation.replaceAll('_',' ')+'</li>':'')+(d.intent.metric?'<li><b>Metric:</b> '+d.intent.metric+'</li>':'')+(d.intent.source_reference?'<li><b>Source reference:</b> '+d.intent.source_reference+'</li>':'')+(d.intent.trigger_relationship?'<li><b>Trigger relationship:</b> '+d.intent.trigger_relationship+'</li>':'')+(d.intent.requested_direction?'<li><b>Requested direction:</b> '+d.intent.requested_direction+'</li>':'')+(d.intent.threshold_effect?'<li><b>Threshold interpretation:</b> '+d.intent.threshold_effect+'</li>':'')+(d.intent.condition_context?'<li><b>Condition:</b> '+d.intent.condition_context+'</li>':'')+(d.intent.magnitude?'<li><b>Magnitude:</b> '+d.intent.magnitude+'</li>':'')+'</ul>';if(d.intent.unresolved&&d.intent.unresolved.length)h+='<h4>Needs confirmation</h4><ul>'+d.intent.unresolved.map(x=>'<li>'+x+'</li>').join('')+'</ul>';if(d.intent.assumptions&&d.intent.assumptions.length)h+='<h4>Assumptions</h4><ul>'+d.intent.assumptions.map(x=>'<li>'+x+'</li>').join('')+'</ul>'}if(d.logic)h+='<h4>What I understood</h4><ol>'+d.logic.map(x=>'<li>'+x+'</li>').join('')+'</ol>';o.innerHTML=h;return}
  if(d.action==='clarify'){o.innerHTML='<h3>Which device?</h3><p>I need you to confirm what you mean before I continue.</p>';d.candidates.forEach(c=>{let b=document.createElement('button');b.className='cand';b.textContent=c.name+' · '+c.entity_id+' · '+c.score;b.onclick=async()=>{await post('/api/alias',{phrase:d.target_phrase,entity_id:c.entity_id});await analyseText(activeRequest,false)};o.appendChild(b)});return}
  let h='<h3>'+d.action.replaceAll('_',' ').toUpperCase()+'</h3><p>Target: <b>'+d.target.entity_id+'</b></p>';
  if(d.controllers.length){h+='<p>Existing controllers found:</p><div id="controllers"></div>'}
  if(d.action==='conflict')h+='<p><b>No new automation will be created until this conflict is resolved.</b></p><p class="muted">If one of these automations is obsolete, propose its removal for admin review.</p>';
  if(d.logic){h+='<h4>What I understood</h4><ol>'+d.logic.map(x=>'<li>'+x+'</li>').join('')+'</ol>'}
  o.innerHTML=h;
  let box=document.getElementById('controllers');
  if(box){d.controllers.forEach(c=>{let row=document.createElement('div');row.className='stage';row.textContent=c.alias+' · '+c.role.toUpperCase()+' · '+c.source;if(d.controllers.length>1){let b=document.createElement('button');b.className='remove';b.textContent='Propose removal';b.onclick=()=>proposeRemoval(c,b);row.appendChild(b)}box.appendChild(row)})}
  refreshInlineAdmin()
}
refreshInlineAdmin();
setInterval(refreshInlineAdmin,1500);
</script></body></html>"""

ADMIN_HTML="""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Natural Automation Admin</title><style>
body{font-family:system-ui;margin:0;background:#0b0b0b;color:#eee}.w{max-width:1200px;margin:30px auto;padding:0 18px}
.card{background:#171717;border:1px solid #333;border-radius:12px;padding:16px;margin:12px 0}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#090909;border:1px solid #292929;padding:12px;border-radius:9px}.muted{color:#999}
button{padding:9px 13px;border:0;border-radius:8px;margin:4px}.approve{background:#245d35;color:#eaffef}.reject{background:#652b2b;color:#ffecec}.warn{background:#725b22;color:#fff4c8} ol{line-height:1.55}.status{font-weight:700}.high{color:#ff9f9f}.medium{color:#ffd685}
</style></head><body><div class=w><h1>Natural Automation Admin</h1>
<p class=muted>LAN-admin diagnostics · not linked from the user dashboard · write gate status shown per event</p>
<button onclick=load()>Refresh</button><button class=warn onclick=scanHousekeeping()>Scan automation housekeeping</button>
<h2>Housekeeping suggestions</h2><div id=housekeeping></div>
<h2>Removal review queue</h2><div id=queue></div><h2>Audit log</h2><div id=out></div></div><script>
async function scanHousekeeping(){
 let r=await fetch('/api/admin/housekeeping-scan',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
 let d=await r.json(); if(!r.ok)alert(d.error||'Housekeeping scan failed'); await load()
}
async function houseReview(id,decision){
 let r=await fetch('/api/admin/housekeeping-review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({suggestion_id:id,decision:decision})});
 let d=await r.json(); if(!r.ok)alert(d.error||'Housekeeping review failed'); await load()
}
async function review(id,decision){
 let r=await fetch('/api/admin/removal-review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({proposal_id:id,decision:decision})});
 let d=await r.json(); if(!r.ok){alert(d.error||'Review failed')} await load()
}
async function load(){let r=await fetch('/api/admin/log');let d=await r.json();let o=document.getElementById('out'),q=document.getElementById('queue'),h=document.getElementById('housekeeping');
if(!r.ok){o.innerHTML='<div class=card>'+d.error+'</div>';return}
let hs=(d.housekeeping||[]).slice();
h.innerHTML=hs.length?hs.map(x=>'<div class=card><b>'+x.alias+'</b><p><span class="'+x.confidence+'">'+x.confidence.toUpperCase()+' confidence</span> · '+x.kind.replaceAll('_',' ')+'</p><p>'+x.reason+'</p><p class="muted">'+x.recommended_action+'</p><p class="status">Status: '+x.status.replaceAll('_',' ')+'</p>'+
(x.status==='suggested'?'<button class="warn" onclick="houseReview(\''+x.suggestion_id+'\',\'propose_removal\')">Propose cleanup</button><button class="approve" onclick="houseReview(\''+x.suggestion_id+'\',\'keep\')">Keep automation</button><button class="reject" onclick="houseReview(\''+x.suggestion_id+'\',\'dismiss\')">Dismiss suggestion</button>':'')+
(x.review_note?'<p>'+x.review_note+'</p>':'')+
'<details><summary>Evidence</summary><pre>'+JSON.stringify(x.evidence,null,2).replaceAll('&','&amp;').replaceAll('<','&lt;')+'</pre></details></div>').join(''):'<div class=card>No housekeeping suggestions. Run a scan to check.</div>';
let pending=(d.removals||[]).slice().reverse();
q.innerHTML=pending.length?pending.map(x=>'<div class=card><b>'+x.alias+'</b><p>'+x.controller_id+' · '+x.source+'</p><p class="status">Status: '+x.status.replaceAll('_',' ')+'</p>'+
(x.status==='pending_review'?'<button class="approve" onclick="review(\''+x.proposal_id+'\',\'approve\')">Approve for later removal</button><button class="reject" onclick="review(\''+x.proposal_id+'\',\'reject\')">Reject</button>':'')+
(x.review_logic?'<ul>'+x.review_logic.map(v=>'<li>'+v+'</li>').join('')+'</ul>':'')+'</div>').join(''):'<div class=card>No removal proposals.</div>';
o.innerHTML=d.events.map(e=>'<div class=card><b>'+new Date((e.ts||0)*1000).toLocaleString()+' · '+(e.event||'event')+'</b>'+
(e.logic?'<h4>Human-readable logic</h4><ol>'+e.logic.map(x=>'<li>'+x+'</li>').join('')+'</ol>':'')+
'<details><summary>Machine record</summary><pre>'+JSON.stringify(e,null,2).replaceAll('&','&amp;').replaceAll('<','&lt;')+'</pre></details></div>').join('')}
load()
</script></body></html>"""

def admin_allowed(handler):
    ip=handler.client_address[0]
    return ip=="127.0.0.1" or ip=="::1" or ip.startswith("10.10.10.")

def recent_audit(limit=100):
    if not AUDIT.exists(): return []
    lines=[x for x in AUDIT.read_text().splitlines() if x.strip()]
    out=[]
    for line in lines[-limit:]:
        try: out.append(json.loads(line))
        except Exception: pass
    return list(reversed(out))

class H(BaseHTTPRequestHandler):
    def sendj(self,d,code=200):
        b=json.dumps(d).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if urlparse(self.path).path=="/":
            b=HTML.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b); return
        path=urlparse(self.path).path
        if path=="/admin":
            if not admin_allowed(self): return self.sendj({"error":"Admin page is available only from the local management LAN."},403)
            b=ADMIN_HTML.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b); return
        if path=="/api/admin/log":
            if not admin_allowed(self): return self.sendj({"error":"Admin log is available only from the local management LAN."},403)
            return self.sendj({"events":recent_audit(100),"removals":load_removals(),"housekeeping":load_housekeeping(),"apply_enabled":ENABLE_APPLY})
        if path=="/api/job":
            job_id=(parse_qs(urlparse(self.path).query).get("id") or [""])[0]
            try: return self.sendj(job_view(job_id))
            except KeyError: return self.sendj({"error":"Analysis job not found."},404)
        if path=="/api/status":
            try:
                inv=inventory(); self.sendj({"ok":True,"vmid":VMID,"entities":len(inv["entities"]),"apply_enabled":ENABLE_APPLY})
            except Exception as e:self.sendj({"ok":False,"error":str(e)},503)
            return
        self.send_error(404)
    def do_POST(self):
        n=int(self.headers.get("Content-Length","0")); p=json.loads(self.rfile.read(n) or b"{}"); path=urlparse(self.path).path
        try:
            if path=="/api/analyse": return self.sendj(analyse(str(p.get("text",""))))
            if path=="/api/analyse-start":
                return self.sendj({"ok":True,"job_id":start_analysis_job(str(p.get("text","")))})
            if path=="/api/alias":
                save_alias(str(p.get("phrase","")),str(p.get("entity_id",""))); return self.sendj({"ok":True})
            if path=="/api/refine-candidates":
                return self.sendj(refine_multi_candidates(
                    str(p.get("category","")),
                    str(p.get("first_entity_id","")),
                ))
            if path=="/api/confirm-multi":
                return self.sendj(confirm_multi_selection(
                    str(p.get("request","")),
                    str(p.get("category","")),
                    p.get("selected") or [],
                ))
            if path=="/api/propose-remove":
                return self.sendj(propose_removal(
                    str(p.get("controller_id","")),
                    str(p.get("source","")),
                    str(p.get("alias","")),
                ))
            if path=="/api/admin/housekeeping-scan":
                if not admin_allowed(self): return self.sendj({"error":"Housekeeping scan is available only from the local management LAN."},403)
                items=scan_housekeeping()
                return self.sendj({"ok":True,"count":len(items),"suggestions":items})
            if path=="/api/admin/housekeeping-review":
                if not admin_allowed(self): return self.sendj({"error":"Housekeeping review is available only from the local management LAN."},403)
                return self.sendj(review_housekeeping(str(p.get("suggestion_id","")),str(p.get("decision",""))))
            if path=="/api/admin/removal-review":
                if not admin_allowed(self): return self.sendj({"error":"Admin review is available only from the local management LAN."},403)
                return self.sendj(review_removal(str(p.get("proposal_id","")),str(p.get("decision",""))))
            if path=="/api/steward/status":
                if not admin_allowed(self): return self.sendj({"error":"Steward status is available only from the local management LAN."},403)
                st=STEWARD.status(); st.update({"ok":True,"vmid":VMID,"apply_enabled":ENABLE_APPLY})
                return self.sendj(st)
            if path=="/api/apply-automation":
                if not admin_allowed(self): return self.sendj({"error":"Automation apply is available only from the local management LAN."},403)
                if not ENABLE_APPLY: return self.sendj({"error":"Controlled automation write gate is closed."},403)
                unresolved=p.get("unresolved") or []
                if unresolved: return self.sendj({"error":"Unresolved targets remain; refusing to apply.","unresolved":unresolved},409)
                result=apply_automation(VMID,p.get("automation"))
                audit("automation_applied",vmid=VMID,automation_id=result.get("automation_id"),backup=result.get("backup"),logic=["Targets resolved.","Configuration written transactionally.","Home Assistant configuration check passed.","HA-General restarted after validation."])
                STEWARD.observe("automation_applied","natural_automation",{"vmid":VMID,"automation_id":result.get("automation_id")})
                return self.sendj(result)
            self.send_error(404)
        except Exception as e:
            request_text=str(p.get("text","")) if isinstance(p,dict) else ""
            message=f"{type(e).__name__}: {e}"
            audit("error",request=request_text,error=message)
            self.sendj({"action":"error","error":str(e),
                        "suggestion":"Try rephrasing the request in plain language. Nothing has been changed.",
                        "request":request_text},422)
    def log_message(self,*a): pass

if __name__=="__main__":
    host=os.environ.get("NA_BIND","0.0.0.0"); port=int(os.environ.get("NA_PORT","8099"))
    audit("service_start",vmid=VMID,apply_enabled=ENABLE_APPLY)
    print(f"Natural Automation listening on {host}:{port}, apply={ENABLE_APPLY}",flush=True)
    ThreadingHTTPServer((host,port),H).serve_forever()
