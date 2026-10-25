#!/usr/bin/env python3
"""Read-only Proxmox VM906 console/device support and guest baseline."""
import subprocess,shlex,json,re
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6","nodea"]
REMOTE=r'''
import json,re,subprocess
def run(cmd,timeout=12):
 try:return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
p=run(["qm","config","906"])
cfg=p.stdout if p and p.returncode==0 else ""
out={"name_confirmed":bool(re.search(r"^name:\s+ha-security",cfg,re.M)),
 "serial_port_defined":bool(re.search(r"^serial\d+:",cfg,re.M)),
 "vga_type":"serial" if re.search(r"^vga:\s*serial",cfg,re.M) else "other",
 "agent_enabled":bool(re.search(r"^agent:\s*(1|enabled=1)",cfg,re.M)),
 "ostype":(re.search(r"^ostype:\s*(\S+)",cfg,re.M).group(1) if re.search(r"^ostype:\s*(\S+)",cfg,re.M) else "unknown"),
 "boot_type":"uefi" if re.search(r"^bios:\s*ovmf",cfg,re.M) else "other"}
p=run(["qm","status","906"])
out["running"]=bool(p and p.returncode==0 and "running" in p.stdout)
p=run(["qm","monitor","906"],3)
out["qemu_monitor_noninteractive_available"]=bool(p and p.returncode==0)
print("VM906_CONSOLE_CAPABILITIES="+json.dumps(out,sort_keys=True))
'''
def main():
 p=subprocess.run(SSH+[shlex.join(["python3","-c",REMOTE])],capture_output=True,text=True,timeout=35)
 if p.returncode:
  print("VM906_CONSOLE_CAPABILITIES_BLOCKED=remote_failure");return
 for line in p.stdout.splitlines():
  if line.startswith("VM906_CONSOLE_CAPABILITIES="):print(line)
main()
