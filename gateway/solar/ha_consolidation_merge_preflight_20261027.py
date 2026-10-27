#!/usr/bin/env python3
"""JNS consolidated HA VM905 preflight: strictly read-only and log-safe.

Runs via existing Node C GitHub Actions runner and authorised SSH/QGA.
No backups, restarts, configuration writes, token output, or guest control.
Never prints entity IDs, unique IDs, MACs, addresses, configuration values,
credentials, raw logs, or hashed identifiers. Uses an ephemeral random salt
for cross-instance entity overlap counting in runner memory only.
"""
import base64
import json
import re
import secrets
import shlex
import subprocess
import time

ROLES = (("ha-primary", "nodea", 902),
         ("ha-security", "nodea", 906),
         ("ha-general", "nodeb", 905))
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=6"]
INNER = r"""
import hashlib,hmac,json,pathlib,re,sys
from collections import Counter
root=pathlib.Path("/config")
salt=bytes.fromhex(sys.argv[1])
def json_data(name):
 try:
  p=root/".storage"/name
  if p.is_symlink():return {}
  d=json.loads(p.read_text())
  return d.get("data",{}) if isinstance(d,dict) else {}
 except (OSError,ValueError,TypeError):return {}
def hash_id(value):
 if not isinstance(value,str):return None
 return hmac.new(salt,value.encode(),hashlib.sha256).hexdigest()
entries=json_data("core.config_entries").get("entries",[])
entities=json_data("core.entity_registry").get("entities",[])
devices=json_data("core.device_registry").get("devices",[])
if not isinstance(entries,list):entries=[]
if not isinstance(entities,list):entities=[]
if not isinstance(devices,list):devices=[]
domains=Counter(str(x.get("domain","")) for x in entries if isinstance(x,dict))
enabled=Counter(str(x.get("domain","")) for x in entries if isinstance(x,dict) and not x.get("disabled_by"))
key_domains=("mobile_app","esphome","mqtt","remote_homeassistant","matter",
             "onvif","go2rtc","mpd","wyoming","piper","tuya_local","tuya",
             "lyric","jns_heating_zones","hassio","apple_tv","samsungtv")
counts=Counter()
hashes=set()
platform_counts=Counter()
owner_by_hash={}
for x in entities:
 if not isinstance(x,dict):continue
 entity=x.get("entity_id")
 if isinstance(entity,str):
  domain=entity.split(".",1)[0]
  counts[domain]+=1
  platform=str(x.get("platform", ""))
  platform_counts[platform]+=1
  hv=hash_id(entity)
  if hv:
   hashes.add(hv)
   owner_by_hash[hv]=platform
def present(name):
 p=root/name
 return p.is_file() and not p.is_symlink()
def dir_count(name):
 p=root/name
 if not p.is_dir():return {"present":False}
 try:return {"present":True,"files":sum(1 for f in p.rglob("*") if f.is_file() and not f.is_symlink())}
 except (OSError,PermissionError):return {"present":True,"files":"unavailable"}
def yaml_markers(name):
 p=root/name
 try:
  if p.is_symlink() or not p.is_file():return 0
  return len(re.findall(r"(?m)^\s*-\s+id\s*:",p.read_text(errors="replace")))
 except OSError:return -1
def sized(name):
 p=root/name
 try:return round(p.stat().st_size/1048576,2) if p.is_file() and not p.is_symlink() else None
 except OSError:return None
def layout():
 allowed=("alarm_control_panel","automation","script","template","mqtt",
          "input_boolean","input_select","input_number","input_text",
          "sensor","binary_sensor","switch","light","camera","esphome",
          "notify","homeassistant","recorder","frontend","lovelace",
          "group","rest","utility_meter","timer","counter","scene")
 out={"main_sections":{},"package_sections":{},"package_yaml_count":0,
      "packages_include_reference":False,"yaml_automations":yaml_markers("automations.yaml")}
 cfg=root/"configuration.yaml"
 try:
  content=cfg.read_text(errors="replace") if cfg.is_file() and not cfg.is_symlink() else ""
 except OSError:content=""
 out["packages_include_reference"]=bool(re.search(r"(?m)^\s*packages\s*:\s*!include_dir_",content))
 out["homeassistant_section_present"]=bool(re.search(r"(?m)^homeassistant\s*:",content))
 out["default_config_declared"]=bool(re.search(r"(?m)^default_config\s*:",content))
 out["mobile_app_explicitly_declared"]=bool(re.search(r"(?m)^mobile_app\s*:",content))
 for key in allowed:
  if re.search(r"(?m)^"+re.escape(key)+r"\s*:",content):
   out["main_sections"][key]=1
 p=root/"packages"
 if p.is_dir() and not p.is_symlink():
  sections=Counter()
  for f in p.rglob("*.yaml"):
   if f.is_symlink() or not f.is_file():continue
   out["package_yaml_count"]+=1
   if out["package_yaml_count"]>100:break
   try:body=f.read_text(errors="replace")
   except OSError:continue
   for k in allowed:
    if re.search(r"(?m)^"+re.escape(k)+r"\s*:",body):sections[k]+=1
  out["package_sections"]=dict(sorted(sections.items()))
 return out
def guest_meminfo():
 try:
  source=pathlib.Path("/proc/meminfo").read_text()
 except OSError:return {}
 out={}
 for k in ("MemTotal","MemAvailable","SwapFree","SwapTotal"):
  m=re.search(r"(?m)^"+k+r":\s*(\d+) kB",source)
  if m:out[k+"_mib"]=round(int(m.group(1))/1024,1)
 return out
out={"read_only":True,"registry_entities":len(entities),"registry_devices":len(devices),
     "config_entries":len(entries),"enabled_entries":sum(enabled.values()),
     "integration_domains":{x:domains[x] for x in key_domains if domains[x]},
     "enabled_integration_domains":{x:enabled[x] for x in key_domains if enabled[x]},
     "entity_categories":{k:counts[k] for k in
         ("automation","script","alarm_control_panel","siren","lock",
          "binary_sensor","camera","media_player","notify","device_tracker",
          "button","event","light","climate","sensor","switch") if counts[k]},
     "files":{"automations_yaml":present("automations.yaml"),
              "scripts_yaml":present("scripts.yaml"),
              "scenes_yaml":present("scenes.yaml"),
              "configuration_yaml":present("configuration.yaml"),
              "secrets_yaml":present("secrets.yaml")},
     "automation_yaml_id_markers_approx":yaml_markers("automations.yaml"),
     "packages":dir_count("packages"),
     "custom_components":dir_count("custom_components"),
     "esphome":dir_count("esphome"),
     "sqlite_mib":sized("home-assistant_v2.db"),
     "sqlite_wal_mib":sized("home-assistant_v2.db-wal"),
     "migration_yaml_layout":layout(),
     "guest_meminfo":guest_meminfo(),
     "entity_platform_families":{k:platform_counts[k] for k in
         ("remote_homeassistant","mqtt","esphome","mobile_app","template",
          "automation","script","group","hassio","matter","onvif") if platform_counts[k]},
     "_entity_hashes":list(hashes),"_entity_owner_by_hash":owner_by_hash}
print("JNS_PRIVATE_AUDIT="+json.dumps(out,sort_keys=True))
"""
def run(argv, timeout=25):
 try:return subprocess.run(argv,text=True,capture_output=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def ssh(host, argv, timeout=25):
 p=run(SSH+[host,shlex.join(argv)],timeout)
 return p.stdout if p and p.returncode==0 else None
def guest(host,vm,salt):
 out={"status":"unavailable","host":host,"vm":vm}
 state=ssh(host,["qm","status",str(vm)])
 if not state:return out
 out["status"]=state.strip().removeprefix("status: ")
 if out["status"]!="running":return out
 source=base64.b64encode(INNER.encode()).decode("ascii")
 cmd=["qm","guest","exec",str(vm),"--","docker","exec","homeassistant",
      "python3","-c","exec(__import__('base64').b64decode('"+source+"'))",salt]
 raw=ssh(host,cmd,38)
 if raw is None:
  out["audit"]="agent_or_access_unavailable"
  return out
 try:j=json.loads(raw)
 except ValueError:
  out["audit"]="invalid_agent_reply"
  return out
 for _ in range(45):
  if j.get("exited"):break
  if not j.get("pid"):break
  time.sleep(.35)
  raw=ssh(host,["qm","guest","exec-status",str(vm),str(j["pid"])],18)
  if raw is None:break
  try:j=json.loads(raw)
  except ValueError:break
 if not j.get("exited") or j.get("exitcode")!=0:
  out["audit"]="guest_command_not_completed"
  return out
 safe=[x.split("=",1)[1] for x in str(j.get("out-data","")).splitlines() if x.startswith("JNS_PRIVATE_AUDIT=")]
 if len(safe)!=1:
  out["audit"]="no_valid_payload"
  return out
 try:payload=json.loads(safe[0])
 except ValueError:
  out["audit"]="invalid_payload"
  return out
 if not payload.get("read_only"):
  out["audit"]="unexpected_payload"
  return out
 hashes=set(payload.pop("_entity_hashes",[]))
 owners=payload.pop("_entity_owner_by_hash",{})
 out["audit"]="ok"
 out["summary"]=payload
 return out,hashes,owners
def host_memory(node):
 raw=ssh(node,["free","-m"],18)
 if not raw:return {"status":"unavailable"}
 for row in raw.splitlines():
  cols=row.split()
  if cols and cols[0]=="Mem:" and len(cols)>=7:
   try:return {"status":"ok","total_mib":int(cols[1]),"available_mib":int(cols[6])}
   except ValueError:break
 return {"status":"unavailable"}
def main():
 print("JNS_HA_CONSOLIDATION_PREFLIGHT_BEGIN",flush=True)
 salt=secrets.token_hex(24)
 summary={}
 hashes={}
 ownership={}
 for role,host,vm in ROLES:
  res=guest(host,vm,salt)
  if isinstance(res,tuple):status,hashed,owners=res
  else:status,hashed,owners=res,set(),{}
  summary[role]=status
  hashes[role]=hashed
  ownership[role]=owners
  print("JNS_ROLE="+json.dumps({"role":role,**status},sort_keys=True),flush=True)
 for host in ("nodea","nodeb"):
  print("JNS_HOST_MEMORY="+json.dumps({"host":host,**host_memory(host)},sort_keys=True),flush=True)
 if all(summary[r].get("audit")=="ok" for r,_,_ in ROLES):
  overlaps={}
  for r in ("ha-primary","ha-security"):
   overlaps[r+"_vs_ha-general"]=len(hashes[r]&hashes["ha-general"])
  overlaps["primary_vs_security"]=len(hashes["ha-primary"]&hashes["ha-security"])
  print("JNS_ENTITY_COLLISIONS_COUNTS_ONLY="+json.dumps(overlaps,sort_keys=True),flush=True)
  for source in ("ha-primary","ha-security"):
   shared=hashes[source]&hashes["ha-general"]
   mirror_src=sum(ownership[source].get(h)=="remote_homeassistant" for h in shared)
   mirror_general=sum(ownership["ha-general"].get(h)=="remote_homeassistant" for h in shared)
   print("JNS_COLLISION_OWNERSHIP="+json.dumps({"source":source,
        "overlaps":len(shared),"mirrored_in_source":mirror_src,
        "mirrored_in_general":mirror_general,
        "other_source_platforms":len(shared)-mirror_src},sort_keys=True),flush=True)
  print("JNS_PREFLIGHT_COMPLETE=YES",flush=True)
 else:
  print("JNS_PREFLIGHT_COMPLETE=NO",flush=True)
 print("JNS_NO_STATE_CHANGED=YES",flush=True)
if __name__=="__main__":
 main()
