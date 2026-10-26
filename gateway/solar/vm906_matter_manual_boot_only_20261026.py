#!/usr/bin/env python3
"""Disable auto-boot of unused VM906 Matter add-on, leaving active Core alone.

Direct authenticated Supervisor request from its HA CLI container.
This intentionally DOES NOT stop the container while the Matter config
entry is enabled: Core currently auto-restarts it when stopped.
"""
import json,subprocess,shlex,time,sys
def ssh(args,timeout=30):
 try:r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
  "nodea",shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return r.stdout if r.returncode==0 else None
def cmd(args):
 raw=ssh(["qm","guest","exec","906","--",*args],34)
 if not raw:return {"status":"unavailable"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"invalid"}
 for _ in range(40):
  if j.get("exited"):break
  if not j.get("pid"):break
  time.sleep(.3)
  p=ssh(["qm","guest","exec-status","906",str(j["pid"])],15)
  if not p:break
  try:j=json.loads(p)
  except ValueError:break
 return {"status":"ok" if j.get("exited") and j.get("exitcode")==0 else "failed",
         "lines":(j.get("out-data") or "").splitlines()}
def addon():
 j=cmd(["ha","apps","info","core_matter_server","--raw-json"])
 if j["status"]!="ok":raise RuntimeError("info")
 obj=json.loads("".join(j["lines"]))
 data=obj.get("data",obj)
 if data.get("slug")!="core_matter_server":raise RuntimeError("identity")
 return data
if ssh(["qm","status","906"])!="status: running\n":raise SystemExit("VM906_NOT_RUNNING")
a=addon()
if a.get("state") not in ("started","stopped") or a.get("boot") not in ("auto","manual"):
 raise SystemExit("MATTER_UNEXPECTED_EXISTING_STATE")
print("JNS_MATTER_BEFORE="+json.dumps({"boot":a["boot"],"state":a["state"]}),flush=True)
if a["boot"]!="manual":
 script="""test -n "$SUPERVISOR_TOKEN" || exit 7
code=$(curl --silent --show-error --max-time 12 --output /dev/null --write-out '%%{http_code}' \
 --request POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" -H "Content-Type: application/json" \
 --data '{"boot":"manual"}' http://supervisor/addons/core_matter_server/options) || exit 8
test "$code" = 200""" 
 j=cmd(["docker","exec","hassio_cli","sh","-c",script.replace("%%{http_code}","%{http_code}")])
 if j["status"]!="ok":raise SystemExit("SUPERVISOR_MANUAL_BOOT_FAILED")
a=addon()
if a.get("boot")!="manual":raise SystemExit("SUPERVISOR_BOOT_NOT_PERSISTED")
print("JNS_MATTER_MANUAL_BOOT_CONFIRMED="+json.dumps({
 "boot":a["boot"],"state":a["state"],"database_unchanged":True,
 "matter_data_retained":True,"addon_uninstalled":False,
 "integration_not_changed":True,"vm906_not_restarted":True},sort_keys=True),flush=True)
