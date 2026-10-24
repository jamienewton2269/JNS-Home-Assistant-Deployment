#!/usr/bin/env python3
"""Read-only doorbell fault isolation. No HA changes; redact confidential configuration."""
import base64, json, shlex, socket, subprocess, time

def cmd(argv, timeout=16):
    try:
        p=subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        return {"rc":p.returncode,"out":p.stdout[-28000:],"error":p.stderr[-300:]}
    except Exception as e:
        return {"error":type(e).__name__+": "+str(e)[:180]}

def remote(host,args):
    return cmd(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=7","-o","StrictHostKeyChecking=yes",host,shlex.join(args)],timeout=18)

print("=== JNS FRONT DOORBELL / ESPHOME LIVE READ-ONLY DIAGNOSTIC ===", flush=True)
print("UTC",time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),flush=True)
for label,host,vm in [("HA-LEGACY","nodea","900"),("HA-GENERAL","nodeb","905"),("HA-SECURITY","local","906")]:
    args=["qm","status",vm]
    status=cmd(args) if host=="local" else remote(host,args)
    print("VM_STATUS",label,host,vm,json.dumps(status)[:700],flush=True)

for name,port in [("KC868_OLD_STATIC_ESPHOME",6053),("KC868_OLD_STATIC_WEB",80)]:
    try:
        with socket.create_connection(("10.10.10.252",port),timeout=3):
            print("TCP_PROBE",name,"REACHABLE",flush=True)
    except OSError as e:
        print("TCP_PROBE",name,type(e).__name__,str(e)[:100],flush=True)

PAYLOAD=r'''
from pathlib import Path
import json,re,collections
P=Path("/config")
rx=re.compile(r"door.?bell|kc868|chime|buzzer|ring(?:er|ing)?|front.?door|ding.?dong",re.I)
out={}
def load(rel,key):
    try: return json.loads((P/".storage"/rel).read_text()).get("data",{}).get(key,[])
    except Exception as e: return []
entities=load("core.entity_registry","entities")
out["matching_entities"]=[{
    "entity_id":e.get("entity_id"),
    "platform":e.get("platform"),
    "disabled":e.get("disabled_by"),
    "device_id":e.get("device_id"),
    "name":e.get("name") or e.get("original_name")
} for e in entities if rx.search(" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name")) )][:65]
devices=load("core.device_registry","devices")
out["matching_devices"]=[{
    "id":d.get("id"),
    "name":d.get("name_by_user") or d.get("name"),
    "manufacturer":d.get("manufacturer"),
    "model":d.get("model"),
    "disabled":d.get("disabled_by")
} for d in devices if rx.search(" ".join(str(d.get(k,"")) for k in ("name","name_by_user","model","manufacturer")) )][:30]
ids={x.get("device_id") for x in out["matching_entities"]}
out["matching_entity_devices"]=[{
    "id":d.get("id"),
    "name":d.get("name_by_user") or d.get("name"),
    "model":d.get("model"),
    "disabled":d.get("disabled_by")
} for d in devices if d.get("id") in ids][:30]
entries=load("core.config_entries","entries")
out["integrations"]=[{
    "domain":e.get("domain"),"title":e.get("title"),"disabled":e.get("disabled_by")
} for e in entries if e.get("domain") in ("esphome","mqtt","mpd","tts") or rx.search(str(e.get("title","")))][:35]
files=[P/"automations.yaml",P/"scripts.yaml"]
files+=sorted((P/"packages").glob("*.yaml")) if (P/"packages").is_dir() else []
out["automation_yaml_matches"]=[]
out["text_matches"]=[]
try: import yaml
except ImportError: yaml=None
for p in files:
    if not p.exists(): continue
    try: raw=p.read_text(errors="replace")
    except Exception: continue
    if not rx.search(raw): continue
    if yaml:
        try:
            data=yaml.safe_load(raw)
            autos=(data if isinstance(data,list) else data.get("automation",[]) if isinstance(data,dict) else [])
            if isinstance(autos,dict): autos=list(autos.values())
            for a in autos:
                if not isinstance(a,dict): continue
                if rx.search(json.dumps(a,default=str)):
                    def fields(obj):
                        if isinstance(obj,list): return [fields(v) for v in obj[:10]]
                        if isinstance(obj,dict):
                            allowed=("entity_id","device_id","event_type","platform","type","domain","service","action","topic","trigger","id")
                            return {k:fields(v) for k,v in obj.items() if k in allowed or k in ("trigger","triggers","conditions","condition","actions","sequence","choose","target") }
                        return str(obj)[:100]
                    out["automation_yaml_matches"].append({"path":p.name,"alias":a.get("alias"),"id":a.get("id"),
                        "trigger":fields(a.get("trigger",a.get("triggers",[]))),
                        "action":fields(a.get("action",a.get("actions",[])))})
        except Exception as ex: out.setdefault("parse_errors",[]).append({"path":p.name,"type":type(ex).__name__})
    for i,line in enumerate(raw.splitlines(),1):
        if rx.search(line) and not re.search(r"(?i)(key|password|token|secret|api_key|authorization|bearer|encrypt)",line):
            out["text_matches"].append({"path":p.name,"line":i,"text":line.strip()[:130]})
    if len(out["text_matches"])>55: out["text_matches"]=out["text_matches"][:55]
    if len(out["automation_yaml_matches"])>20: out["automation_yaml_matches"]=out["automation_yaml_matches"][:20]
log=P/"home-assistant.log"
if log.exists():
    try:
        recent=log.read_text(errors="replace").splitlines()[-3500:]
        found=[l for l in recent if rx.search(l) or ("ERROR" in l and any(x in l.lower() for x in ("esphome","media_player","automations","mqtt","piper","tts")))]
        out["recent_log_matches"]=[{"level": "ERROR" if "ERROR" in l else "WARNING" if "WARNING" in l else "INFO",
            "component":(re.search(r"\[([^\]]+)\]",l).group(1) if re.search(r"\[([^\]]+)\]",l) else "?"),
            "hint": ("doorbell" if "doorbell" in l.lower() else "esphome" if "esphome" in l.lower() else "chime" if "chime" in l.lower() else "audio/automation")} for l in found[-40:]]
        out["matching_log_line_count"]=len(found)
    except Exception as ex: out["log_read_error"]=type(ex).__name__
print(json.dumps(out,ensure_ascii=False,default=str,separators=(",",":")))
'''
arg="exec(__import__('base64').b64decode("+repr(base64.b64encode(PAYLOAD.encode()).decode())+"))"
for label,host,vm in [("HA-LEGACY","nodea","900"),("HA-GENERAL","nodeb","905"),("HA-SECURITY","local","906")]:
    args=["qm","guest","exec",vm,"--","docker","exec","homeassistant","python3","-c",arg]
    r=cmd(args,timeout=24) if host=="local" else remote(host,args)
    if r.get("rc") != 0:
        print("GUEST_UNAVAILABLE",label,json.dumps(r)[:550],flush=True)
        continue
    try:
        d=json.loads(r["out"])
        if d.get("pid") and not d.get("exited"):
            poll=["qm","guest","exec-status",vm,str(d["pid"])]
            for n in range(12):
                time.sleep(1)
                z=cmd(poll,timeout=12) if host=="local" else remote(host,poll)
                if z.get("rc")!=0: break
                d=json.loads(z["out"])
                if d.get("exited"): break
        if d.get("exited") and d.get("exitcode")==0:
            print("HA_CONFIG",label,(d.get("out-data") or "")[:21000],flush=True)
        else: print("GUEST_RESULT",label,json.dumps(d)[:700],flush=True)
    except Exception as e:
        print("GUEST_PARSE_ERROR",label,type(e).__name__,str(e)[:200],flush=True)
print("AUDIT_END: no HA configuration or device modifications",flush=True)
