#!/usr/bin/env python3
"""Read-only, privacy-safe JNS consolidation cutover preflight, 28 Oct 2026.
No guest writes, GPIO actions, config flow calls, restarts or power changes.
"""
import base64,json,os,re,shlex,subprocess,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
INNER=r'''
import json,pathlib,re
from collections import Counter
root=pathlib.Path("/config")
def entries(k):
 try:
  d=json.loads((root/".storage"/k).read_text()).get("data",{})
  key={"core.config_entries":"entries","core.device_registry":"devices","core.entity_registry":"entities"}[k]
  a=d.get(key,[])
  return a if isinstance(a,list) else []
 except (OSError,ValueError,TypeError):return []
ce=entries("core.config_entries")
devices=entries("core.device_registry")
entities=entries("core.entity_registry")
domains=Counter(x.get("domain","") for x in ce if isinstance(x,dict) and not x.get("disabled_by"))
ids=Counter(str(x.get("platform","")) for x in entities if isinstance(x,dict))
mobile_ids=set(str(x.get("entry_id","")) for x in ce if isinstance(x,dict) and x.get("domain")=="mobile_app" and not x.get("disabled_by"))
mobile_dev=sum(any(isinstance(c,(list,tuple)) and len(c)>=1 and str(c[0])=="mobile_app" for c in (d.get("identifiers") or [])) for d in devices if isinstance(d,dict))
mobile_device_links=sum(bool(set(str(i) for i in d.get("config_entries",[]))&mobile_ids) for d in devices if isinstance(d,dict))
mobile_app_entries=sum(x.get("domain")=="mobile_app" for x in ce if isinstance(x,dict))
mobile_app_entities=sum(x.get("platform")=="mobile_app" for x in entities if isinstance(x,dict))
esphome_ids=set(str(x.get("entry_id")) for x in ce if isinstance(x,dict) and x.get("domain")=="esphome" and not x.get("disabled_by"))
esphome_dev=sum(bool(set(str(i) for i in d.get("config_entries",[]))&esphome_ids) for d in devices if isinstance(d,dict))
cfg=root/"configuration.yaml"
try:t=cfg.read_text(errors="replace")
except OSError:t=""
try:
 packages=[p for p in (root/"packages").glob("*.yaml") if p.is_file() and not p.is_symlink()]
except OSError:packages=[]
out={
 "config_entries_total":len(ce),"devices_total":len(devices),"entities_total":len(entities),
 "native_mobile_app_explicit":bool(re.search(r"(?m)^mobile_app\s*:",t)),
 "mobile_app_entries":mobile_app_entries,"mobile_linked_devices":mobile_device_links,
 "mobile_identifier_devices":mobile_dev,"mobile_platform_entities":mobile_app_entities,
 "esphome_entries":domains.get("esphome",0),"esphome_linked_devices":esphome_dev,
 "esphome_platform_entities":ids.get("esphome",0),
 "manual_alarm_yaml":bool(re.search(r"(?m)^\s*-?\s*platform\s*:\s*manual\s*$",t)),
 "alarm_control_panel_entities":sum(str(x.get("entity_id","")).startswith("alarm_control_panel.") for x in entities if isinstance(x,dict)),
 "native_automation_platform_entities":ids.get("automation",0),
 "native_script_platform_entities":ids.get("script",0),
 "mqtt_integration":domains.get("mqtt",0),
 "remote_homeassistant_integration":domains.get("remote_homeassistant",0),
 "has_security_helper_package":(root/"packages/jns_ha_security_passive_helpers_20261027.yaml").is_file(),
 "packages_count":len(packages),
}
print("JNS_HA_CUTOVER_PRIVATE_CORE="+json.dumps(out,sort_keys=True))
'''
HOST=r'''
import json,os,pathlib,subprocess
out={"host":os.uname().nodename.split(".")[0]}
base=pathlib.Path("/var/lib/jns-solar/consolidation/ha-security-906-20261027-v1")
out["security_yaml_stage_present"]=(base/"manifest.json").is_file()
out["esphome_private_stage_present"]=(base/"esphome-enrolment-private.json").is_file()
out["archive_manifests_present"]={
 "905":pathlib.Path("/mnt/pve/NAS/dump/jns-ha-general-consolidation-20261027-v1/MANIFEST.json").is_file(),
 "902":pathlib.Path("/mnt/pve/NAS/dump/jns-vm902-consolidation-20261027-v1/MANIFEST.json").is_file(),
 "906":pathlib.Path("/mnt/pve/NAS/dump/jns-vm906-agent-recovery-20261026-v1/MANIFEST.json").is_file()}
r=subprocess.run(["free","-m"],capture_output=True,text=True)
try:out["host_mem_available_mib"]=next(int(x.split()[6]) for x in r.stdout.splitlines() if x.startswith("Mem:"))
except (StopIteration,IndexError,ValueError):pass
print("JNS_SECURITY_STAGE_READONLY="+json.dumps(out,sort_keys=True))
'''
def ssh(host,args,timeout=30):
 try:r=subprocess.run(SSH+[host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return r.stdout if r.returncode==0 else None
def guest(host,vm,args):
 s=ssh(host,["qm","guest","exec",str(vm),"--",*args],40)
 if not s:return None
 try:j=json.loads(s)
 except ValueError:return None
 for _ in range(70):
  if j.get("exited"):return j if j.get("exitcode")==0 else None
  if not j.get("pid"):break
  time.sleep(.4)
  s=ssh(host,["qm","guest","exec-status",str(vm),str(j["pid"])],18)
  if not s:break
  try:j=json.loads(s)
  except ValueError:break
 return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_CUTOVER_PREFLIGHT_BLOCKED=wrong_runner");return 1
 summaries={}
 for role,host,vm in (("general","nodeb",905),("primary","nodea",902),("security","nodea",906)):
  stat=ssh(host,["qm","status",str(vm)],17)
  is_running=bool(stat and stat.strip()=="status: running")
  out={"role":role,"host":host,"vm":vm,"running":is_running}
  if is_running:
   core_status=guest(host,vm,["ha","core","info"])
   out["ha_core_info_responding"]=bool(core_status and core_status.get("exitcode")==0)
   b=base64.b64encode(INNER.encode()).decode()
   j=guest(host,vm,["docker","exec","homeassistant","python3","-c","exec(__import__('base64').b64decode('"+b+"'))"])
   if j:
    lines=[x.split("=",1)[1] for x in (j.get("out-data") or "").splitlines() if x.startswith("JNS_HA_CUTOVER_PRIVATE_CORE=")]
    if len(lines)==1:
     try:out["core"]=json.loads(lines[0])
     except ValueError:out["core"]="unavailable"
  summaries[role]=out
  print("JNS_CUTOVER_ROLE="+json.dumps(out,sort_keys=True),flush=True)
 b=base64.b64encode(HOST.encode()).decode()
 v=ssh("nodeb",["python3","-c","exec(__import__('base64').b64decode('"+b+"'))"],27)
 lines=[x for x in (v or "").splitlines() if x.startswith("JNS_SECURITY_STAGE_READONLY=")]
 if len(lines)==1:print(lines[0],flush=True)
 # Security handover may be in its approved, timed maintenance interval.
 # Read-only freshness check: verify the Node A failsafe instead of treating
 # deliberately stopped VM906 as an unexpected source-controller failure.
 timer=ssh("nodea",["systemctl","is-active","jns-ha906-recovery-20261028.timer"],17)
 timer_active=bool(timer and timer.strip()=="active")
 target_config=ssh("nodeb",["qm","config","905"],17) or ""
 native_src='''import json,pathlib
p=pathlib.Path("/config/packages/jns_ha_security_native_cutover_20261028_v2.yaml")
s=p.read_text() if p.is_file() and not p.is_symlink() else ""
print("JNS_NATIVE_CUTOVER_AUDIT="+json.dumps({"package_present":bool(s),"manual_alarm_present":"alarm_control_panel:" in s,"disabled_automations_declared":s.count("initial_state: false"),"esphome_entry_known":False},sort_keys=True))
'''
 payload=base64.b64encode(native_src.encode()).decode()
 check=guest("nodeb",905,["docker","exec","homeassistant","python3","-c","exec(__import__('base64').b64decode('"+payload+"'))"])
 marker=[x.split("=",1)[1] for x in str((check or {}).get("out-data","")).splitlines() if x.startswith("JNS_NATIVE_CUTOVER_AUDIT=")]
 try: native=json.loads(marker[0]) if len(marker)==1 else None
 except ValueError:native=None
 source=summaries.get("security",{})
 general=summaries.get("general",{})
 primary=summaries.get("primary",{})
 source_offline=not source.get("running") and (ssh("nodea",["qm","status","906"],17) or "").strip()=="status: stopped"
 gates={"vm905_running":bool(general.get("running")),"vm902_running":bool(primary.get("running")),
        "vm906_running":bool(source.get("running")),"vm906_isolated":source_offline,
        "vm906_recovery_timer_active":timer_active,"native_alarm_v2":native,
        "vm905_name_guard":bool(re.search(r"(?m)^name: ha-s2-general$",target_config))}
 print("JNS_SECURITY_POSTCUTOVER_READONLY="+json.dumps(gates,sort_keys=True),flush=True)
 print("JNS_HA_CUTOVER_READ_ONLY=yes",flush=True)
 security_safe=bool(source.get("running") and isinstance(source.get("core"),dict)) or bool(source_offline and timer_active and isinstance(native,dict) and native.get("package_present") and native.get("disabled_automations_declared")==6)
 return 0 if (general.get("running") and isinstance(general.get("core"),dict) and primary.get("running") and isinstance(primary.get("core"),dict) and security_safe) else 1
if __name__=="__main__":raise SystemExit(main())
