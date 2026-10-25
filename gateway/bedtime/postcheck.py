#!/usr/bin/env python3
"""Read-only HA905 post-activation verification of Garden String bedtime and morning."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
P=r"""
import json,pathlib,datetime,hashlib,sqlite3
import yaml
root=pathlib.Path('/config')
p=root/'packages/jns_bedtime_controller.yaml'
item=yaml.safe_load(p.read_text())
target='switch.0xa4c1388ba234f2e3'
daily=[x for x in item.get('automation',[]) if x.get('id')=='jns_garden_string_morning_catchall_v1']
relay=item['script']['jns_bedtime_shutdown']['sequence'][0]['variables']['relays']
registry=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
registered=[{"id":e.get('entity_id'),"disabled":e.get('disabled_by')}
 for e in registry if 'garden_string_lights' in str(e.get('entity_id','')) and
 e.get('entity_id','').startswith('automation.')]
database=root/'home-assistant_v2.db'
state=None
if database.is_file():
 try:
  con=sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True,timeout=3)
  row=con.execute("SELECT state,last_updated_ts FROM states JOIN states_meta USING(metadata_id) WHERE entity_id=? ORDER BY last_updated_ts DESC LIMIT 1",(target,)).fetchone()
  if row:
   state={'last_recorder_state':row[0],'at_utc':datetime.datetime.fromtimestamp(row[1],datetime.timezone.utc).isoformat() if row[1] else None}
  con.close()
 except Exception:state={"error":"recorder_unavailable"}
print(json.dumps({"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
 "bedtime_target_in_relay_selector":target in relay,
 "morning_automation_exists":len(daily)==1,
 "morning_trigger_count":len(daily[0].get('triggers',[])) if daily else 0,
 "morning_registry_entries":registered[:10],"recorded_device_state":state}))
"""
def guest(a):
 r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*a]))
 for _ in range(25):
  if r.get('exited'):return r
  if not isinstance(r.get('pid'),int):raise RuntimeError("QGA verification unavailable")
  time.sleep(1)
  r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
 raise RuntimeError("QGA read timed out")
print("JNS_BEDTIME_POSTCHECK_BEGIN",flush=True)
print("VM905",ssh_host("nodeb",["qm","status","905"]).strip(),flush=True)
r=guest(["ha","core","info"])
print("CORE_INFO",json.dumps({"exitcode":r.get("exitcode"),"tail":(r.get("out-data") or "")[-850:]}),flush=True)
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(P.encode()).decode())+"))"
r=guest(["docker","exec","homeassistant","python3","-c",code])
print("POSTCHECK_RESULT",r.get('exitcode'),(r.get('out-data') or "")[-3000:],flush=True)
if r.get('exitcode')!=0:raise SystemExit(2)
try:
 r=guest(["docker","inspect","--format","{{.State.StartedAt}}", "homeassistant"])
 print("CORE_CONTAINER_STARTED_UTC",(r.get('out-data') or "").strip()[:120],flush=True)
except Exception as e:print("CORE_CONTAINER_START_UNAVAILABLE",type(e).__name__,flush=True)
