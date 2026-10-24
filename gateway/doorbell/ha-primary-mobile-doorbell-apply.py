#!/usr/bin/env python3
"""Transactional, no-restart HA-Primary VM902 front doorbell -> Android notify MVP."""
import base64,json,shlex,subprocess,time
HOST="nodea";VM="902";EXPECTED="4ad16903025b09ea1e0189cd57a0bc122825ffac77ea67e796b08cfe8a0f0280"
APPLY=r'''
from pathlib import Path
import re,yaml,hashlib,shutil,os,json,datetime
P=Path("/config")
p=P/"automations.yaml"
old=p.read_bytes()
oldhash=hashlib.sha256(old).hexdigest()
expect="4ad16903025b09ea1e0189cd57a0bc122825ffac77ea67e796b08cfe8a0f0280"
id="jns_primary_doorbell_phone_notification_v1"
new_item={
 "id":id,
 "alias":"JNS Primary - Front Doorbell Mobile Alert",
 "description":"Notify the registered SM-S721B phone from HA-Security's nonretained MQTT doorbell event. No camera streaming or sounder control on HA-Primary.",
 "triggers":[{"trigger":"mqtt","topic":"jns/security/doorbell/press","payload":"pressed"}],
 "conditions":[],
 "actions":[{"action":"notify.send_message","target":{"entity_id":"notify.sm_s721b"},"data":{"title":"Front doorbell","message":"Someone has pressed the front doorbell. Open Home Assistant to check the camera."}},
 {"delay":"00:00:05"}],
 "mode":"single",
 "max_exceeded":"silent"
}
current=yaml.safe_load(old) or []
if not isinstance(current,list):raise SystemExit("REFUSE: existing automation root not list")
if any(x.get("id")==id for x in current if isinstance(x,dict)):
 print("RESULT="+json.dumps({"status":"ALREADY_PRESENT"}),flush=True)
 raise SystemExit(0)
if oldhash!=expect:raise SystemExit("REFUSE: HA-Primary automation file changed since preflight")
reg=json.loads((P/".storage/core.entity_registry").read_text())["data"]["entities"]
if not any(e.get("entity_id")=="notify.sm_s721b" and e.get("disabled_by") is None for e in reg):
 raise SystemExit("REFUSE: registered mobile notification entity unavailable")
cfg=json.loads((P/".storage/core.config_entries").read_text())["data"]["entries"]
if not any(e.get("domain")=="mqtt" and e.get("disabled_by") is None for e in cfg):
 raise SystemExit("REFUSE: HA-Primary MQTT not enabled")
snippet=(
"- id: jns_primary_doorbell_phone_notification_v1\n"
"  alias: JNS Primary - Front Doorbell Mobile Alert\n"
"  description: >-\n"
"    Notify the registered SM-S721B phone on a new doorbell MQTT event.\n"
"    No camera processing or sounder control runs on HA-Primary.\n"
"  triggers:\n"
"  - trigger: mqtt\n"
"    topic: jns/security/doorbell/press\n"
"    payload: 'pressed'\n"
"  conditions: []\n"
"  actions:\n"
"  - action: notify.send_message\n"
"    target:\n"
"      entity_id: notify.sm_s721b\n"
"    data:\n"
"      title: Front doorbell\n"
"      message: Someone has pressed the front doorbell. Open Home Assistant to check the camera.\n"
"  - delay: '00:00:05'\n"
"  mode: single\n"
"  max_exceeded: silent\n")
sep="\n" if not old.endswith(b"\n") else ""
candidate=old.decode()+sep+snippet
newlist=yaml.safe_load(candidate)
if len(newlist)!=len(current)+1:raise SystemExit("REFUSE: unexpected automation count")
if newlist[:-1]!=current or newlist[-1].get("id")!=id:
 raise SystemExit("REFUSE: extra changes detected")
a=newlist[-1]
if (a["triggers"][0]["topic"],a["triggers"][0]["payload"])!=("jns/security/doorbell/press","pressed"):
 raise SystemExit("REFUSE: trigger differs from verified event")
if a["actions"][0]["target"]!={"entity_id":"notify.sm_s721b"}:
 raise SystemExit("REFUSE: unexpected notification target")
backups=P/".jns_doorbell_backups"
backups.mkdir(exist_ok=True,mode=0o700)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup=backups/("ha-primary-automations.before-mobile-doorbell-"+stamp+".bak")
if backup.exists():raise SystemExit("REFUSE: backup name collision")
shutil.copy2(p,backup)
if hashlib.sha256(backup.read_bytes()).hexdigest()!=oldhash:raise SystemExit("REFUSE: backup failed hash")
stage=p.with_name("automations.yaml.jns-mobile-new")
if stage.exists():raise SystemExit("REFUSE: unfinished stage exists")
try:
 with open(stage,"xb") as f:
  f.write(candidate.encode());f.flush();os.fsync(f.fileno())
 shutil.copymode(p,stage)
 if hashlib.sha256(p.read_bytes()).hexdigest()!=oldhash:raise SystemExit("REFUSE: concurrent edit")
 os.replace(stage,p)
finally:
 if stage.exists():stage.unlink()
print("RESULT="+json.dumps({"status":"PATCHED_NEEDS_RELOAD","backup":str(backup),"oldsha":oldhash,"newsha":hashlib.sha256(p.read_bytes()).hexdigest(),"count":len(newlist)}),flush=True)
'''
VERIFY=r'''
from pathlib import Path
import yaml,hashlib,json
p=Path("/config/automations.yaml")
items=yaml.safe_load(p.read_text())
new=[x for x in items if isinstance(x,dict) and x.get("id")=="jns_primary_doorbell_phone_notification_v1"]
assert len(new)==1
x=new[0]
assert x["triggers"]==[{"trigger":"mqtt","topic":"jns/security/doorbell/press","payload":"pressed"}]
assert x["actions"][0]["action"]=="notify.send_message"
assert x["actions"][0]["target"]["entity_id"]=="notify.sm_s721b"
print("VERIFY_OK count",len(items),"sha",hashlib.sha256(p.read_bytes()).hexdigest(),flush=True)
'''
def cmd(hostargs,timeout=250):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",HOST,shlex.join(hostargs)],capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError("SSH_FAILED "+p.stderr[-250:])
 return json.loads(p.stdout)
def guest(args,limit=180):
 d=cmd(["qm","guest","exec",VM,"--",*args],timeout=limit+30)
 pid=d.get("pid");started=time.monotonic()
 while not d.get("exited"):
  if pid is None or time.monotonic()-started>limit:raise RuntimeError("GUEST_TIMEOUT_OR_NO_PID")
  time.sleep(2)
  d=cmd(["qm","guest","exec-status",VM,str(pid)],timeout=25)
 return d.get("exitcode"),d.get("out-data","") or "",d.get("err-data","") or ""
def inside(src,limit=35):
 payload="exec(__import__('base64').b64decode("+repr(base64.b64encode(src.encode()).decode())+"))"
 return guest(["docker","exec","homeassistant","python3","-c",payload],limit)
def rollback(path,sha):
 if not path.startswith("/config/.jns_doorbell_backups/") or not path.endswith(".bak"):
  raise RuntimeError("UNSAFE_BACKUP_PATH")
 py=("from pathlib import Path\nimport hashlib,os,shutil\n"
 "p=Path('/config/automations.yaml')\n"
 "b=Path("+repr(path)+")\n"
 "assert hashlib.sha256(b.read_bytes()).hexdigest()=="+repr(sha)+"\n"
 "t=p.with_name('automations.yaml.jns-mobile-rollback')\n"
 "assert not t.exists()\n"
 "shutil.copy2(b,t)\nos.replace(t,p)\nprint('JNS_MOBILE_ROLLBACK_OK')\n")
 rc,out,err=inside(py,limit=40)
 print("ROLLBACK",rc,out[-500:],err[-200:],flush=True)
 if rc!=0:raise RuntimeError("CRITICAL_ROLLBACK_FAILED")
print("JNS_HA_PRIMARY_MOBILE_DOORBELL_PATCH_START",flush=True)
rc,out,err=inside(APPLY,limit=40)
print("PATCH",rc,out[-1200:],err[-700:],flush=True)
if rc!=0:raise RuntimeError("PATCH_REFUSED")
info=None
for line in out.splitlines():
 if line.startswith("RESULT="):info=json.loads(line[len("RESULT="):])
if info is None:raise RuntimeError("NO_PATCH_RESULT")
if info["status"]=="ALREADY_PRESENT":
 print("ALREADY_PRESENT_NO_CHANGE",flush=True)
 raise SystemExit(0)
try:
 print("HA_PRIMARY_CORE_CHECK_START",flush=True)
 rc,out,err=guest(["ha","core","check"],limit=240)
 print("CORE_CHECK",rc,out[-1400:],err[-1000:],flush=True)
 if rc!=0:raise RuntimeError("HA_CONFIG_CHECK_FAILED")
 rc,out,err=inside(VERIFY,limit=30)
 print("VERIFY",rc,out[-600:],err[-300:],flush=True)
 if rc!=0:raise RuntimeError("VERIFICATION_FAILED")
except BaseException as e:
 print("VALIDATION_FAILED_ROLLBACK",type(e).__name__,str(e)[:180],flush=True)
 rollback(info["backup"],info["oldsha"])
 raise
print("JNS_HA_PRIMARY_MOBILE_NOTIFY_STAGED_VALIDATED",flush=True)
print("BACKUP",info["backup"],flush=True)
print("NOT_ACTIVE_UNTIL_AUTOMATION_ONLY_RELOAD",flush=True)
print("NO_MOBILE_NOTIFICATION_SENT_AS_PART_OF_APPLY",flush=True)
