#!/usr/bin/env python3
"""Reversible retirement of obsolete Guardian containers on B then A.

Leaves CT117 on Node C untouched pending its separate authorised inspection.
Only old 900/901-era host timers and cluster proxy are disabled. All guest
disks, systemd unit files, configuration and recovery data are preserved.
Pre/post-check HA role TCP endpoints and dependent production guests. Roll
back target immediately if a postcheck fails.
"""
import base64,json,shlex,subprocess,sys
REMOTE=r'''
import os,re,json,subprocess,socket,sys,time
from pathlib import Path
host=os.uname().nodename.split(".")[0]
def fail(msg):
 print("JNS_GUARDIAN_RETIRE_BLOCKED="+host+"_"+msg,flush=True);sys.exit(80)
def r(cmd,t=20):
 try:return subprocess.run(cmd,capture_output=True,text=True,timeout=t)
 except (OSError,subprocess.TimeoutExpired):return None
if host not in ("nodea","nodeb") or os.geteuid()!=0:fail("unauthorised_host")
if Path("/etc/pve/corosync.conf").exists():fail("real_cluster_config_present")
ct=116 if host=="nodea" else 115
identity="guardian02" if host=="nodea" else "guardian01"
old=r(["pct","status",str(ct)]);cfg=r(["pct","config",str(ct)])
if not old or old.returncode or old.stdout.strip()!="status: running":fail("ct_not_running")
if not cfg or cfg.returncode or not re.search(r"^hostname:\s*"+identity+r"\s*$",cfg.stdout,re.M):
 fail("unexpected_container_identity")
if not re.search(r"^onboot:\s*1\s*$",cfg.stdout,re.M):fail("unexpected_onboot")
if re.search(r"^lock:",cfg.stdout,re.M):fail("ct_locked")
other=(("qm",902),("qm",906),("pct",210),("pct",247)) if host=="nodea" else (
 ("qm",905),("pct",212),("pct",214),("pct",248))
def healthy():
 statuses={}
 for kind,id in other:
  x=r([kind,"status",str(id)])
  statuses[kind+str(id)]=bool(x and x.returncode==0 and x.stdout.strip()=="status: running")
 for name in ("ha-primary.home.arpa","ha-general.home.arpa","ha-security.home.arpa"):
  try:
   with socket.create_connection((name,80),timeout=4):statuses[name]=True
  except OSError:statuses[name]=False
 if host=="nodeb":
  for id,svc in ((212,"mosquitto"),(214,"zigbee2mqtt")):
   p=r(["pct","exec",str(id),"--","systemctl","is-active",svc],12)
   statuses[svc]=bool(p and p.stdout.strip()=="active")
 return statuses
pre=healthy()
if not all(pre.values()):fail("baseline_prod_check_failed_"+",".join(k for k,v in pre.items() if not v)[:100])
unitfiles=["jns-cluster-proxy.service","jns-ha-guardian-probe.timer","lunar-discovery-export.timer"]
stops=["jns-ha-guardian-probe.service","lunar-discovery-export.service"]
states={}
for unit in unitfiles:
 x=r(["systemctl","is-enabled",unit],9)
 states[unit]=x.stdout.strip() if x else "unavailable"
 if states[unit] not in ("enabled","disabled"):fail("unit_state_unexpected_"+unit)
# An undeclared running dependency or live Proxmox cluster would block the change.
# Backup current unit configurations and original CT config in ROOT-only files.
out=Path("/var/lib/jns-solar/guardian-legacy-cold-retirement-20261026")
if out.exists() or out.is_symlink():fail("private_archive_already_exists")
out.mkdir(parents=True,mode=0o700)
with (out/"pct-original.conf").open("x") as f:f.write(cfg.stdout)
data={"ct":ct,"host":host,"old_onboot":1,"units":states,
      "source_left_unchanged":False,
      "epoch":int(time.time())}
(out/"status-before.json").write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
for u in unitfiles:
 source=Path("/etc/systemd/system")/u
 if source.is_file() and not source.is_symlink():
  (out/("unit-"+u)).write_bytes(source.read_bytes())
for v in out.iterdir():os.chmod(v,0o600)
os.chmod(out,0o700)
print("JNS_GUARDIAN_PRIVATE_CONFIG_SAVED="+host,flush=True)
changed=[]
def rollback(reason):
 print("JNS_GUARDIAN_RETIRE_ROLLBACK_TRIGGERED="+host+"_"+reason,flush=True)
 q=r(["pct","status",str(ct)])
 if q and q.stdout.strip()=="status: stopped":r(["pct","start",str(ct)],95)
 r(["pct","set",str(ct),"-onboot","1"])
 for unit,was in states.items():
  if was=="enabled":r(["systemctl","enable","--now",unit],50)
 for unit in stops:
  # Timer will start them again as required.
  pass
 print("JNS_GUARDIAN_RETIRE_ROLLBACK_REQUESTED="+host,flush=True)
 sys.exit(83)
for u in unitfiles:
 z=r(["systemctl","disable","--now",u],55)
 if not z or z.returncode:rollback("disable_failed_"+u)
 changed.append(u)
for u in stops:
 z=r(["systemctl","stop",u],45)
 if not z or z.returncode:rollback("stop_service_failed_"+u)
z=r(["pct","set",str(ct),"-onboot","0"],20)
if not z or z.returncode:rollback("disable_container_autostart_failed")
z=r(["pct","shutdown",str(ct),"--timeout","120"],155)
if not z or z.returncode:rollback("graceful_shutdown_failed")
time.sleep(3)
q=r(["pct","status",str(ct)]);c=r(["pct","config",str(ct)])
if not q or q.stdout.strip()!="status: stopped" or not c or not re.search(r"^onboot:\s*0\s*$",c.stdout,re.M):
 rollback("state_verification_failed")
post=healthy()
if not all(post.values()):rollback("production_health_changed_"+",".join(k for k,v in post.items() if not v)[:100])
status={
 "host":host,"ctid":ct,"ct_stopped":True,"onboot_disabled":True,
 "disabled_unitnames":changed,"guest_disks_retained":True,
 "systemd_files_retained":True,"post_production_healthy":True,
 "pre_production_healthy":True,"rollback_config_saved":True,
 "nodec_guardian_untouched":True}
(out/"completion.json").write_text(json.dumps(status,sort_keys=True,indent=2)+"\n")
os.chmod(out/"completion.json",0o600)
print("JNS_GUARDIAN_COLD_RETIREMENT_VERIFIED="+json.dumps(status,sort_keys=True),flush=True)
'''
def stage(host):
 k=base64.b64encode(REMOTE.encode()).decode()
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6",host,
      shlex.join(["python3","-u","-c","exec(__import__('base64').b64decode('"+k+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=490)
 except (OSError,subprocess.TimeoutExpired):raise SystemExit("JNS_GUARDIAN_REMOTE_TIMEOUT_"+host)
 for line in p.stdout.splitlines():
  if line.startswith("JNS_GUARDIAN_"):print(line,flush=True)
 if p.returncode:raise SystemExit("JNS_GUARDIAN_STAGE_FAILED_"+host)
 if "JNS_GUARDIAN_COLD_RETIREMENT_VERIFIED=" not in p.stdout:
  raise SystemExit("JNS_GUARDIAN_STAGE_INCOMPLETE_"+host)
if __name__=="__main__":
 import os
 if os.uname().nodename.split(".")[0]!="nodec":raise SystemExit("must run Node C runner")
 target=sys.argv[1] if len(sys.argv)>1 else "nodeb"
 if target not in ("nodea","nodeb"):raise SystemExit("unsupported_target")
 stage(target)
 print("JNS_GUARDIAN_"+target.upper()+"_COLD_RETIREMENT_COMPLETE=yes",flush=True)
 print("JNS_GUARDIAN_NODEC_NOT_MODIFIED=yes",flush=True)
