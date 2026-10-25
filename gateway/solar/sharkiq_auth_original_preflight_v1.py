#!/usr/bin/env python3
"""SharkIQ read-only HA902/HA905 audit + HA900 offline-disk access check.
NEVER emit log lines or secrets/tokens/email/device IDs; output only metadata.
"""
import json,base64,subprocess,shlex,time
HOSTS={902:"nodea",905:"nodeb"}
PAYLOAD=r'''
import json,re
from pathlib import Path
from importlib import metadata
base=Path("/config")
s=base/".storage"
out={"integration":"sharkiq"}
try:
 d=json.loads((s/"core.config_entries").read_text())
 entries=[e for e in d.get("data",{}).get("entries",[]) if e.get("domain")=="sharkiq"]
 out["entry_count"]=len(entries)
 out["entries"]=[]
 for e in entries:
  x={"disabled":bool(e.get("disabled_by")),"source":e.get("source"),
     "version":e.get("version"),
     "data_keys":sorted(e.get("data",{}).keys()),"options_keys":sorted(e.get("options",{}).keys())}
  for k in ("region","europe","auth_method","auth_region"):
   v=e.get("data",{}).get(k)
   if isinstance(v,(str,bool)) and len(str(v))<30:x[k]=v
  out["entries"].append(x)
except (OSError,ValueError,TypeError):out["entry_count"]="unreadable"
try:
 d=json.loads((s/"core.entity_registry").read_text())
 out["registered_vacuum_count"]=sum(e.get("platform")=="sharkiq" and e.get("entity_id","").startswith("vacuum.") for e in d.get("data",{}).get("entities",[]))
except (OSError,ValueError,TypeError):out["registered_vacuum_count"]="unreadable"
out["custom_component_installed"]=(base/"custom_components/sharkiq").is_dir()
try:out["sdk_version"]=metadata.version("sharkiq")
except metadata.PackageNotFoundError:out["sdk_version"]="unavailable"
try:
 p=base/"home-assistant.log"
 with p.open("rb") as f:f.seek(max(0,p.stat().st_size-300000));raw=f.read().decode(errors="replace")
 shark="\n".join(l for l in raw.splitlines() if "sharkiq" in l.lower() or "sharkclean" in l.lower())
 out["error_categories"]={k:(v.lower() in shark.lower()) for k,v in {
   "suspicious_verification":"Suspicious request requires verification",
   "invalid_authentication":"Invalid authentication",
   "auth0_redirect_uri":"REDIRECT_URI",
   "rate_limited":"429",
   "integration_setup_failed":"ConfigEntryNotReady"}.items()}
except OSError:out["error_categories"]="unavailable"
print("JNS_SHARK_SAFE="+json.dumps(out,sort_keys=True))
'''
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5"]
def r(node,argv,timeout=20):
 try:p=subprocess.run(SSH+[node,shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def audit(vm,node):
 status=r(node,["qm","status",str(vm)],12)
 if not status or "running" not in status:return {"status":"not_running"}
 payload=base64.b64encode(PAYLOAD.encode()).decode()
 command=["qm","guest","exec",str(vm),"--","docker","exec","homeassistant",
          "python3","-c","exec(__import__('base64').b64decode('"+payload+"'))"]
 raw=r(node,command,30)
 if raw is None:return {"status":"guest_exec_unavailable"}
 try:d=json.loads(raw)
 except ValueError:return {"status":"non_json"}
 for i in range(10):
  if d.get("exited"):break
  if d.get("pid") is None:break
  time.sleep(1)
  raw=r(node,["qm","guest","exec-status",str(vm),str(d["pid"])],15)
  if raw is None:break
  try:d=json.loads(raw)
  except ValueError:break
 if not d.get("exited"):return {"status":"not_finished"}
 if d.get("exitcode")!=0:return {"status":"guest_failed"}
 safe=[x for x in d.get("out-data","").splitlines() if x.startswith("JNS_SHARK_SAFE=")]
 try:return {"status":"ok",**json.loads(safe[-1].split("=",1)[1])}
 except (IndexError,ValueError):return {"status":"missing_marker"}
def main():
 print("JNS_SHARKIQ_READONLY_AUDIT")
 cmd=["bash","-c",'''set -eu; test "$(hostname -s)" = nodea;
 qm status 900;
 qm config 900 | grep '^onboot:' || :;
 for k in guestfish virt-cat guestmount virt-ls jq qemu-img; do
  if command -v "$k" >/dev/null 2>&1; then echo "PRESENT_TOOL=$k"; fi;
 done;
 test ! -e /dev/zvol/vmdata/vm-900-disk-1 || echo 'HA900_ZVOL_PRESENT=yes'
 ''']
 print("LEGACY_NODEA="+json.dumps({"read_only":(r("nodea",cmd,20) or "unavailable").strip().splitlines()},sort_keys=True))
 for vm,node in HOSTS.items():
  print("VM"+str(vm)+"="+json.dumps(audit(vm,node),sort_keys=True))
 print("JNS_SHARKIQ_READONLY_AUDIT_COMPLETE")
if __name__=="__main__":main()
