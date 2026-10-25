#!/usr/bin/env python3
"""Transactional, scoped HA-General bedtime Garden String Lights fix; dry-run default."""
from pathlib import Path
import copy,datetime,hashlib,json,os,stat,sys,tempfile,yaml

ROOT=Path("/config")
TARGET=ROOT/"packages/jns_bedtime_controller.yaml"
ENTITY="switch.0xa4c1388ba234f2e3"
NEW_ID="jns_garden_string_morning_catchall_v1"
TAG="JNS_GARDEN_STRING_BEDTIME_20261025"
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def atomic(path,data):
 s=path.stat()
 fd,tmp=tempfile.mkstemp(prefix=".jns-bedtime-",dir=str(path.parent))
 try:
  with os.fdopen(fd,"wb") as f:
   f.write(data);f.flush();os.fsync(f.fileno())
  os.chown(tmp,s.st_uid,s.st_gid)
  os.chmod(tmp,stat.S_IMODE(s.st_mode))
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def main():
 require(TARGET.is_file() and not TARGET.is_symlink(),"Bedtime package missing or symbolic link")
 old=TARGET.read_bytes()
 data=yaml.safe_load(old)
 require(isinstance(data,dict) and isinstance(data.get("script"),dict) and isinstance(data.get("automation"),list),"Unexpected bedtime package schema")
 original=copy.deepcopy(data)
 shutdown=data["script"].get("jns_bedtime_shutdown")
 require(isinstance(shutdown,dict) and isinstance(shutdown.get("sequence"),list),"Staged shutdown script absent")
 seq=shutdown["sequence"]
 relay_var=[x.get("variables",{}).get("relays") for x in seq if isinstance(x,dict) and isinstance(x.get("variables"),dict) and "relays" in x["variables"]]
 require(len(relay_var)==1 and isinstance(relay_var[0],str),"Dynamic relay selection unexpected")
 before=relay_var[0]
 oldrelay="'switch.0xa4c13888eb407dfa'"
 require(before.count(oldrelay)==1,"Original relay marker changed")
 require(ENTITY not in before,"Garden String Lights already in bedtime relay list")
 assert any("switch.turn_off"==step.get("action") for step in seq if isinstance(step,dict) for step in step.get("repeat",{}).get("sequence",[]) if isinstance(step,dict))
 # Modify precisely one Jinja selector; existing scenes snapshot from 'relays' automatically includes target.
 for item in seq:
  if isinstance(item,dict) and isinstance(item.get("variables"),dict) and "relays" in item["variables"]:
   item["variables"]["relays"]=before.replace(oldrelay,oldrelay+", '"+ENTITY+"'")
   break
 a=data["automation"]
 ids=[x.get("id") for x in a if isinstance(x,dict)]
 require("jns_bedtime_clear_scene_at_sunrise" in ids,"Original sunrise reset missing")
 require(NEW_ID not in ids,"Morning catch-all already exists; refusing second copy")
 # Existing snapshot expiration and Lux manual-off reset are not changed.
 a.append({
   "id":NEW_ID,
   "alias":"JNS Garden String Lights - Sunrise and Morning Safety Off",
   "description":TAG+" - independent catch-all; only Garden String Lights",
   "mode":"single",
   "triggers":[
     {"trigger":"sun","event":"sunrise"},
     {"trigger":"time","at":"08:00:00"}],
   "actions":[
     {"action":"switch.turn_off","target":{"entity_id":ENTITY}},
     {"action":"logbook.log","data":{
       "name":"JNS Garden String Lights",
       "message":"Morning safety-off command sent",
       "entity_id":ENTITY}}]
 })
 new=yaml.safe_dump(data,sort_keys=False,allow_unicode=True,width=160).encode()
 require(yaml.safe_load(new)==data and len(data["automation"])==len(original["automation"])+1,"New YAML semantic validation failed")
 assert ENTITY in data["script"]["jns_bedtime_shutdown"]["sequence"][0]["variables"]["relays"]
 print("JNS_BEDTIME_GARDEN_PLAN",json.dumps({
   "target":str(TARGET),"before_sha256":sha(old),"after_sha256":sha(new),
   "added_bedtime_relay":ENTITY,"morning_triggers":["sunrise","08:00 local"],
   "new_automation_id":NEW_ID,"no_other_entities_changed":True
 }),flush=True)
 if "--apply" not in sys.argv:return
 backupdir=ROOT/".jns-backups"/("bedtime-garden-"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
 backupdir.mkdir(mode=0o700,parents=True,exist_ok=False)
 backup=backupdir/TARGET.name
 backup.write_bytes(old)
 os.chmod(backup,0o600)
 require(backup.read_bytes()==old,"Backup readback mismatch")
 require(TARGET.read_bytes()==old,"Concurrent bedtime package edit; abort")
 atomic(TARGET,new)
 require(TARGET.read_bytes()==new,"Post-write hash mismatch")
 print("JNS_BEDTIME_GARDEN_APPLIED",json.dumps({"backup":str(backup),"target":str(TARGET),"before_sha256":sha(old),"after_sha256":sha(new)}),flush=True)
try:main()
except Exception as e:
 print("JNS_BEDTIME_GARDEN_BLOCKED",type(e).__name__,str(e)[:280],flush=True)
 sys.exit(2)
