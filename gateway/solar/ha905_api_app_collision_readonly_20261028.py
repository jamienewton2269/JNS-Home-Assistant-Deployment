#!/usr/bin/env python3
"""Diagnose one specific HAOS app's install/availability status read-only."""
import json,os,shlex,subprocess,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
HOST=r'''
import json,os,subprocess,time,pathlib
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
slug="local_jns_ha905_core_api_probe"
def command(args,timeout=45):
 r=subprocess.run(["qm","guest","exec","905","--",*args],
                  capture_output=True,text=True,timeout=20)
 if r.returncode:raise SystemExit(71)
 j=json.loads(r.stdout)
 deadline=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<deadline:
  if not j.get("pid"):raise SystemExit(72)
  time.sleep(.4)
  r=subprocess.run(["qm","guest","exec-status","905",str(j["pid"])],
                  capture_output=True,text=True,timeout=20)
  if r.returncode:raise SystemExit(73)
  j=json.loads(r.stdout)
 if not j.get("exited"):raise SystemExit(74)
 return j
j=command(["ha","apps","info",slug,"--raw-json"])
out=str(j.get("out-data","")).strip()
record={}
try:
 data=json.loads(out)
 record["json_parseable"]=True
 record["result"]=str(data.get("result","unknown")) if isinstance(data,dict) else "nondict"
 info=data.get("data",data) if isinstance(data,dict) else {}
 if not isinstance(info,dict):info={}
 record["installed"]=info.get("installed")
 record["available"]=info.get("available")
 record["state"]=str(info.get("state","unknown"))
 record["repository_local"]=info.get("repository")=="local"
 record["location_nonempty"]=bool(info.get("location"))
 record["has_install_field"]="installed" in info
 record["has_available_field"]="available" in info
except (ValueError,TypeError):
 record["json_parseable"]=False
record["cli_exit_code"]=j.get("exitcode")
record["source_folder_exists"]=command(["sh","-c","test -e /mnt/data/supervisor/apps/local/jns_ha905_core_api_probe"]).get("exitcode")==0
record["one_time_marker_present"]=pathlib.Path("/var/lib/jns-solar/consolidation/ha905-core-api-bridge-probe-20261028-v1/one-test-attempted.json").is_file()
print("JNS_HA905_API_APP_COLLISION_READONLY="+json.dumps(record,sort_keys=True))
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 import base64
 code=base64.b64encode(HOST.encode()).decode()
 args=SSH+["nodeb",shlex.join(["python3","-c",
   "exec(__import__('base64').b64decode('"+code+"'))"])]
 try:p=subprocess.run(args,text=True,capture_output=True,timeout=110)
 except (OSError,subprocess.TimeoutExpired):return 1
 rows=[x for x in p.stdout.splitlines() if x.startswith("JNS_HA905_API_APP_COLLISION_READONLY=")]
 if p.returncode or len(rows)!=1:
  print("JNS_HA905_API_APP_COLLISION_AUDIT_BLOCKED=private_read");return 1
 print(rows[0]);print("JNS_API_COLLISION_AUDIT_NO_GUEST_CHANGE=yes");return 0
if __name__=="__main__":raise SystemExit(main())
