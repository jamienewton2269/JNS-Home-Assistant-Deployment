#!/usr/bin/env python3
"""VM905 guarded Proxmox reboot to activate already-staged 2048MiB memory.
Requires verified independent snapshot, healthy external MQTT/Zigbee2MQTT
and sufficient Node B RAM. Does not stop any infrastructure LXC.
No force stops, resets, migrations, HA config edits or other VM operations.
"""
import base64,json,os,shlex,subprocess,sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
REMOTE=r'''
import json,os,re,subprocess,sys,time
from pathlib import Path
def fail(msg):
 print("JNS_VM905_REBOOT_BLOCKED="+msg,flush=True)
 raise SystemExit(74)
def run(args,timeout=18):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def field(text,k):
 m=re.search("^"+re.escape(k)+r":\s*(.*)$",text,re.M)
 return m.group(1).strip() if m else None
def running():
 p=run(["qm","status","905"],15)
 return bool(p and p.returncode==0 and p.stdout.strip()=="status: running")
def mem_total():
 p=run(["qm","guest","exec","905","--","cat","/proc/meminfo"],15)
 if not p or p.returncode:return None
 try:j=json.loads(p.stdout)
 except ValueError:return None
 if not j.get("exited") or j.get("exitcode")!=0:return None
 m=re.search(r"(?m)^MemTotal:\s*(\d+)\s+kB",str(j.get("out-data","")))
 return round(int(m.group(1))/1024,1) if m else None
def docker_ok():
 p=run(["qm","guest","exec","905","--","docker","ps",
        "--format","{{.Names}}"],17)
 if not p or p.returncode:return False
 try:j=json.loads(p.stdout)
 except ValueError:return False
 return bool(j.get("exited") and j.get("exitcode")==0 and
             "homeassistant" in str(j.get("out-data","")))
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":fail("wrong_host_or_user")
c=run(["qm","config","905"])
if not c or c.returncode:fail("config_unavailable")
cfg=c.stdout
if field(cfg,"name")!="ha-s2-general" or field(cfg,"memory")!="2048" or field(cfg,"balloon")!="0":
 fail("vm_identity_or_ram_config_mismatch")
if field(cfg,"lock"):fail("vm_has_lock")
if not field(cfg,"scsi0") or not field(cfg,"scsi0").startswith("vmdata:vm-905-disk-1,"):
 fail("storage_mismatch")
if not running():fail("vm905_not_running_before_reboot")
p=run(["free","-m"])
try:available=next(int(x.split()[6]) for x in p.stdout.splitlines() if x.startswith("Mem:"))
except (AttributeError,IndexError,ValueError,StopIteration):fail("host_memory_unavailable")
if available<2500:fail("nodeb_memory_pressure")
for ct,name in ((212,"mosquitto"),(214,"zigbee2mqtt")):
 p=run(["pct","status",str(ct)])
 if not p or p.returncode or p.stdout.strip()!="status: running":fail("required_ct_not_running")
 p=run(["pct","exec",str(ct),"--","systemctl","is-active",name],16)
 if not p or p.returncode or p.stdout.strip()!="active":fail("required_ct_service_unhealthy")
backup=Path("/mnt/pve/NAS/dump/jns-ha-general-consolidation-20261027-v1/MANIFEST.json")
if not backup.is_file() or backup.is_symlink():fail("safety_backup_manifest_missing")
try:m=json.loads(backup.read_text())
except (OSError,ValueError):fail("safety_backup_manifest_invalid")
if m.get("vm")!=905 or m.get("source_host")!="nodeb" or not m.get("zstd_test_passed"):
 fail("safety_backup_not_verified")
if time.time()-backup.stat().st_mtime>48*3600:fail("safety_backup_too_old")
before=mem_total()
if before is None:fail("guest_agent_not_ready")
if before>=1800:
 print("JNS_VM905_REBOOT_COMPLETE="+json.dumps({"already_2gb":True,"guest_mem_total_mib":before,
       "vm_running":True,"guest_core_running":docker_ok(),"reboot_performed":False},sort_keys=True),flush=True)
 raise SystemExit(0)
if before<800 or before>1300:fail("unexpected_pre_reboot_memtotal")
print("JNS_VM905_CONTROLLED_REBOOT_START=yes",flush=True)
p=run(["qm","reboot","905","--timeout","240"],330)
if not p or p.returncode:
 print("JNS_VM905_REBOOT_ERROR=qm_reboot_command_failed",flush=True)
 raise SystemExit(78)
deadline=time.monotonic()+400
memory=None
core=False
while time.monotonic()<deadline:
 if running():
  memory=mem_total()
  if memory is not None and memory>=1800:
   core=docker_ok()
   if core:break
 time.sleep(5)
if not running():fail("vm905_not_running_after_reboot")
if memory is None or memory<1800:fail("pending_memory_not_applied")
if not core:fail("core_container_not_ready")
print("JNS_VM905_REBOOT_COMPLETE="+json.dumps({
 "reboot_performed":True,"vm_running":True,"guest_core_running":True,
 "guest_mem_total_mib":memory,"nodeb_mqtt_untouched":True,
 "nodeb_zigbee2mqtt_untouched":True,"runtime_ownership_unchanged":True},sort_keys=True),flush=True)
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_VM905_REBOOT_BLOCKED=wrong_runner",flush=True);return 1
 if not os.path.isfile("gateway/solar/requests/vm905-activate-2gb-20261027.request"):
  print("JNS_VM905_REBOOT_BLOCKED=no_request_file",flush=True);return 1
 code=base64.b64encode(REMOTE.encode()).decode()
 args=SSH+["nodeb",shlex.join(["python3","-u","-c",
                  "exec(__import__('base64').b64decode('"+code+"'))"])]
 try:r=subprocess.run(args,capture_output=True,text=True,timeout=950)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_VM905_REBOOT_BLOCKED=transport_timeout",flush=True);return 1
 for line in r.stdout.splitlines():
  if line.startswith(("JNS_VM905_","JNS_VM905_REBOOT_ERROR=")):
   print(line,flush=True)
 if r.returncode:
  if not any(x.startswith(("JNS_VM905_REBOOT_BLOCKED=","JNS_VM905_REBOOT_ERROR="))
             for x in r.stdout.splitlines()):
   print("JNS_VM905_REBOOT_ERROR=remote_command_failed",flush=True)
  return 1
 return 0
if __name__=="__main__":sys.exit(main())
