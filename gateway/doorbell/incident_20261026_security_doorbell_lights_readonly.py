#!/usr/bin/env python3
"""Incident read-only audit: security KC868/doorbell/MQTT/porch PIR/light path.

Runs from Node C GitHub runner through existing strictly pinned SSH to Node A/B.
QGA into HA-Security VM906 and HA-General VM905; never mutates guest files,
integrations, configs, MQTT topics, Zigbee state or alarm devices.
Secrets, tokens, integration host and addresses must not enter logs.
"""
import base64,json,re,shlex,socket,subprocess,time
from datetime import datetime,timezone
PAYLOAD=r'''
from pathlib import Path
import json,re,os,sqlite3,datetime,collections
P=Path("/config")
safe_rx=re.compile(r"door.?bell|kc868|alarmpanel|door.?chime|security|porch|dogs?.?run|front.?door|garage.?light|welcome.?home|motion",re.I)
def load(n,k):
 try:
  z=json.loads((P/".storage"/n).read_text()).get("data",{}).get(k,[])
  return z if isinstance(z,list) else []
 except Exception:return []
ents=load("core.entity_registry","entities")
devs=load("core.device_registry","devices")
cfgs=load("core.config_entries","entries")
matches=[]
for e in ents:
 txt=" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name"))
 if safe_rx.search(txt):
  matches.append({"entity_id":e.get("entity_id"),"platform":e.get("platform"),
     "disabled":e.get("disabled_by"),"name":(e.get("name") or e.get("original_name") or "")[:90]})
matter=next((x for x in cfgs if x.get("domain")=="esphome"),{})
out={
 "role":os.environ.get("JNS_ROLE","unknown"),
 "integrations":{"esphome":sum(x.get("domain")=="esphome" and not x.get("disabled_by") for x in cfgs),
 "mqtt":sum(x.get("domain")=="mqtt" and not x.get("disabled_by") for x in cfgs),
 "matter":sum(x.get("domain")=="matter" and not x.get("disabled_by") for x in cfgs)},
 "matched_entities":matches[:90],"registered_automations":[],
 "kc868_registered":sum(bool(re.search(r"kc868|alarmpanel",str(x.get("name",""))+str(x.get("name_by_user","")),re.I)) for x in devs),
 "esphome_config_entry_disabled":matter.get("disabled_by"),
 "esphome_host_key_present":bool(isinstance(matter.get("data"),dict) and matter.get("data",{}).get("host")),
 "read_only":True
}
for e in ents:
 if e.get("platform")=="automation" and safe_rx.search(" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name"))):
  out["registered_automations"].append({"entity_id":e.get("entity_id"),
   "disabled":e.get("disabled_by"),"name":(e.get("name") or e.get("original_name") or "")[:110]})
for f in ["configuration.yaml","automations.yaml"]:
 p=P/f
 out[f+"_present"]=p.exists()
 if p.is_file():
  txt=p.read_text(errors="replace")
  out[f+"_bytes"]=len(txt.encode())
  if f=="configuration.yaml":
   out["packages_declared"]=bool(re.search(r"(?m)^\s*packages\s*:",txt))
   out["automation_include_declared"]=bool(re.search(r"(?m)^\s*automation\s*:",txt))
   out["mqtt_include_declared"]=bool(re.search(r"(?m)^\s*mqtt\s*:",txt))
p=P/"packages"
out["packages_file_count"]=len(list(p.glob("*.yaml"))) if p.is_dir() else 0
out["doorbell_package_present"]=bool((p/"jns_security_doorbell_recovery.yaml").is_file())
out["package_ids"]={}
for name in ("jns_security_doorbell_recovery.yaml",):
 fp=p/name
 if fp.is_file():
  s=fp.read_text(errors="replace")
  out["package_ids"][name]={key:key in s for key in ("1792316952337","1792512302559","jns_security_doorbell_siren_safety_off_v1")}
try:
 import yaml
 list_files=[P/"automations.yaml"]+sorted(p.glob("*.yaml")) if p.is_dir() else [P/"automations.yaml"]
 autos=[]
 for fp in list_files:
  if not fp.is_file():continue
  try:root=yaml.safe_load(fp.read_text())
  except Exception as exc:
   out.setdefault("automation_parse_errors",[]).append({"file":fp.name,"type":type(exc).__name__});continue
  aa=root if isinstance(root,list) else root.get("automation",[]) if isinstance(root,dict) else []
  if isinstance(aa,dict):aa=list(aa.values())
  if isinstance(aa,list):
   for a in aa:
    if isinstance(a,dict):
     title=str(a.get("alias",""))
     if safe_rx.search(title):
      autos.append({"source":fp.name,"alias":title[:100],"id":str(a.get("id",""))[:50],
         "trigger_kc868":bool(re.search("kc868|x15|doorbell|jns/security",str(a.get("triggers",a.get("trigger",""))),re.I)),
         "mqtt_event_publish":bool(re.search("mqtt.publish|jns/security/doorbell/press",str(a.get("actions",a.get("action",""))),re.I)),
         "targets":sorted(set(re.findall(r"(?:switch|light|siren|binary_sensor)\.[A-Za-z0-9_]+",str(a.get("actions",a.get("action",""))))))[:14],
         "trigger_types":sorted(set(re.findall(r"trigger['\"]?:\s*['\"]?([a-z_]+)",str(a.get("triggers",a.get("trigger",""))))))[:8]})
 out["matching_automation_yaml"]=autos[:60]
except ImportError:out["yaml_module"]="not_available"
# Registry restored states are historical and NOT the same as live entity states
try:
 restored=json.loads((P/".storage/core.restore_state").read_text()).get("data",{})
 rows=restored.get("states",[]) if isinstance(restored,dict) else restored
 out["last_restored_states"]=[{"id":x.get("state",{}).get("entity_id"),"state":x.get("state",{}).get("state"),"last_updated":x.get("state",{}).get("last_updated")}
  for x in rows if isinstance(x,dict) and isinstance(x.get("state"),dict) and (
   re.search(r"alarmpanel_kc868_a16_x15|alarmpanel_kc868_a16_y01|doorbell_sounder|security_publish|external_security_lights",str(x["state"].get("entity_id","")),re.I))][:20]
except Exception:out["last_restored_states_status"]="unavailable"
# Last history timestamps only for the incident chain. SQLite opened read-only, no PRAGMA writes.
db=P/"home-assistant_v2.db"
if db.is_file():
 try:
  c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=3)
  cur=c.cursor()
  out["history_last"]={}
  for name in (
    "binary_sensor.alarmpanel_kc868_a16_x15",
    "siren.alarmpanel_kc868_a16_y01",
    "automation.jns_security_publish_doorbell_press",
    "automation.doorbell_sounder_on_schedule",
    "automation.external_security_lights_porch_pir",
    "binary_sensor.0xa4c138b3446c34e1_occupancy",
    "switch.0x84fd27fffe9ce438",
    "switch.0xa4c138bda6ec8ea0"
  ):
   try:
    cur.execute("""SELECT s.state,s.last_updated_ts FROM states s
      JOIN states_meta m ON s.metadata_id=m.metadata_id
      WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 3""",(name,))
    rows=cur.fetchall()
    out["history_last"][name]=[{"state":st,"time_utc":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if isinstance(ts,(float,int)) else None} for st,ts in rows]
   except sqlite3.Error:out["history_last"][name]=[]
  c.close()
 except Exception as exc:out["recorder_read_status"]=type(exc).__name__
print("JNS_INCIDENT_HA_CONFIG="+json.dumps(out,sort_keys=True,default=str),flush=True)
'''
def run(cmd,timeout=35):
 try:return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def ssh(node,argv,timeout=33):
 p=run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",node,shlex.join(argv)],timeout)
 return p.stdout if p and p.returncode==0 else None
def guest(node,vm,code,timeout=35):
 enc=base64.b64encode(code.encode()).decode()
 raw=ssh(node,["qm","guest","exec",str(vm),"--","docker","exec","homeassistant","python3","-c",
               "exec(__import__('base64').b64decode('"+enc+"'))"],timeout)
 if not raw:return {"status":"qga_unavailable"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"invalid_qga"}
 for _ in range(40):
  if j.get("exited"):break
  if j.get("pid") is None:break
  time.sleep(.5)
  raw=ssh(node,["qm","guest","exec-status",str(vm),str(j["pid"])],14)
  if not raw:break
  try:j=json.loads(raw)
  except ValueError:break
 if not j.get("exited"):return {"status":"timeout"}
 if j.get("exitcode")!=0:return {"status":"error","exitcode":j.get("exitcode")}
 matches=[x.partition("=")[2] for x in (j.get("out-data") or "").splitlines() if x.startswith("JNS_INCIDENT_HA_CONFIG=")]
 try:return {"status":"ok",**json.loads(matches[-1])}
 except (IndexError,ValueError):return {"status":"no_safe_payload"}
def remote(node,script,timeout=35):
 enc=base64.b64encode(script.encode()).decode()
 p=ssh(node,["python3","-c","exec(__import__('base64').b64decode('"+enc+"'))"],timeout)
 try:return json.loads([l.partition("=")[2] for l in p.splitlines() if l.startswith("JNS_INCIDENT_NETWORK=")][-1])
 except (AttributeError,IndexError,ValueError):return {"access":"unavailable"}
NET=r'''
import json,os,socket,subprocess
node=os.uname().nodename.split(".")[0]
out={"node":node}
for host in ("alarmpanel.home.arpa","ha-security.home.arpa","ha-general.home.arpa","ha-primary.home.arpa"):
 rec={"dns":False,"has_v4":False,"has_v6":False}
 try:
  info=socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)
  rec["dns"]=bool(info);rec["has_v4"]=any(x[0]==socket.AF_INET for x in info);rec["has_v6"]=any(x[0]==socket.AF_INET6 for x in info)
 except OSError:pass
 for port in ((6053,80) if host=="alarmpanel.home.arpa" else (80,)):
  try:
   with socket.create_connection((host,port),timeout=3):rec["tcp_"+str(port)]=True
  except OSError:rec["tcp_"+str(port)]=False
 out[host.split(".")[0]]=rec
if node=="nodeb":
 for container,service in ((212,"mosquitto"),(214,"zigbee2mqtt")):
  a=subprocess.run(["pct","exec",str(container),"--","systemctl","is-active",service],capture_output=True,text=True,timeout=15)
  out[service+"_active"]=a.stdout.strip()=="active"
print("JNS_INCIDENT_NETWORK="+json.dumps(out,sort_keys=True))
'''
def main():
 print("JNS_SECURITY_INCIDENT_READ_ONLY_20261026")
 for node,vm,role in (("nodea",906,"security"),("nodeb",905,"general")):
  state=ssh(node,["qm","status",str(vm)])
  print("JNS_VM_STATE="+json.dumps({"vm":vm,"host":node,"state":state.strip() if state else "unknown"}),flush=True)
  print("JNS_ROLE_"+role.upper()+"="+json.dumps(guest(node,vm,PAYLOAD),sort_keys=True),flush=True)
 for node in ("nodea","nodeb"):
  print("JNS_NETWORK_"+node.upper()+"="+json.dumps(remote(node,NET),sort_keys=True),flush=True)
 print("JNS_INCIDENT_READ_ONLY_COMPLETE=yes")
if __name__=="__main__":main()
