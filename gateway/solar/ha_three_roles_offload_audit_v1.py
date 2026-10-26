#!/usr/bin/env python3
"""JNS HA architecture: live, read-only resource/offload candidate audit.
Only aggregate metrics. Does not emit secrets, URLs, IPs, entity names,
DB rows, config source, automation contents, or log text.
"""
import base64,json,shlex,subprocess,time,re
ROLE=[("ha-primary",902,"nodea"),("ha-general",905,"nodeb"),("ha-security",906,"nodea")]
PAYLOAD=r'''
import json,re,os,subprocess,pathlib,time
from collections import Counter
ROOT=pathlib.Path("/config");d={"read_only":True,"config_exists":ROOT.is_dir()}
def mb(x):return round(x/1048576,2)
def file(n):
 p=ROOT/n
 try:
  if not p.is_file() or p.is_symlink():return {"present":False}
  st=p.stat()
  return {"present":True,"bytes":st.st_size,"size_MiB":mb(st.st_size)}
 except OSError:return {"present":"unknown"}
def fdir(n):
 p=ROOT/n
 if not p.is_dir():return {"present":False}
 size=0;count=0;symlinks=0
 try:
  for v in p.rglob("*"):
   if v.is_symlink():symlinks+=1;continue
   if v.is_file():size+=v.stat().st_size;count+=1
 except (OSError,PermissionError):return {"present":True,"readable":False}
 return {"present":True,"files":count,"size_MiB":mb(size),"symlinks":symlinks}
for name in ("home-assistant_v2.db","home-assistant_v2.db-wal","home-assistant_v2.db-shm","home-assistant.log","home-assistant.log.1","automations.yaml","scripts.yaml","configuration.yaml","secrets.yaml"):
 d["file_"+name.replace(".","_")]=file(name)
for name in ("packages","custom_components","media","www","esphome","backups","tts"):
 d["dir_"+name]=fdir(name)
store=ROOT/".storage"
for n in ("core.config_entries","core.entity_registry","core.device_registry","recorder","core.restore_state","lovelace"):
 d["storage_"+n.replace(".","_")]=file(".storage/"+n)
def registry(n,key):
 try:
  a=json.loads((store/n).read_text())
  value=a.get("data",{}).get(key,[])
  return value if isinstance(value,list) else []
 except (OSError,ValueError,TypeError):return []
entities=registry("core.entity_registry","entities")
configs=registry("core.config_entries","entries")
devices=registry("core.device_registry","devices")
d["entities_total"]=len(entities)
d["automation_entities"]=sum(x.get("platform")=="automation" for x in entities)
d["integrations_total"]=len(configs)
d["integration_unique_domains"]=len(set(x.get("domain") for x in configs))
d["devices_total"]=len(devices)
# Only non-identifying known core/provider integration domains, no user-defined names.
known=("recorder","history","logbook","mqtt","zha","esphome","hacs","onvif","tapo","piper","mpd",
       "mobile_app","honeywell","lyric","stream","go2rtc","camera","ffmpeg","dlna_dmr",
       "jns_heating_zones","influxdb","mariadb","mysql","sql","systemmonitor","bluetooth",
       "backup","wake_on_lan","template","rest","homekit","matter","sharkiq")
counts=Counter(str(x.get("domain","")) for x in configs)
d["known_config_entries"]={k:counts[k] for k in known if counts[k]}
d["automation_yaml_present"]=file("automations.yaml").get("present")
# Parse top-level YAML with HA's !include/!secret tags safely as plain text:
# never print values, keep only accepted named switches/flags.
cfg=ROOT/"configuration.yaml"
try:
 text=cfg.read_text(errors="replace")
 d["configuration_recorder_section_present"]=bool(re.search(r"(?m)^recorder\s*:",text))
 d["configuration_recorder_db_url_key"]=bool(re.search(r"(?m)^\s+db_url\s*:",text))
 d["configuration_recorder_purge_keep_days_key"]=bool(re.search(r"(?m)^\s+purge_keep_days\s*:",text))
 d["configuration_recorder_auto_purge_key"]=bool(re.search(r"(?m)^\s+auto_purge\s*:",text))
 d["configuration_recorder_include_exclude_key"]=bool(re.search(r"(?m)^\s+(include|exclude)\s*:",text))
 d["configuration_logger_section_present"]=bool(re.search(r"(?m)^logger\s*:",text))
 d["configuration_stream_section_present"]=bool(re.search(r"(?m)^stream\s*:",text))
 d["configuration_database_url_reference"]={
    "db_url_secret_reference":bool(re.search(r"(?m)^\s+db_url\s*:\s*!secret",text)),
    "db_url_mysql_literal":bool(re.search(r"(?m)^\s+db_url\s*:\s*[\"']?(mysql|mariadb)",text)),
    "db_url_postgres_literal":bool(re.search(r"(?m)^\s+db_url\s*:\s*[\"']?postgres",text)),
    "db_url_sqlite_literal":bool(re.search(r"(?m)^\s+db_url\s*:\s*[\"']?sqlite",text))
 }
except OSError:d["configuration_readable"]=False
d["component_categories"]={}
components=ROOT/"custom_components"
if components.is_dir():
 safe=("jns_heating_zones","jns_deployment","jns_native_area_sync","hacs","tuya_local",
       "localtuya","onvif","frigate","go2rtc","piper","sharkiq")
 d["component_categories"]={k:(components/k).is_dir() for k in safe}
try:
 with open("/proc/self/cgroup") as f:groups=f.read()
 match=re.search(r"0::(/[^\n]*)",groups)
 if match:
  root=pathlib.Path("/sys/fs/cgroup")/match.group(1).lstrip("/")
  metrics={}
  for n in ("memory.current","memory.max","memory.swap.current"):
   try:
    val=(root/n).read_text().strip()
    metrics[n.replace(".","_")]=round(int(val)/1048576,1) if val.isdecimal() else val[:20]
   except OSError:pass
  d["core_container_cgroup_memory_MiB"]=metrics
except OSError:pass
# Count CPU/memory major offenders by process *name only*, no full cmd.
try:
 ps=subprocess.run(["ps","-eo","comm=,rss=","--sort=-rss"],capture_output=True,text=True,timeout=8)
 if ps.returncode==0:
  top=[]
  for row in ps.stdout.splitlines()[:12]:
   bits=row.split()
   if len(bits)>=2 and bits[-1].isdigit():top.append({"name":bits[0][:32],"rss_MiB":round(int(bits[-1])/1024,1)})
  d["core_container_top_processes"]=top
except (OSError,subprocess.TimeoutExpired):pass
print("JNS_HA_INTERNALS_JSON="+json.dumps(d,sort_keys=True))
'''
def ssh(host,args,timeout=25):
 try:p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
       "-o","ConnectTimeout=5",host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def get_status(vm,host):
 raw=ssh(host,["qm","status",str(vm)])
 return raw.strip() if raw is not None else "unavailable"
def guest(vm,host):
 if get_status(vm,host)!="status: running":return {"status":"not_running"}
 token=base64.b64encode(PAYLOAD.encode()).decode()
 cmd=["qm","guest","exec",str(vm),"--","docker","exec","homeassistant","python3","-c",
      "exec(__import__('base64').b64decode('"+token+"'))"]
 raw=ssh(host,cmd,30)
 if raw is None:return {"status":"no_guest_agent_or_docker"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"guest_reply_not_json"}
 for i in range(12):
  if j.get("exited"):break
  if j.get("pid") is None:break
  time.sleep(.5)
  raw=ssh(host,["qm","guest","exec-status",str(vm),str(j["pid"])],13)
  if raw is None:break
  try:j=json.loads(raw)
  except ValueError:break
 if not j.get("exited"):return {"status":"guest_command_timeout"}
 if j.get("exitcode")!=0:return {"status":"guest_command_failed","exit_code":j.get("exitcode")}
 results=[l.split("=",1)[1] for l in (j.get("out-data") or "").splitlines() if l.startswith("JNS_HA_INTERNALS_JSON=")]
 if not results:return {"status":"missing_payload"}
 try:return {"status":"ok",**json.loads(results[-1])}
 except ValueError:return {"status":"bad_safe_json"}
def host(vm,node):
 # node memory summary and PVE state, no raw guest settings
 raw=ssh(node,["pvesh","get",f"/nodes/{node}/qemu/{vm}/status/current","--output-format","json"])
 if raw is None:return {"status":"unavailable"}
 try:
  j=json.loads(raw)
  o={"status":j.get("status")}
  for k in ("mem","maxmem"):
   if isinstance(j.get(k),(int,float)):o[k+"_MiB"]=round(j[k]/1048576,1)
  return o
 except ValueError:return {"status":"invalid_json"}
def main():
 print("JNS_HA_TRIPLE_NODE_OFFLOAD_AUDIT_START",flush=True)
 for role,vm,node in ROLE:
  print("ROLE_"+role.upper().replace("-","_")+"="+json.dumps({
    "host":node,"vmid":vm,"pve":host(vm,node),"core":guest(vm,node)},sort_keys=True),flush=True)
 print("JNS_HA_TRIPLE_NODE_OFFLOAD_AUDIT_END",flush=True)
if __name__=="__main__":main()
