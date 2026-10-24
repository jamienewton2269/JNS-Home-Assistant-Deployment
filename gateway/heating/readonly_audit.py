#!/usr/bin/env python3
"""Read-only diagnostic for JNS Heating Zones v0.3.x, VM905 only.

No secrets, learned samples, weather coordinates, thermostat state or
configuration contents are exported. No HA writes/restarts are performed.
"""
import base64
import json
import sys
import time

sys.path.insert(0, "gateway/arrival_lighting")
from readiness_probe import ssh_host

INSPECT = r'''
import ast
import hashlib
import json
import pathlib
import re
root=pathlib.Path("/config")
comp=root/"custom_components"/"jns_heating_zones"
out={"component_present":comp.is_dir()}
manifest=comp/"manifest.json"
if manifest.exists():
    try:
        m=json.loads(manifest.read_text())
        out["version"]=m.get("version")
        out["domain"]=m.get("domain")
    except (ValueError,OSError):
        out["manifest_read_error"]=True
for name in ("coordinator.py","sensor.py","__init__.py"):
    f=comp/name
    if not f.is_file():
        continue
    raw=f.read_bytes()
    out[name+"_sha256"]=hashlib.sha256(raw).hexdigest()
    if name!="coordinator.py":
        continue
    try:
        src=raw.decode("utf-8")
        tree=ast.parse(src)
    except (UnicodeError,SyntaxError):
        out["coordinator_parse_error"]=True
        continue
    lines=src.splitlines()
    members={}
    for node in ast.walk(tree):
        if isinstance(node,(ast.AsyncFunctionDef,ast.FunctionDef)) and any(x in node.name.lower() for x in ("forecast","learn","thermal","update_data","predict","interval")):
            members[node.name]={"first":node.lineno,"last":node.end_lineno}
    out["relevant_methods"]=members
    out["forecast_line_count"]=len([l for l in lines if re.search("forecast",l,re.I)])
    out["forecast_refresh_interval_seconds_literals"]=sorted(set(re.findall(r"(?:timedelta\(\s*(?:minutes|seconds)\s*=\s*\d+|_forecast_at)",src)))[:15]
    snippets={}
    for key in ("_refresh_forecast","_async_update_data"):
        found=[n for n in ast.walk(tree) if isinstance(n,(ast.AsyncFunctionDef,ast.FunctionDef)) and n.name==key]
        if not found:
            continue
        n=found[0]
        if key=="_async_update_data":
            selected=[(i,lines[i-1]) for i in range(n.lineno,min(n.end_lineno,n.lineno+120)+1)
                      if re.search("forecast|async_request_refresh|_update|_learn",lines[i-1],re.I)]
        else:
            selected=[(i,lines[i-1]) for i in range(n.lineno,min(n.end_lineno,n.lineno+130)+1)]
        # No live sensor states or credentials; redact suspect source lines.
        shown=[]
        for lineno,line in selected:
            if re.search(r"(?i)(password|api_key|secret|authorization|bearer|access_token|refresh_token|client_secret)",line):
                shown.append(f"{lineno}: [REDACTED]")
            else:
                shown.append(f"{lineno}: {line[:180]}")
        snippets[key]="\n".join(shown)[:14500]
    out["safe_forecast_snippets"]=snippets
registry=root/".storage"/"core.entity_registry"
if registry.exists():
    try:
        es=json.loads(registry.read_text())["data"]["entities"]
        out["heating_entity_ids"]=[e.get("entity_id") for e in es
          if "heating" in (e.get("entity_id") or "") or
             (e.get("platform")=="jns_heating_zones")][:60]
    except (ValueError,OSError,KeyError):
        out["registry_read_error"]=True
stor=root/".storage"
out["matching_storage_files"]=[{"name":p.name,"size":p.stat().st_size}
   for p in stor.iterdir() if p.is_file() and re.search("jns.*heat|heat.*learn",p.name,re.I)][:30] if stor.is_dir() else []
log=root/"home-assistant.log"
if log.exists():
    lines=log.read_text(errors="replace").splitlines()[-2500:]
    out["recent_heating_log_levels"]={
      "ERROR":sum("ERROR" in s and "jns_heating" in s.lower() for s in lines),
      "WARNING":sum("WARNING" in s and "jns_heating" in s.lower() for s in lines)}

out["component_source_files"] = sorted(p.name for p in comp.iterdir() if p.suffix==".py") if comp.is_dir() else []
details={}
for filename in ("learner.py","thermal.py","model.py","sensor.py","__init__.py"):
    p=comp/filename
    if not p.is_file():
        continue
    source=p.read_text(errors="replace")
    source_lines=source.splitlines()
    try:
        parsed=ast.parse(source)
        details[filename]={"ast_valid":True,"classes":[x.name for x in parsed.body if isinstance(x,ast.ClassDef)],
            "functions":[n.name for n in ast.walk(parsed) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))][:80]}
    except SyntaxError:
        details[filename]={"ast_valid":False}
        continue
    # Show code context for model readiness and prediction gating, not credentials or raw samples.
    hits=[i for i,line in enumerate(source_lines) if re.search(
        r"48\b|valid_interval|minimum|insufficient|ready|unavailable|predict|projection|project\(|\blearned\b|record\(|thermal|interval",line,re.I)]
    chosen=set()
    for i in hits[:35]:
        chosen.update(range(max(0,i-4),min(len(source_lines),i+5)))
    excerpt=[]
    for idx in sorted(chosen)[:170]:
        line=source_lines[idx]
        if re.search(r"(?i)(password|api_key|secret|authorization|bearer|access_token|refresh_token|client_secret)",line):
            line="[REDACTED]"
        excerpt.append(f"{idx+1}: {line[:180]}")
    details[filename]["targeted_source_excerpt"]="\n".join(excerpt)[:18000]
out["thermal_source_detail"]=details
for entry in out.get("matching_storage_files",[]):
    try:
        saved=json.loads((stor/entry["name"]).read_text())
        data=saved.get("data",{}) if isinstance(saved,dict) else {}
        entry["stored_top_level_keys"]=list(saved)[:30] if isinstance(saved,dict) else []
        if isinstance(data,dict):
            entry["data_shape"]={k:({"type":type(v).__name__,"count":len(v)} if isinstance(v,(list,dict))
                                    else {"type":type(v).__name__})
                                   for k,v in data.items() if not re.search("secret|token|password|key",k,re.I)}
    except (ValueError,OSError):
        entry["shape_unavailable"]=True

print(json.dumps(out,sort_keys=True))
'''

def run_guest():
    status=ssh_host("nodeb",["qm","status","905"])
    if "running" not in status:
        raise RuntimeError("VM905 not running")
    source="exec(__import__('base64').b64decode('"+base64.b64encode(INSPECT.encode()).decode()+"'))"
    command=["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",source]
    result=json.loads(ssh_host("nodeb",command))
    deadline=time.monotonic()+75
    while not result.get("exited"):
        if not isinstance(result.get("pid"),int):
            raise RuntimeError("QGA returned no PID")
        if time.monotonic()>deadline:
            raise RuntimeError("QGA still running; audit stopped")
        time.sleep(1)
        result=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(result["pid"])]))
    if result.get("exitcode")!=0:
        raise RuntimeError("guest probe exited non-zero")
    return json.loads(result["out-data"])

if __name__=="__main__":
    print("JNS_HEATING_READONLY_AUDIT_START",flush=True)
    try:
        print(json.dumps(run_guest(),sort_keys=True,indent=2),flush=True)
    except Exception as exc:
        print("JNS_HEATING_AUDIT_BLOCKED",type(exc).__name__,str(exc)[:180],flush=True)
        raise SystemExit(1)
    print("JNS_HEATING_READONLY_AUDIT_END",flush=True)
