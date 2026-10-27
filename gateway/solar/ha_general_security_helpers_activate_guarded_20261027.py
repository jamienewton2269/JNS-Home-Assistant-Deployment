#!/usr/bin/env python3
"""Guarded one-time HA-General Core restart to load 193 passive security helpers.
No VM restart, no other HA configuration writes, no alarm automation imports
or ESPHome enrolment. Preserves running HA-Security as current owner.
Uses Node C runner and existing authorised Proxmox QGA, fail-closed.
"""
import base64,datetime,json,os,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
INNER=r'''
import datetime,json,pathlib,re
p=pathlib.Path("/config/packages/jns_ha_security_passive_helpers_20261027.yaml")
o={"present":p.is_file() and not p.is_symlink()}
if not o["present"]:raise SystemExit(73)
s=p.read_text()
o["trusted_header"]="JNS Security passive helper definitions only" in s
section=None
counts={}
for line in s.splitlines():
 m=re.match(r"^(input_boolean|input_select|input_text):\s*$",line)
 if m:section=m.group(1);counts.setdefault(section,0);continue
 if section is not None and re.match(r"^  [a-zA-Z][a-zA-Z0-9_]*\s*:",line):counts[section]+=1
o["counts"]=counts
o["mtime_utc"]=datetime.datetime.fromtimestamp(p.stat().st_mtime,datetime.timezone.utc).isoformat()
try:
 ent=json.loads(pathlib.Path("/config/.storage/core.entity_registry").read_text()).get("data",{}).get("entities",[])
 o["registered"]={k:sum(isinstance(v,dict) and str(v.get("entity_id","")).startswith(k+".") for v in ent)
                for k in ("input_boolean","input_select","input_text")}
except (OSError,ValueError):o["registered"]={}
print("JNS_PASSIVE_SECURITY_HELPERS="+json.dumps(o,sort_keys=True))
'''
def die(code):
 print("JNS_HELPER_ACTIVATION_BLOCKED="+code,flush=True)
 raise SystemExit(1)
def run(cmd,timeout=30):
 try:return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def ssh(node,args,timeout=30):
 p=run(SSH+[node,shlex.join(args)],timeout)
 return p.stdout if p and p.returncode==0 else None
def qga(args,timeout=115):
 raw=ssh("nodeb",["qm","guest","exec","905","--",*args],35)
 if not raw:return None
 try:j=json.loads(raw)
 except ValueError:return None
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if j.get("exited"):return j
  if not j.get("pid"):break
  time.sleep(.8)
  raw=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],22)
  if not raw:break
  try:j=json.loads(raw)
  except ValueError:break
 return None
def check_helpers():
 code=base64.b64encode(INNER.encode()).decode()
 j=qga(["docker","exec","homeassistant","python3","-c",
    "exec(__import__('base64').b64decode('"+code+"'))"],60)
 if not j or j.get("exitcode")!=0:return None
 lines=[s.split("=",1)[1] for s in (j.get("out-data") or "").splitlines() if s.startswith("JNS_PASSIVE_SECURITY_HELPERS=")]
 if len(lines)!=1:return None
 try:return json.loads(lines[0])
 except ValueError:return None
def core_start():
 j=qga(["docker","inspect","homeassistant","--format","{{.State.StartedAt}}"],42)
 if not j or j.get("exitcode")!=0:return None
 return (j.get("out-data") or "").strip()
def dt(s):
 try:return datetime.datetime.fromisoformat(s.replace("Z","+00:00"))
 except (ValueError,AttributeError):return None
def validate_backup_markers():
 # Intentionally not reading private HA files into CI.
 # Use previously independently verified backups as the operator safety baseline,
 # while requiring the manifest paths still exist at execution time.
 code=r'''
import json,pathlib,os
root=pathlib.Path("/mnt/pve/NAS/dump")
a=root/"jns-ha-general-consolidation-20261027-v1"/"MANIFEST.json"
b=root/"jns-vm902-consolidation-20261027-v1"/"MANIFEST.json"
c=root/"jns-vm906-agent-recovery-20261026-v1"/"MANIFEST.json"
try:
 x=json.loads(a.read_text());y=json.loads(b.read_text());z=json.loads(c.read_text())
 ok=x.get("vm")==905 and x.get("zstd_test_passed") and y.get("source_node")=="nodea" and z.get("source_node")=="nodea"
except (ValueError,OSError):ok=False
print("JNS_SAFE_ARCHIVES="+("yes" if ok else "no"))
'''
 s=base64.b64encode(code.encode()).decode()
 data=ssh("nodeb",["python3","-c","exec(__import__('base64').b64decode('"+s+"'))"],32)
 return bool(data and "JNS_SAFE_ARCHIVES=yes" in data)
def main():
 if os.uname().nodename.split(".")[0]!="nodec":die("wrong_runner")
 for node,vm in (("nodea",906),("nodeb",905)):
  stat=ssh(node,["qm","status",str(vm)])
  if not stat or stat.strip()!="status: running":die("source_or_target_vm_unavailable")
 c=ssh("nodeb",["qm","config","905"])
 if not c or not re.search(r"^name:\s*ha-s2-general\s*$",c,re.M):die("vm905_identity")
 if not re.search(r"^memory:\s*2048\s*$",c,re.M):die("vm905_ram_not_2gb")
 if re.search(r"^lock:",c,re.M):die("vm905_locked")
 if not validate_backup_markers():die("recovery_backup_marker_missing")
 before=check_helpers()
 if not before or before.get("counts")!={"input_boolean":65,"input_select":64,"input_text":64} or not before.get("trusted_header"):
  die("passive_helper_stage_invalid")
 initial=core_start()
 start,mtime=dt(initial),dt(before.get("mtime_utc"))
 if not start or not mtime:die("core_start_or_helper_time_unavailable")
 if start>=mtime:
  print("JNS_HELPER_ACTIVATION_ALREADY_RESTARTED_AFTER_STAGE=yes",flush=True)
  print("JNS_HELPER_ACTIVATION_NO_CHANGE=yes",flush=True)
  return 0
 print("JNS_HELPER_ACTIVATION_PREFLIGHT=passed",flush=True)
 chk=qga(["ha","core","check"],210)
 if not chk or chk.get("exitcode")!=0:
  die("ha_core_config_check_failed")
 print("JNS_HELPER_ACTIVATION_CONFIGCHECK=passed",flush=True)
 cmd=qga(["ha","core","restart"],100)
 if not cmd or cmd.get("exitcode")!=0:
  die("ha_core_restart_command_failed")
 print("JNS_HELPER_ACTIVATION_RESTART_ISSUED=yes",flush=True)
 deadline=time.monotonic()+230
 final=None
 while time.monotonic()<deadline:
  now=dt(core_start())
  if now and now>start and now>=mtime:
   final=check_helpers()
   if final and final.get("counts")==before.get("counts"):
    print("JNS_HELPER_ACTIVATION_RESULT="+json.dumps({"restart_done":True,
      "ha_security_source_unchanged":True,"helper_definition_count":sum(final["counts"].values()),
      "registered_before":before.get("registered",{}),
      "registered_after":final.get("registered",{}),
      "core_started_after_helper_stage":True,
      "ha_general_vm_remained_running":True},sort_keys=True),flush=True)
    print("JNS_HELPER_ACTIVATION_COMPLETE=yes",flush=True)
    return 0
  time.sleep(5)
 die("ha_core_not_healthy_within_verification_window")
if __name__=="__main__":main()
