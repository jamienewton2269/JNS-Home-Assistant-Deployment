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


for filename,ranges in {"thermal.py":[(5,100)],"coordinator.py":[(28,90)],"sensor.py":[(35,65)]}.items():
    file_path=comp/filename
    if not file_path.exists():
        continue
    lines=file_path.read_text(errors="replace").splitlines()
    excerpts=[]
    for first,last in ranges:
        for i in range(first-1,min(last,len(lines))):
            line=lines[i]
            if re.search(r"(?i)(password|api_key|secret|authorization|bearer|access_token|refresh_token|client_secret)",line):
                line="[REDACTED]"
            excerpts.append(f"{i+1}: {line[:180]}")
    out.setdefault("model_readiness_code",{})[filename]="\n".join(excerpts)[:15000]
# Structural sample metadata only; raw temperatures, locations and times are withheld.
try:
    store=json.loads((stor/out["matching_storage_files"][0]["name"]).read_text())
    sample_data=store.get("data",{}).get("samples",[])
    if sample_data and isinstance(sample_data[0],dict):
        out["saved_sample_schema"]=sorted(sample_data[0].keys())
except (IndexError,KeyError,ValueError,OSError,TypeError):
    out["saved_sample_schema_unavailable"]=True


try:
    from datetime import datetime
    from collections import Counter
    persisted=json.loads((stor/out["matching_storage_files"][0]["name"]).read_text())
    samples=persisted.get("data",{}).get("samples",[])
    counts=Counter()
    intervals=[]
    for x,y in zip(samples,samples[1:]):
        try:
            dt=(datetime.fromisoformat(y["at"])-datetime.fromisoformat(x["at"])).total_seconds()/60
            if dt <= 0: counts["non_increasing_time"]+=1
            elif dt < 4.5: counts["short_under_4_5_min"]+=1
            elif dt < 5: counts["short_4_5_to_5_min"]+=1
            elif dt > 60: counts["long_over_60_min"]+=1
            elif not (x.get("valid",True) and y.get("valid",True)): counts["invalid_marked_sample"]+=1
            elif abs(y["indoor"]-x["indoor"]) > 3*(dt/60)+.3: counts["implausible_temp_change"]+=1
            else:
                counts["accepted"]+=1
                counts["accepted_heated_80pct"]=counts["accepted_heated_80pct"] + int(y["duty"]>=.8)
                counts["accepted_unheated_20pct"]=counts["accepted_unheated_20pct"] + int(y["duty"]<=.2)
            intervals.append(dt)
        except (ValueError,TypeError,KeyError,OverflowError):
            counts["malformed"]+=1
    valid_intervals=sorted(x for x in intervals if x>0)
    def percentile(pct):
        return round(valid_intervals[round((len(valid_intervals)-1)*pct)],3) if valid_intervals else None
    out["sample_interval_audit"]={"saved_samples":len(samples),"adjacent_pairs":max(0,len(samples)-1),
       "filter_counts":dict(counts),"interval_min_percentiles":{
         "p05":percentile(.05),"p50":percentile(.5),"p95":percentile(.95)},
       "accepted_if_4_5_min_threshold":sum(4.5<=x<=60 for x in intervals)}
except (ValueError,OSError,KeyError,IndexError,TypeError):
    out["sample_interval_audit_unavailable"]=True


# Evaluate the actual deployed learner against its persisted samples, without changing HA state.
try:
    import importlib.util,sys
    p=comp/"thermal.py"
    spec=importlib.util.spec_from_file_location("_jns_heating_thermal_probe",p)
    mdl=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mdl
    spec.loader.exec_module(mdl)
    rec=json.loads((stor/out["matching_storage_files"][0]["name"]).read_text())
    learner=mdl.ZoneLearner(rec["data"].get("samples",[]))
    result=learner.status()
    out["computed_learner_status"]={k:v for k,v in result.items() if k in (
      "ready","reason","samples","loss_per_hour","heat_gain_c_per_hour","drift_c_per_hour")}
except (ValueError,KeyError,OSError,IndexError,ImportError,AttributeError,TypeError) as exc:
    out["computed_learner_status_error"]=type(exc).__name__


try:
    from collections import Counter
    from datetime import datetime
    persisted=json.loads((stor/out["matching_storage_files"][0]["name"]).read_text())["data"]["samples"]
    indoor=[float(x["indoor"]) for x in persisted]
    outdoor=[float(x["outdoor"]) for x in persisted]
    duty=[float(x["duty"]) for x in persisted]
    dt=datetime.fromisoformat(persisted[-1]["at"])-datetime.fromisoformat(persisted[0]["at"])
    aligned=[]
    for a,b in zip(persisted,persisted[1:]):
        hours=(datetime.fromisoformat(b["at"])-datetime.fromisoformat(a["at"])).total_seconds()/3600
        if a.get("valid",True) and b.get("valid",True) and 5/60 <= hours <= 1 and abs(b["indoor"]-a["indoor"])<=3*hours+.3:
            aligned.append(round(float(b["indoor"])-float(a["indoor"]),3))
    dd=Counter(aligned)
    out["thermal_signal_summary"]={
       "stored_hours":round(dt.total_seconds()/3600,1),
       "indoor_unique_values":len(set(indoor)),
       "indoor_range_c":[min(indoor),max(indoor)],
       "outdoor_unique_values":len(set(outdoor)),
       "outdoor_range_c":[min(outdoor),max(outdoor)],
       "on_sample_count":sum(x>=.8 for x in duty),
       "off_sample_count":sum(x<=.2 for x in duty),
       "indoor_delta_unchanged_pairs":dd[0.0],
       "accepted_pair_count":len(aligned),
       "indoor_nonzero_step_count":sum(abs(x)>.001 for x in aligned),
       "most_common_indoor_steps_c":dd.most_common(7)
    }
except (ValueError,IndexError,OSError,KeyError,TypeError,ZeroDivisionError):
    out["thermal_signal_summary_unavailable"]=True


# Version-locked source snapshot for offline v0.3.5 candidate derivation.
source_file=comp/"thermal.py"
if source_file.is_file() and json.loads(manifest.read_text()).get("version")=="0.3.4":
    out["thermal_source_snapshot"]=source_file.read_text(encoding="utf-8")
else:
    out["thermal_source_snapshot"]="SOURCE_CHANGED_OR_MISSING"

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
