#!/usr/bin/env python3
"""Post-restart smoke audit for unified HA-General: read-only.
No physical device actions, secrets, addresses, config edits or guest restarts.
"""
import base64,json,os,re,shlex,subprocess,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
INNER=r'''
import json,pathlib,re
from collections import Counter
base=pathlib.Path("/config")
out={}
try:
 text=(base/"configuration.yaml").read_text(errors="replace")
 out["default_config_configured"]=bool(re.search(r"(?m)^default_config\s*:",text))
 out["mobile_app_explicitly_configured"]=bool(re.search(r"(?m)^mobile_app\s*:",text))
except OSError:
 out["configuration_readable"]=False
try:
 e=json.loads((base/".storage/core.config_entries").read_text()).get("data",{}).get("entries",[])
 counts=Counter(str(x.get("domain","")) for x in e if isinstance(x,dict))
 out["integration_domains"]={k:counts[k] for k in ("mqtt","mobile_app","esphome","onvif","mpd","wyoming","lyric","tuya_local","jns_heating_zones") if counts[k]}
except (OSError,ValueError,TypeError):out["integration_audit_unavailable"]=True
try:
 entities=json.loads((base/".storage/core.entity_registry").read_text()).get("data",{}).get("entities",[])
 def count_domain(d):return sum(isinstance(x,dict) and str(x.get("entity_id","")).startswith(d+".") for x in entities)
 out["registered_entities_total"]=len(entities)
 out["automation_registered"]=count_domain("automation")
 out["mobile_app_entities"]=sum(isinstance(x,dict) and x.get("platform")=="mobile_app" for x in entities)
 out["security_helper_registered_total"]=sum(count_domain(d) for d in ("input_boolean","input_select","input_text"))
 out["camera_registered"]=count_domain("camera")
 out["lights_registered"]=count_domain("light")
except (OSError,ValueError,TypeError):out["entities_unavailable"]=True
print("JNS_POST_RESTART_CORE_AUDIT="+json.dumps(out,sort_keys=True))
'''
def run(args,timeout=28):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def ssh(node,args,timeout=25):
 p=run(SSH+[node,shlex.join(args)],timeout)
 return p.stdout if p and p.returncode==0 else None
def guest(args,timeout=65):
 s=ssh("nodeb",["qm","guest","exec","905","--",*args],35)
 if not s:return None
 try:j=json.loads(s)
 except ValueError:return None
 for _ in range(45):
  if j.get("exited"):return j
  if not j.get("pid"):break
  time.sleep(.45)
  s=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],20)
  if not s:break
  try:j=json.loads(s)
  except ValueError:break
 return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_SMOKE_BLOCKED=wrong_runner");return 1
 result={"read_only":True}
 for node,vm in (("nodeb",905),("nodea",902),("nodea",906)):
  state=ssh(node,["qm","status",str(vm)])
  result["vm"+str(vm)+"_running"]=bool(state and state.strip()=="status: running")
 for ct,svc in ((212,"mosquitto"),(214,"zigbee2mqtt"),(216,"chrony"),(248,"jns-dns")):
  state=ssh("nodeb",["pct","status",str(ct)])
  key="nodeb_ct"+str(ct)
  result[key+"_running"]=bool(state and state.strip()=="status: running")
  if result[key+"_running"]:
   active=ssh("nodeb",["pct","exec",str(ct),"--","systemctl","is-active",svc],30)
   result[key+"_service_active"]=bool(active and active.strip()=="active")
 p=ssh("nodeb",["free","-m"])
 if p:
  try:result["nodeb_host_available_mib"]=next(int(row.split()[6]) for row in p.splitlines() if row.startswith("Mem:"))
  except (StopIteration,ValueError,IndexError):pass
 info=guest(["ha","core","info"])
 result["ha_cli_core_info_ok"]=bool(info and info.get("exitcode")==0)
 src=base64.b64encode(INNER.encode()).decode()
 j=guest(["docker","exec","homeassistant","python3","-c","exec(__import__('base64').b64decode('"+src+"'))"])
 if j and j.get("exitcode")==0:
  rows=[x.split("=",1)[1] for x in str(j.get("out-data","")).splitlines() if x.startswith("JNS_POST_RESTART_CORE_AUDIT=")]
  if len(rows)==1:
   try:result["core"]=json.loads(rows[0])
   except ValueError:pass
 print("JNS_HA_GENERAL_POST_ACTIVATION_SMOKE="+json.dumps(result,sort_keys=True),flush=True)
 print("JNS_PHYSICAL_OUTPUTS_UNCHANGED=yes",flush=True)
 return 0 if result.get("vm905_running") and result.get("ha_cli_core_info_ok") else 1
if __name__=="__main__":raise SystemExit(main())
