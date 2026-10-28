#!/usr/bin/env python3
"""Private VM906->VM905 YAML cutover structure and dependency readiness audit.
Read-only. Never print raw YAML, keys, passwords, hostnames, entity IDs or secrets.
"""
import base64,shlex,subprocess,os
SRC=r'''
import hashlib,json,os,pathlib,re,sys
p=pathlib.Path("/var/lib/jns-solar/consolidation/ha-security-906-20261027-v1")
m=p/"manifest.json"
def fail(c):
 print("JNS_SECURITY_STRUCTURE_BLOCKED="+c);raise SystemExit(77)
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":fail("identity")
if not m.is_file() or m.is_symlink():fail("missing_manifest")
meta=json.loads(m.read_text())
if meta.get("source_vm")!=906 or meta.get("target_vm")!=905:fail("source_mismatch")
out={"source_files":len(meta.get("files",[])),"files":[],"safe_to_bulk_copy":False}
for entry in meta.get("files",[]):
 f=p/"files"/str(entry.get("staged_basename",""))
 if not f.is_file() or f.is_symlink():fail("missing_stage")
 data=f.read_bytes()
 if hashlib.sha256(data).hexdigest()!=entry.get("sha256"):fail("hash_mismatch")
 text=data.decode("utf-8","replace")
 tops=re.findall(r"(?m)^([a-z][a-z0-9_]*)\s*:",text)
 secret_refs=len(re.findall(r"!secret\b",text))
 # Count YAML constructs; never output values or names.
 o={"kind":entry.get("kind"),"file_type": "automation" if entry.get("original_basename")=="automations.yaml" else "script" if entry.get("original_basename")=="scripts.yaml" else "configuration" if entry.get("original_basename")=="configuration.yaml" else "scene" if entry.get("original_basename")=="scenes.yaml" else "package",
    "top_level_sections":sorted(set(tops)),"secret_references":secret_refs,
    "automation_id_markers":len(re.findall(r"(?m)^\s*-\s*id\s*:",text)),
    "platform_manual_markers":len(re.findall(r"(?m)^\s*-?\s*platform\s*:\s*manual\s*$",text)),
    "service_call_markers":len(re.findall(r"(?m)^\s*(?:service|action)\s*:",text)),
    "template_markers":len(re.findall(r"\{\{|\{%",text)),
    "bytes":len(data)}
 out["files"].append(o)
e=p/"esphome-enrolment-private.json"
out["esphome_stage_exists"]=e.is_file() and not e.is_symlink()
if out["esphome_stage_exists"]:
 d=json.loads(e.read_text()).get("data",{})
 out["esphome_stage_data_has_host"]=any(k in d for k in ("host","ip_address"))
 out["esphome_stage_data_has_noise_key"]=any("noise" in k.lower() or "key" in k.lower() for k in d)
 out["esphome_stage_data_has_port"]=any("port" in k.lower() for k in d)
print("JNS_SECURITY_STRUCTURE_AUDIT="+json.dumps(out,sort_keys=True))
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 code=base64.b64encode(SRC.encode()).decode()
 r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
    "-o","ConnectTimeout=6","nodeb",shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+code+"'))"])],capture_output=True,text=True,timeout=45)
 for x in r.stdout.splitlines():
  if x.startswith(("JNS_SECURITY_STRUCTURE_AUDIT=","JNS_SECURITY_STRUCTURE_BLOCKED=")):print(x,flush=True)
 print("JNS_NO_PRODUCTION_CHANGE=yes",flush=True)
 return 0 if r.returncode==0 else 1
if __name__=="__main__":raise SystemExit(main())
