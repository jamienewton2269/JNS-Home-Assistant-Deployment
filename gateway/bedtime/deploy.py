#!/usr/bin/env python3
"""Guarded HA905 Garden String bedtime fix. On Node C runner, no direct host shell changes."""
import base64,json,pathlib,re,subprocess,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
PKG=pathlib.Path("gateway/bedtime/patch_vm905.py")
def guest(args,seconds=270):
 r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--synchronous","0","--",*args]))
 deadline=time.monotonic()+seconds
 while not r.get("exited"):
  if not isinstance(r.get("pid"),int):raise RuntimeError("Guest agent returned no async PID; "+str({"keys":list(r),"exited":r.get("exited"),"exitcode":r.get("exitcode"),"err_tail":str(r.get("err-data") or "")[-220:]}) )
  if time.monotonic()>deadline:raise RuntimeError("QGA PID "+str(r["pid"])+" incomplete; do not retry.")
  time.sleep(3)
  r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
 return r
def core(code,argv=(),seconds=95):
 b64=base64.b64encode(code.encode()).decode()
 py="exec(compile(__import__('base64').b64decode("+repr(b64)+"),'<jns-bedtime-guard>','exec'))"
 return guest(["docker","exec","homeassistant","python3","-c",py,*argv],seconds)
def patch(flag):
 r=core(PKG.read_text(),[flag],seconds=120)
 out=r.get("out-data") or ""
 print("JNS_BEDTIME_PATCH_"+flag.replace("-",""),out[-2400:],flush=True)
 if r.get("exitcode")!=0:raise RuntimeError("Scoped VM905 patch failed "+(r.get("err-data") or "")[-280:])
 tag="JNS_BEDTIME_GARDEN_APPLIED" if flag=="--apply" else "JNS_BEDTIME_GARDEN_PLAN"
 m=re.search(r"(?m)^"+tag+r" (\{.+\})\s*$",out)
 if not m:raise RuntimeError("Missing expected "+tag)
 return json.loads(m.group(1))
ROLLBACK=r"""
from pathlib import Path
import hashlib,os,stat,tempfile,sys
target=Path('/config/packages/jns_bedtime_controller.yaml')
backup=Path(sys.argv[1])
expected_sha=sys.argv[2]
old_sha=sys.argv[3]
assert backup.name==target.name and backup.parent.name.startswith('bedtime-garden-')
assert backup.parent.parent==Path('/config/.jns-backups')
assert not target.is_symlink() and not backup.is_symlink()
current=target.read_bytes()
assert hashlib.sha256(current).hexdigest()==expected_sha, 'Concurrent edit; do not clobber'
old=backup.read_bytes()
assert hashlib.sha256(old).hexdigest()==old_sha, 'Backup checksum mismatch'
s=target.stat()
fd,tmp=tempfile.mkstemp(prefix='.jns-bedtime-rollback-',dir=str(target.parent))
try:
 with os.fdopen(fd,'wb') as f:
  f.write(old);f.flush();os.fsync(f.fileno())
 os.chown(tmp,s.st_uid,s.st_gid);os.chmod(tmp,stat.S_IMODE(s.st_mode))
 os.replace(tmp,target)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
print('JNS_BEDTIME_ROLLBACK_VERIFIED',hashlib.sha256(target.read_bytes()).hexdigest())
"""
def rollback(manifest):
 r=core(ROLLBACK,[manifest["backup"],manifest["after_sha256"],manifest["before_sha256"]],seconds=90)
 print("JNS_BEDTIME_ROLLBACK",(r.get("out-data") or "")[-300:],flush=True)
 if r.get("exitcode")!=0:raise RuntimeError("Rollback could not be confirmed")
def ha(cmd,timeout=260):
 print("JNS_BEDTIME_HA_CLI"," ".join(cmd),flush=True)
 r=guest(["ha",*cmd],seconds=timeout)
 print("JNS_BEDTIME_HA_RESULT",json.dumps({"cmd":" ".join(cmd),"exitcode":r.get("exitcode"),"output":(r.get("out-data") or "")[-650:],"error":(r.get("err-data") or "")[-300:]}),flush=True)
 return r.get("exitcode")==0
VERIFY=r"""
import json,pathlib
root=pathlib.Path('/config')
p=root/'packages/jns_bedtime_controller.yaml'
import yaml
d=yaml.safe_load(p.read_text())
tag='switch.0xa4c1388ba234f2e3'
assert tag in d['script']['jns_bedtime_shutdown']['sequence'][0]['variables']['relays']
assert sum(a.get('id')=='jns_garden_string_morning_catchall_v1' for a in d['automation'])==1
reg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
ids=[x['entity_id'] for x in reg if x.get('platform')=='automation' or x.get('entity_id','').startswith('automation.')]
matches=[x for x in ids if 'garden_string' in x and 'morning' in x]
print('JNS_BEDTIME_POST_BOOT',json.dumps({'bedtime_contains_relay':True,'morning_yaml_present':True,'morning_registered':matches[:8]}))
"""

def ha_background(label,command,seconds=250):
 """Start long HAOS CLI check/restart with a short QGA shell, poll private /tmp exit marker."""
 import os
 if (label,command) not in (("check","core check"),("restart","core restart")):raise RuntimeError("Unexpected HA operation")
 runid=os.environ.get("GITHUB_RUN_ID","manual")
 if not runid.isdecimal():raise RuntimeError("Unsafe run identifier")
 base="/tmp/jns-bedtime-"+label+"-"+runid
 done=base+".rc"
 output=base+".out"
 shell="if test -e "+done+";then exit 7;fi; ( timeout --signal=TERM "+str(seconds)+" ha "+command+" > "+output+" 2>&1; echo $? > "+done+" ) </dev/null >/dev/null 2>&1 & echo JNS_BEDTIME_BG_STARTED"
 start=guest(["sh","-c",shell],seconds=35)
 if start.get("exitcode")!=0 or "JNS_BEDTIME_BG_STARTED" not in (start.get("out-data") or ""):
  raise RuntimeError("Background HA CLI start not confirmed; do not restart or retry blindly")
 print("JNS_BEDTIME_BG_STARTED",label,flush=True)
 until=time.monotonic()+seconds+40
 while time.monotonic()<until:
  time.sleep(6)
  r=guest(["sh","-c","if test -f "+done+";then cat "+done+";else echo PENDING;fi"],seconds=25)
  if r.get("exitcode")!=0:raise RuntimeError("Background HA CLI status unknown")
  ans=(r.get("out-data") or "").strip()
  if ans=="PENDING":continue
  if not ans.isdigit():raise RuntimeError("Malformed background HA CLI exit status")
  rc=int(ans)
  print("JNS_BEDTIME_BG_RESULT",label,"exitcode",rc,flush=True)
  return rc==0
 raise RuntimeError("Background HA CLI command still unconfirmed; no retry")

def main():
 print("JNS_BEDTIME_DEPLOY_BEGIN",flush=True)
 if "running" not in ssh_host("nodeb",["qm","status","905"]):raise RuntimeError("VM905 not running")
 patch("--dry-run")
 manifest=patch("--apply")
 print("JNS_BEDTIME_BACKUP",manifest["backup"],flush=True)
 try:
  if not ha_background("check","core check",seconds=250):
   raise RuntimeError("Home Assistant configuration validation rejected change")
 except Exception:
  try:rollback(manifest)
  except Exception as e:print("JNS_BEDTIME_ROLLBACK_BLOCKED",type(e).__name__,str(e)[:190],flush=True)
  raise
 print("JNS_BEDTIME_CONFIG_VALIDATED",flush=True)
 # HA Core restart required because existing authenticated API reload is HTTP 401.
 if not ha_background("restart","core restart",seconds=170):
  raise RuntimeError("HA Core restart not confirmed; new package remains on disk. Inspect live state before retry.")
 print("JNS_BEDTIME_CORE_RESTART_REQUEST_ACCEPTED",flush=True)
 for i in range(14):
  time.sleep(6)
  try:
   if ha(["core","info"],timeout=40):
    print("JNS_BEDTIME_CORE_RUNNING",flush=True)
    break
  except Exception as e:
   print("JNS_BEDTIME_RECOVERY_PROBE",i+1,type(e).__name__,flush=True)
 else:raise RuntimeError("Core did not report healthy; do not blindly restart or replay deployment")
 r=core(VERIFY,seconds=65)
 print("JNS_BEDTIME_VERIFY",(r.get("out-data") or "")[-1200:],flush=True)
 if r.get("exitcode")!=0 or "JNS_BEDTIME_POST_BOOT" not in (r.get("out-data") or ""):
  raise RuntimeError("Post-boot YAML validation blocked. Do not claim loaded until checked.")
 print("JNS_BEDTIME_CONFIG_ACTIVATED_NO_OTHER_GUEST_CHANGES",flush=True)
if __name__=="__main__":
 try:main()
 except Exception as e:
  print("JNS_BEDTIME_DEPLOY_FAILED",type(e).__name__,str(e)[:350],flush=True)
  sys.exit(2)
