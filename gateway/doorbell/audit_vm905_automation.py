#!/usr/bin/env python3
"""Read-only HA-General automation audit, with no authentication data printed."""
import base64,json,subprocess,shlex,time
SOURCE=r'''
from pathlib import Path
import re,json,yaml
p=Path("/config")
rx=re.compile("door.?bell|chime|bell|ring|kc868|alarm.?panel|esphome|button|buzzer|relay|front.?door|press",re.I)
aut=[]
for path in [p/"automations.yaml", *sorted((p/"packages").glob("*.yaml"))]:
    try:d=yaml.safe_load(path.read_text())
    except Exception as e:
        print("YAML_UNREADABLE",path.name,type(e).__name__);continue
    rows=d if isinstance(d,list) else d.get("automation",[]) if isinstance(d,dict) else []
    if isinstance(rows,dict):rows=list(rows.values())
    if not isinstance(rows,list):continue
    for row in rows:
        if isinstance(row,dict):
            aut.append((str(path.name),row))
def summary(x):
    if isinstance(x,list):return [summary(y) for y in x[:25]]
    if isinstance(x,dict):
        fields=("trigger","triggers","platform","entity_id","device_id","domain","type",
        "topic","event_type","id","action","actions","service","target","choose",
        "sequence","then","else","delay","condition","conditions","state",
        "for","value_template","payload","data")
        return {k:summary(v) for k,v in x.items() if k in fields}
    return str(x)[:130]
print("AUTOMATION_TOTAL",len(aut))
print("AUTOMATION_ALIASES",json.dumps([{"file":path,"alias":a.get("alias"),"id":a.get("id")} for path,a in aut],default=str)[:18000])
for path,a in aut:
    if rx.search(str(a.get("alias",""))+" "+str(a.get("id",""))+" "+json.dumps(summary(a),default=str)):
        print("RELEVANT_AUTOMATION",json.dumps({"file":path,"id":a.get("id"),"alias":a.get("alias"),
        "initial_state":a.get("initial_state"),"trigger":summary(a.get("trigger",a.get("triggers"))),
        "condition":summary(a.get("condition",a.get("conditions"))),
        "action":summary(a.get("action",a.get("actions")))},default=str)[:4200])
def records(name,key):
    try:return json.loads((p/".storage"/name).read_text())["data"][key]
    except Exception:return []
entries=records("core.config_entries","entries")
print("ESPHOME_ENTRIES",json.dumps([{"title":e.get("title"),"disabled":e.get("disabled_by"),"domain":e.get("domain")} for e in entries if e.get("domain") in ("esphome","mqtt")]))
entities=records("core.entity_registry","entities")
print("MATCHING_ENTITIES",json.dumps([{"id":e.get("entity_id"),"platform":e.get("platform"),"disabled":e.get("disabled_by"),"name":e.get("name") or e.get("original_name")} for e in entities if rx.search(" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name","platform")))][:100],default=str)[:16000])
print("AUTOMATION_REGISTRY",json.dumps([{"id":e.get("entity_id"),"name":e.get("name") or e.get("original_name"),"disabled":e.get("disabled_by")} for e in entities if e.get("entity_id","").startswith("automation.") and rx.search(" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name"))) ],default=str)[:6000])
traces=p/".storage"/"trace.saved_traces"
if traces.exists():
    try:
        data=json.loads(traces.read_text()).get("data",{})
        print("TRACE_AUTOMATION_KEYS",json.dumps([k for k in data.keys() if rx.search(k)])[:2000] if isinstance(data,dict) else "other")
    except Exception as e:print("TRACE_UNREADABLE",type(e).__name__)
'''
payload="exec(__import__('base64').b64decode("+repr(base64.b64encode(SOURCE.encode()).decode())+"))"
def ssh(command):
    p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(command)],
        capture_output=True,text=True,timeout=30)
    if p.returncode: raise RuntimeError(p.stderr[-300:])
    return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",payload])
for i in range(25):
    if d.get("exited"):break
    time.sleep(1)
    d=ssh(["qm","guest","exec-status","905",str(d["pid"])])
print("GUEST_EXIT_CODE",d.get("exitcode"),flush=True)
print((d.get("out-data") or "")[:47000],flush=True)
print("GUEST_STDERR",(d.get("err-data") or "")[:400],flush=True)
