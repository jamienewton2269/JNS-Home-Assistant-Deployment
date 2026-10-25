#!/usr/bin/env python3
"""Read-only live Node A VM906 startup and DNS/bridge diagnostics.

Never print MAC, address, credential, hostname inventory, config or guest output.
"""
import json,subprocess,shlex,socket,urllib.request,urllib.error,re
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6","nodea"]
SCRIPT=r'''
import json,re,subprocess,socket,urllib.request,urllib.error,ipaddress
from pathlib import Path
VM=906
NAME="ha-security.home.arpa"
def run(a,timeout=12):
 try:return subprocess.run(a,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def isok(a):
 p=run(a)
 return p is not None and p.returncode==0
out={"node":"nodea","scope":"VM906"}
p=run(["qm","status",str(VM)])
out["vm_running"]=bool(p and p.returncode==0 and "status: running" in p.stdout)
p=run(["qm","config",str(VM)])
cfg=p.stdout if p and p.returncode==0 else ""
out["vm_config_present"]=bool(cfg)
out["guest_agent_enabled"]=bool(re.search(r"^agent:\\s*(1|enabled=1)",cfg,re.M))
out["vm_net0_present"]=bool(re.search(r"^net0:",cfg,re.M))
out["vm_bridge_vmbr0"]=bool(re.search(r"^net0:.*bridge=vmbr0",cfg,re.M))
out["nic_firewall_enabled"]=bool(re.search(r"^net0:.*firewall=1",cfg,re.M))
net=re.search(r"^net0:.*?(([a-fA-F0-9]{2}:){5}[a-fA-F0-9]{2})",cfg,re.M)
mac=net.group(1).lower() if net else None
p=run(["ip","-o","link","show","tap906i0"])
out["tap_present"]=bool(p and p.returncode==0)
out["tap_up"]=bool(p and p.returncode==0 and "UP" in p.stdout)
p=run(["qm","agent",str(VM),"ping"],timeout=9)
out["guest_agent_responding"]=bool(p and p.returncode==0)
try:
 dns={v[4][0] for v in socket.getaddrinfo(NAME,None)}
except (socket.gaierror,OSError):dns=set()
out["dns_resolves"]=bool(dns)
out["dns_has_ipv4"]=any(":" not in v for v in dns)
out["dns_has_ipv6"]=any(":" in v for v in dns)
for port in (8123,4357,22):
 ok=False
 for addr in dns:
  try:
   s=socket.create_connection((addr,port),timeout=2);s.close();ok=True;break
  except OSError:pass
 out["dns_tcp_"+str(port)+"_reachable"]=ok
p=run(["ip","-j","neigh","show","dev","vmbr0"])
if p and p.returncode==0:
 try:
  neighbors=json.loads(p.stdout)
  matches=[x for x in neighbors if mac and x.get("lladdr","").lower()==mac]
  out["bridge_neighbor_mac_seen"]=bool(matches)
  out["mac_neighbor_has_ip"]=any(bool(x.get("dst")) for x in matches)
  out["dns_ip_matches_mac_neighbor"]=any(x.get("dst") in dns for x in matches)
 except ValueError:out["neighbor_probe"]="invalid"
else:out["neighbor_probe"]="unavailable"
out["haos_disk_zfs_present"]=isok(["zfs","list","-H","vmdata/vm-906-disk-1"])
p=run(["qm","config",str(VM)])
out["onboot"]=(re.search(r"^onboot:\\s*([01])",p.stdout,re.M).group(1) if p and re.search(r"^onboot:\\s*([01])",p.stdout,re.M) else "unknown")
print("VM906_NODEA_DIAGNOSTIC="+json.dumps(out,sort_keys=True))
'''
def main():
 p=subprocess.run(SSH+[shlex.join(["python3","-c",SCRIPT])],
   capture_output=True,text=True,timeout=55)
 if p.returncode:
  print("VM906_NODEA_DIAGNOSTIC_UNAVAILABLE=rc_"+str(p.returncode))
  return
 for l in p.stdout.splitlines():
  if l.startswith("VM906_NODEA_DIAGNOSTIC="):
   print(l)
print("VM906_NODEA_NETWORK_AUDIT_START")
main()
print("VM906_NODEA_NETWORK_AUDIT_END")
