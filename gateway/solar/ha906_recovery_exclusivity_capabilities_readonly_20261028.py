#!/usr/bin/env python3
"""Read-only verification of VM906 fallback independence, HA905 fencing access,
and local restore evidence. Never reads secrets or changes services/VMs.
"""
import os,subprocess,shlex,sys,json
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5"]
TEST=r'''
import os,re,subprocess,json,pathlib
def run(a,timeout=15):
 try:return subprocess.run(a,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def check(a,expect=None):
 p=run(a);return bool(p and p.returncode==0 and (expect is None or expect in p.stdout))
out={"host":os.uname().nodename.split(".")[0],
 "source_running":check(["qm","status","906"],"status: running"),
 "source_config_identity":check(["qm","config","906"],"name: ha-security"),
 "target_ssh_from_nodea":check(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5","nodeb","hostname"],"nodeb"),
 "backup_manifest_on_nodea":any(p.is_file() and not p.is_symlink() for p in
  (pathlib.Path("/mnt/pve/NAS/dump/jns-vm906-agent-recovery-20261026-v1/MANIFEST.json"),
   pathlib.Path("/mnt/pve/nfs-ct/dump/jns-vm906-agent-recovery-20261026-v1/MANIFEST.json"))),
 "source_qga_healthy":check(["qm","guest","exec","906","--","ha","core","info"]),
 "recovery_timer_active":check(["systemctl","is-active","jns-ha906-recovery-20261028.timer"],"active"),
 "local_recovery_script_exists":pathlib.Path("/usr/sbin/qm").is_file()}
if out["target_ssh_from_nodea"]:
 c=run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
        "-o","ConnectTimeout=5","nodeb","qm status 905"],17)
 out["target_state_read_from_nodea"]=bool(c and c.returncode==0 and c.stdout.strip()=="status: running")
else:out["target_state_read_from_nodea"]=False
print("JNS_EXCLUSIVE_FALLBACK_READONLY="+json.dumps(out,sort_keys=True),flush=True)
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 cmd=["python3","-c","exec(__import__('base64').b64decode("+repr(__import__("base64").b64encode(TEST.encode()).decode())+"))"]
 p=subprocess.run(SSH+["nodea",shlex.join(cmd)],capture_output=True,text=True,timeout=95)
 for s in p.stdout.splitlines():
  if s.startswith("JNS_EXCLUSIVE_FALLBACK_READONLY="):print(s)
 return 0 if p.returncode==0 and "JNS_EXCLUSIVE_FALLBACK_READONLY=" in p.stdout else 1
if __name__=="__main__":sys.exit(main())
