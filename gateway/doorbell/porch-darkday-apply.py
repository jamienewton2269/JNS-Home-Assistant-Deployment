#!/usr/bin/env python3
"""JNS VM905 Porch PIR dark-day amendment. Narrow, backed-up, no HA restart or relay actions."""
import base64, json, shlex, subprocess, time
HOST="nodeb"
VMID="905"
EXPECT_SHA="df03577e509f929b50ba6e5eaaa8d00c4180d0f49a05fbc4bbca96afbfca91ec"
MAIN_ID="1792086505206"

def remote(argv, timeout=27):
    p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
                      "-o","ConnectTimeout=6",HOST,shlex.join(argv)],
                     capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError("NODEB_COMMAND_FAILED "+p.stderr[-240:])
    try: return json.loads(p.stdout)
    except Exception:raise RuntimeError("NODEB_GUEST_JSON_INVALID "+p.stdout[-260:])

def qga(argv, timeout_seconds=180):
    d=remote(["qm","guest","exec",VMID,"--",*argv],timeout=30)
    start=time.monotonic()
    while not d.get("exited"):
        if time.monotonic()-start>timeout_seconds: raise RuntimeError("GUEST_TIMEOUT_AFTER_"+str(timeout_seconds))
        time.sleep(2)
        d=remote(["qm","guest","exec-status",VMID,str(d["pid"])],timeout=18)
    return d.get("exitcode"),(d.get("out-data") or ""),(d.get("err-data") or "")

def python_guest(code,limit=150):
    enc=base64.b64encode(code.encode()).decode()
    return qga(["docker","exec","homeassistant","python3","-c",
               "exec(__import__('base64').b64decode("+repr(enc)+"))"],limit)

APPLY=r'''
from pathlib import Path
import hashlib,os,tempfile,shutil,datetime,json,copy,yaml,re
config=Path("/config/automations.yaml")
old=config.read_bytes()
old_sha=hashlib.sha256(old).hexdigest()
expected="df03577e509f929b50ba6e5eaaa8d00c4180d0f49a05fbc4bbca96afbfca91ec"
id="1792086505206"
old_condition=("  conditions:\n"
"  - condition: sun\n"
"    after: sunset\n"
"    before: sunrise\n")
new_condition=("  conditions:\n"
"  - condition: or\n"
"    conditions:\n"
"    - condition: sun\n"
"      after: sunset\n"
"      before: sunrise\n"
"    - condition: template\n"
"      value_template: >-\n"
"        {{ is_number(states('sensor.jns_lighting_effective_lux'))\n"
"           and is_number(states('input_number.general_outdoor_lighting_on_lux'))\n"
"           and (states('sensor.jns_lighting_effective_lux') | float(999999))\n"
"             <= (states('input_number.general_outdoor_lighting_on_lux') | float(-1)) }}\n")
body=old.decode("utf-8")
pattern=r"(?ms)^- id: '1792086505206'\n.*?(?=^- id: |\Z)"
segments=list(re.finditer(pattern,body))
if len(segments)!=1: raise SystemExit("REFUSE: unique porch automation ID not found")
block=segments[0].group()
if new_condition in block:
 print("JNS_RESULT="+json.dumps({"status":"ALREADY_APPLIED","sha":old_sha}),flush=True)
 raise SystemExit(0)
if old_sha!=expected:
 raise SystemExit("REFUSE: config SHA drift; inspect before editing")
if block.count(old_condition)!=1:raise SystemExit("REFUSE: original condition has changed")
new_block=block.replace(old_condition,new_condition,1)
new_body=body[:segments[0].start()]+new_block+body[segments[0].end():]
original=yaml.safe_load(body)
updated=yaml.safe_load(new_body)
old_items={str(x.get("id")):x for x in original if isinstance(x,dict)}
new_items={str(x.get("id")):x for x in updated if isinstance(x,dict)}
if set(old_items)!=set(new_items) or len(original)!=len(updated):
 raise SystemExit("REFUSE: automation count/IDs changed")
a=copy.deepcopy(new_items[id])
assert a.get("conditions")==[
  {"condition":"or","conditions":[{"condition":"sun","after":"sunset","before":"sunrise"},
   {"condition":"template","value_template":a["conditions"][0]["conditions"][1]["value_template"]}]}]
assert "sensor.jns_lighting_effective_lux" in a["conditions"][0]["conditions"][1]["value_template"]
assert "input_number.general_outdoor_lighting_on_lux" in a["conditions"][0]["conditions"][1]["value_template"]
orig=copy.deepcopy(old_items[id])
a["conditions"]=orig["conditions"]
assert a==orig
for other_id in old_items:
 if other_id!=id and old_items[other_id]!=new_items[other_id]:
  raise SystemExit("REFUSE: unrelated automation changed")
bkdir=Path("/config/.jns_porch_backups")
bkdir.mkdir(exist_ok=True,mode=0o700)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
bk=bkdir/("automations.yaml.before-porch-darkday-"+stamp+".bak")
if bk.exists(): raise SystemExit("REFUSE: backup path conflict")
shutil.copy2(config,bk)
if hashlib.sha256(bk.read_bytes()).hexdigest()!=old_sha:raise SystemExit("REFUSE: backup verification failed")
temp=config.with_name("automations.yaml.jns-porch-new")
if temp.exists():raise SystemExit("REFUSE: leftover staging file requires inspection")
try:
 with open(temp,"xb") as out:
  out.write(new_body.encode("utf-8"))
  out.flush()
  os.fsync(out.fileno())
 shutil.copymode(config,temp)
 if hashlib.sha256(config.read_bytes()).hexdigest()!=old_sha:
  raise SystemExit("REFUSE: config changed during staging")
 os.replace(temp,config)
finally:
 if temp.exists():temp.unlink()
actual=hashlib.sha256(config.read_bytes()).hexdigest()
print("JNS_RESULT="+json.dumps({"status":"PATCHED_NEEDS_RELOAD","backup":str(bk),
      "oldsha":old_sha,"newsha":actual,"automations":len(updated)}),flush=True)
'''
VERIFY=r'''
from pathlib import Path
import yaml,hashlib,json
p=Path("/config/automations.yaml")
s=p.read_bytes()
docs=yaml.safe_load(s)
x=[a for a in docs if isinstance(a,dict) and a.get("id")=="1792086505206"]
assert len(x)==1
conditions=x[0]["conditions"]
assert len(conditions)==1 and conditions[0]["condition"]=="or"
assert len(conditions[0]["conditions"])==2
assert conditions[0]["conditions"][0]=={"condition":"sun","after":"sunset","before":"sunrise"}
assert conditions[0]["conditions"][1]["condition"]=="template"
print("JNS_VERIFIED_CONFIG "+hashlib.sha256(s).hexdigest(),flush=True)
'''
def rollback(path,sha):
    if not path.startswith("/config/.jns_porch_backups/") or not path.endswith(".bak"):
        raise RuntimeError("REFUSE_UNSAFE_ROLLBACK_PATH")
    code=StringToPyReplace(path,sha)
    rc,out,err=python_guest(code)
    print("ROLLBACK_RC",rc,"RESULT",out[-400:],"ERR",err[-100:],flush=True)
    if rc!=0:raise RuntimeError("CRITICAL_ROLLBACK_FAILED")

def StringToPyReplace(path,sha):
    return "from pathlib import Path\nimport os,hashlib,shutil\np=Path('/config/automations.yaml')\nb=Path("+repr(path)+")\ns=b.read_bytes()\nassert hashlib.sha256(s).hexdigest()=="+repr(sha)+"\nt=p.with_name('automations.yaml.jns-rollback-new')\nassert not t.exists()\nshutil.copy2(b,t)\nos.replace(t,p)\nprint('JNS_ROLLBACK_RESTORED')\n"

print("JNS_PORCH_DARK_DAY_PATCH_START",flush=True)
rc,out,err=python_guest(APPLY)
print("PATCH_RC",rc,"PATCH_OUTPUT",out[-1600:],"PATCH_ERR",err[-400:],flush=True)
if rc!=0:raise RuntimeError("PATCH_REFUSED")
data=None
for line in out.splitlines():
    if line.startswith("JNS_RESULT="):data=json.loads(line.split("=",1)[1])
if not data:raise RuntimeError("PATCH_OUTPUT_MISSING")
if data["status"]=="ALREADY_APPLIED":
    print("JNS_PORCH_ALREADY_APPLIED",flush=True)
    raise SystemExit(0)
backup=data["backup"]
sha=data["oldsha"]
try:
    print("JNS_HA_CORE_CHECK_START",flush=True)
    checkrc,check_out,check_err=qga(["ha","core","check"],timeout_seconds=240)
    print("CORE_CHECK_RC",checkrc,"INFO",check_out[-1800:],"ERR",check_err[-1200:],flush=True)
    if checkrc!=0:raise RuntimeError("CONFIG_VALIDATION_FAILED")
    rc,output,err=python_guest(VERIFY)
    print("VERIFY_RC",rc,"OUT",output[-350:],"ERR",err[-300:],flush=True)
    if rc!=0:raise RuntimeError("NEW_CONDITION_VERIFY_FAILED")
except BaseException as e:
    print("VALIDATION_FAILED_ROLLING_BACK",type(e).__name__,str(e)[:250],flush=True)
    rollback(backup,sha)
    raise
print("JNS_PORCH_DARKDAY_CONFIG_VALIDATED_NO_CORE_RESTART",flush=True)
print("BACKUP_AT",backup,flush=True)
print("ACTION_REQUIRED_AUTOMATION_ONLY_RELOAD",flush=True)
